"""No network. Exercise spend invariants and the live adapter's failure boundaries."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amiga_ocr.fixtures import scenario
from amiga_ocr.live_budget import RESERVATION_MICRO_USD, BudgetError, BudgetLedger
from amiga_ocr.openai_live import Config, LiveError, OpenAIClient, ROOT, make_payload, normalize_payload, normalize_response, usage_cost


def ledger():
    # Persist test-only files in the workspace; never touch the real spend ledger.
    result = BudgetLedger(ROOT / 'prototype' / 'output' / 'test-runtime' / (str(uuid4()) + '.sqlite3'))
    result.initialize()
    return result


def response():
    payload = scenario('normal').invoice_payload
    raw = {'invoice': payload['invoice'], 'evidence': [
        {'field': key, 'page': entry['page'], 'raw_value': entry['raw_value']}
        for key, entry in payload['source_evidence'].items() if entry is not None]}
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(raw)}]}],
        'usage': {'input_tokens': 5000, 'output_tokens': 2000}, 'service_tier': 'default'}


class BudgetTests(unittest.TestCase):
    def test_twenty_six_calls_exhaust_budget_persistently(self):
        log = ledger()
        for _ in range(26):
            log.finish(log.reserve('test'), 'HTTP_ERROR')
        with self.assertRaises(BudgetError):
            BudgetLedger(log.path).reserve('twenty-seventh')
        self.assertEqual(log.snapshot()['reserved_authorization_usd'], '7.8')
        self.assertEqual(log.snapshot()['remaining_calls'], 0)

    def test_snapshot_counts_remaining_calls_in_whole_reservations(self):
        log = ledger()
        self.assertEqual(log.snapshot()['remaining_calls'], 26)
        log.finish(log.reserve('test'), 'HTTP_ERROR')
        self.assertEqual(log.snapshot()['remaining_calls'], 25)

    def test_unknown_or_pending_call_blocks_restart(self):
        log = ledger()
        attempt = log.reserve('test')
        with self.assertRaises(BudgetError):
            BudgetLedger(log.path).reserve('next')
        log.finish(attempt, 'UNCERTAIN')
        with self.assertRaises(BudgetError):
            BudgetLedger(log.path).reserve('next')

    def test_missing_ledger_and_cap_override_fail_closed(self):
        with self.assertRaises(BudgetError):
            BudgetLedger(ROOT / ('absent-' + str(uuid4()))).reserve('test')
        for cap in ('10', 'Infinity', 'NaN', '-1', '0'):
            with self.subTest(cap=cap), self.assertRaises(BudgetError):
                BudgetLedger(ROOT / 'unused', Decimal(cap))

    def test_ledger_cannot_be_reinitialized(self):
        log = ledger()
        log.finish(log.reserve('test'), 'HTTP_ERROR')
        with self.assertRaises(FileExistsError):
            log.initialize()
        self.assertEqual(log.snapshot()['attempt_count'], 1)

    def test_concurrent_reservations_allow_only_one_in_flight(self):
        log = ledger()
        def reserve(_):
            try:
                return BudgetLedger(log.path).reserve('concurrent')
            except BudgetError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_lower_limit_and_double_finish(self):
        log = ledger()
        log = BudgetLedger(log.path, Decimal('0.5'))
        attempt = log.reserve('one')
        log.finish(attempt, 'COMPLETED', {}, Decimal('0.001'))
        with self.assertRaises(BudgetError):
            log.finish(attempt, 'HTTP_ERROR')
        with self.assertRaises(BudgetError):
            log.reserve('two')


class LiveTests(unittest.TestCase):
    def test_payload_has_fixed_model_no_tools_no_storage_and_output_limit(self):
        payload = make_payload(b'%PDF-demo')
        self.assertEqual(payload['model'], 'gpt-6-luna')
        self.assertEqual(payload['service_tier'], 'default')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'], 8192)
        self.assertNotIn('tools', payload)
        for value in (b'not pdf', b'%PDF-' + b'x' * 5_000_000):
            with self.assertRaises(LiveError):
                make_payload(value)

    def test_account_zeros_and_missing_value_preserved(self):
        result = normalize_response(response(), 'doc_demo_001')
        self.assertEqual(result['invoice']['payment']['account_number'], '00123456')
        self.assertIsNone(result['invoice']['due_date'])

    def test_empty_field_takes_back_its_own_unambiguous_quote(self):
        # Seen live on a PNG: the quotes held every value while the invoice fields were null.
        raw = json.loads(response()['output'][0]['content'][0]['text'])
        quotes = {'vendor_name': 'PT Contoh Demo', 'vendor_npwp': '99.123.456.7-012.000', 'stated_total': '4.440.000,00',
                  'invoice_date': '2026-10-14', 'due_date': '28 Oktober 2026', 'po_number': 'Nomor PO: PO-1',
                  'payment.account_number': '00123456'}
        for path in quotes:
            if path.startswith('payment.'):
                raw['invoice']['payment'][path[8:]] = None
            else:
                raw['invoice'][path] = None
        raw['evidence'] = [e for e in raw['evidence'] if e['field'] not in quotes]
        raw['evidence'] += [{'field': path, 'page': 1, 'raw_value': quote} for path, quote in quotes.items()]
        invoice = normalize_payload(raw, 'doc')['invoice']
        self.assertEqual((invoice['vendor_name'], invoice['vendor_npwp'], invoice['stated_total'], invoice['invoice_date'],
                          invoice['payment']['account_number']),
                         ('PT Contoh Demo', '99.123.456.7-012.000', '4440000.00', '2026-10-14', '00123456'))
        # A non-ISO date and a quote that still carries its label stay unread rather than guessed.
        self.assertIsNone(invoice['due_date'])
        self.assertIsNone(invoice['po_number'])

    def test_common_spellings_are_normalized_and_uncertain_formats_become_unread(self):
        # Seen live on real scans: 'Rp' as currency and a written-out due date rejected the whole invoice.
        raw = json.loads(response()['output'][0]['content'][0]['text'])
        raw['invoice'].update(currency='Rp', due_date='30 Oktober 2026', invoice_date='14/10/2026',
                              stated_total='4.440.000,00')
        raw['invoice']['line_items'][0]['unit_price'] = '1.500.000'
        raw['evidence'] = [e for e in raw['evidence'] if e['field'] not in ('currency', 'due_date', 'invoice_date')]
        invoice = normalize_payload(raw, 'doc')['invoice']
        self.assertEqual((invoice['currency'], invoice['due_date'], invoice['stated_total']), ('IDR', '2026-10-30', '4440000.00'))
        self.assertIsNone(invoice['invoice_date'])
        self.assertIsNone(invoice['line_items'][0]['unit_price'])

    def test_refusal_and_partial_output_rejected(self):
        for result in ({'status': 'incomplete'}, {'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'refusal'}]}]}):
            with self.assertRaises(LiveError):
                normalize_response(result, 'doc')

    def test_worst_model_context_reservation_has_headroom(self):
        self.assertEqual(usage_cost({'input_tokens': 1_050_000, 'output_tokens': 8192}), Decimal('0.268644'))
        self.assertLess(usage_cost({'input_tokens': 1_050_000, 'output_tokens': 8192}),
                        Decimal(RESERVATION_MICRO_USD) / 1_000_000)
        for usage in ({}, {'input_tokens': True, 'output_tokens': 1}, {'input_tokens': 1, 'output_tokens': 8193}):
            with self.assertRaises(LiveError):
                usage_cost(usage)

    def test_timeout_is_not_retried_or_refunded(self):
        log = ledger()
        client = OpenAIClient(Config('sk-test'), log)
        with patch.object(client, '_request', side_effect=TimeoutError()) as request:
            with self.assertRaises(LiveError):
                client.extract_pdf(b'%PDF-demo', 'timeout')
            self.assertEqual(request.call_count, 1)
        self.assertEqual(log.snapshot()['reserved_authorization_usd'], '0.3')
        self.assertEqual(log.snapshot()['states'], ['UNCERTAIN'])

    def test_http_error_is_one_counted_attempt(self):
        log = ledger()
        client = OpenAIClient(Config('sk-test'), log)
        error = urllib.error.HTTPError('https://api.openai.com', 429, 'rate limit', {}, None)
        with patch.object(client, '_request', side_effect=error) as request:
            with self.assertRaises(LiveError):
                client.extract_pdf(b'%PDF-demo', 'rate-limit')
            self.assertEqual(request.call_count, 1)
        self.assertEqual(log.snapshot()['states'], ['HTTP_ERROR'])

    def test_usage_accounted_even_if_invoice_is_incomplete(self):
        log = ledger()
        client = OpenAIClient(Config('sk-test'), log)
        partial = response()
        partial['status'] = 'incomplete'
        with patch.object(client, '_request', return_value=partial):
            trace = client.extract_pdf(b'%PDF-demo', 'partial')
        self.assertEqual(log.snapshot()['states'], ['COMPLETED'])
        with self.assertRaises(LiveError):
            normalize_response(trace['response'], 'doc')

    def test_unknown_billing_blocks_subsequent_calls(self):
        log = ledger()
        client = OpenAIClient(Config('sk-test'), log)
        with patch.object(client, '_request', return_value={'status': 'completed'}):
            with self.assertRaises(LiveError):
                client.extract_pdf(b'%PDF-demo', 'unknown')
        with self.assertRaises(BudgetError):
            log.reserve('next')

    def test_key_never_appears_in_config_repr(self):
        self.assertNotIn('testsecret', repr(Config('sk-testsecret')))


if __name__ == '__main__':
    unittest.main()
