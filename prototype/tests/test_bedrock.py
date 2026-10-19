"""No network. Bedrock adapter: request shape, rendering, ledger states, retries and config secrecy."""

from contextlib import closing
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from uuid import uuid4

from botocore.exceptions import ClientError, ReadTimeoutError
from PIL import Image
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amiga_ocr.bedrock_live import (INSTRUCTION, RESERVATION_MICRO_USD, TOOL_NAME, BedrockClient, BedrockConfig,
                                    BedrockError, bedrock_schema, worst_case_request_usd)
from amiga_ocr.fixtures import scenario
from amiga_ocr.live_budget import BudgetError, BudgetLedger
from amiga_ocr.openai_live import PROMPT, ROOT, LiveError

RUNTIME_DIR = ROOT / 'prototype' / 'output' / 'test-runtime'
METADATA = {'vendor_npwp': '99.123.456.7-012.000', 'buyer_name': 'PT Klien Contoh A',
            'buyer_npwp': '99.765.432.1-098.000', 'po_number': 'PO-DEMO-0099',
            'faktur_number': '010.000-26.00000099', 'faktur_date': '2026-10-12'}


def ledger(reservation=RESERVATION_MICRO_USD):
    # Throwaway ledgers only; the real Bedrock ledgers are provisioned by the lead.
    result = BudgetLedger(RUNTIME_DIR / (str(uuid4()) + '.sqlite3'), Decimal('2.00'), reservation)
    result.initialize()
    return result


def rows(log):
    with closing(sqlite3.connect(log.path.as_uri() + '?mode=ro', uri=True)) as conn:
        return conn.execute('SELECT id, state, usage_json, cost_upper_usd FROM attempts ORDER BY created').fetchall()


def config(**overrides):
    return BedrockConfig('TESTACCESSKEY00000002', 'testsecretvalue', **overrides)


def tool_payload():
    payload = scenario('normal').invoice_payload
    invoice = deepcopy(payload['invoice'])
    invoice.pop('vendor_id')  # the Bedrock schema omits it; the client adds it back
    invoice.update(METADATA)
    invoice['stated_other_charges_total'] = None  # schema v3 asks for it; the sample prints no such charge
    evidence = [{'field': key, 'page': entry['page'], 'raw_value': entry['raw_value']}
                for key, entry in payload['source_evidence'].items() if entry is not None]
    evidence += [{'field': key, 'page': 1, 'raw_value': value} for key, value in METADATA.items()]
    return {'invoice': invoice, 'evidence': evidence}


def converse(payload=None, usage=(2728, 1184), retries=0, missing_tool=False, drop=()):
    payload = tool_payload() if payload is None else payload
    content = [{'text': 'No tool call.'}] if missing_tool else [
        {'toolUse': {'toolUseId': 'tooluse_test', 'name': TOOL_NAME, 'input': payload}}]
    response = {'ResponseMetadata': {'RequestId': 'req-test', 'HTTPStatusCode': 200,
                                     'HTTPHeaders': {'x-amzn-requestid': 'req-test'}, 'RetryAttempts': retries},
                'output': {'message': {'role': 'assistant', 'content': content}},
                'stopReason': 'end_turn' if missing_tool else 'tool_use',
                'usage': {'inputTokens': usage[0], 'outputTokens': usage[1], 'totalTokens': sum(usage)},
                'metrics': {'latencyMs': 5100}}
    for key in drop:
        response.pop(key)
    return response


class FakeRuntime:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def converse(self, **request):
        self.calls.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def client(*outcomes, log=None):
    runtime = FakeRuntime(*outcomes)
    return BedrockClient(config(), log or ledger(), runtime), runtime


def pdf_bytes(pages=2, text=True):
    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page(width=595, height=842)
        if text:
            page.insert_text((72, 72), f'INVOICE INV-DEMO-001 page {number + 1}')
        else:
            page.draw_rect(pymupdf.Rect(72, 72, 300, 200), fill=(0, 0, 0))
    return document.tobytes()


def access_denied():
    return ClientError({'Error': {'Code': 'AccessDeniedException', 'Message':
                                  'User: arn:aws:iam::123456789012:user/student9 is not authorized'}}, 'Converse')


class RequestTests(unittest.TestCase):
    def test_pdf_pages_become_png_images_with_text_hints(self):
        bedrock, runtime = client(converse())
        trace = bedrock.extract_document(pdf_bytes(2), 'application/pdf', 'pdf')
        content = runtime.calls[0]['messages'][0]['content']
        self.assertEqual(len(content), 7)
        self.assertEqual([content[0], content[3], content[6]],
                         [{'text': 'Page 1:'}, {'text': 'Page 2:'}, {'text': INSTRUCTION}])
        for image_block, hint_block, number in ((content[1], content[2], 1), (content[4], content[5], 2)):
            self.assertEqual(image_block['image']['format'], 'png')
            data = image_block['image']['source']['bytes']
            self.assertTrue(data.startswith(b'\x89PNG'))
            self.assertEqual(Image.open(io.BytesIO(data)).size, (1190, 1684))
            self.assertTrue(hint_block['text'].startswith(f'Text layer hint for page {number}:'))
            self.assertIn(f'INV-DEMO-001 page {number}', hint_block['text'])
        self.assertEqual([page['text_hint'] for page in trace['pages']], [True, True])

    def test_scanned_pdf_page_has_no_hint(self):
        bedrock, runtime = client(converse())
        bedrock.extract_pdf(pdf_bytes(1, text=False), 'scan')
        content = runtime.calls[0]['messages'][0]['content']
        self.assertEqual([list(block) for block in content], [['text'], ['image'], ['text']])

    def test_jpeg_is_sent_as_one_upright_downscaled_image(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # stored sideways; must arrive upright
        out = io.BytesIO()
        Image.new('RGB', (3000, 2000), 'white').save(out, 'JPEG', exif=exif.tobytes())
        original = out.getvalue()
        bedrock, runtime = client(converse())
        trace = bedrock.extract_document(original, 'image/jpeg', 'photo')
        content = runtime.calls[0]['messages'][0]['content']
        self.assertEqual(content[0], {'text': 'Page 1:'})
        self.assertEqual(content[1]['image']['format'], 'jpeg')
        self.assertEqual(Image.open(io.BytesIO(content[1]['image']['source']['bytes'])).size, (1600, 2400))
        self.assertEqual(content[2], {'text': INSTRUCTION})
        self.assertEqual(len(content), 3)
        self.assertFalse(trace['pages'][0]['text_hint'])
        self.assertEqual(original, out.getvalue())

    def test_transparent_png_is_flattened_on_white(self):
        out = io.BytesIO()
        Image.new('RGBA', (120, 60), (0, 0, 0, 0)).save(out, 'PNG')
        bedrock, runtime = client(converse())
        bedrock.extract_document(out.getvalue(), 'image/png', 'png')
        block = runtime.calls[0]['messages'][0]['content'][1]['image']
        self.assertEqual(block['format'], 'png')
        image = Image.open(io.BytesIO(block['source']['bytes']))
        self.assertEqual((image.mode, image.getpixel((0, 0))), ('RGB', (255, 255, 255)))

    def test_tool_choice_forces_the_invoice_tool(self):
        bedrock, runtime = client(converse())
        bedrock.extract_pdf(pdf_bytes(1), 'shape')
        request = runtime.calls[0]
        self.assertEqual(request['modelId'], 'global.amazon.nova-2-lite-v1:0')
        self.assertEqual(request['system'], [{'text': PROMPT}])
        self.assertEqual(request['toolConfig']['toolChoice'], {'tool': {'name': 'simpan_invoice'}})
        self.assertEqual([tool['toolSpec']['name'] for tool in request['toolConfig']['tools']], ['simpan_invoice'])
        schema = request['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json']
        self.assertEqual(schema, bedrock_schema())
        self.assertEqual(set(schema), {'type', 'properties', 'required'})
        self.assertNotIn('additionalProperties', json.dumps(schema))
        self.assertNotIn('vendor_id', json.dumps(schema))
        self.assertEqual(request['inferenceConfig'], {'maxTokens': 4096, 'temperature': 0})

    def test_bad_input_rejected_before_any_reservation(self):
        log = ledger()
        bedrock, runtime = client(log=log)
        png = io.BytesIO()
        Image.new('RGB', (10, 10)).save(png, 'PNG')
        cases = ((b'not a pdf', 'application/pdf'), (b'%PDF-' + b'x' * 5_000_000, 'application/pdf'),
                 (b'%PDF-demo', 'application/pdf'), (pdf_bytes(6), 'application/pdf'),
                 (png.getvalue(), 'image/jpeg'), (b'\xff\xd8\xffgarbage', 'image/jpeg'),
                 (pdf_bytes(1), 'image/gif'))
        for data, media_type in cases:
            with self.subTest(media_type=media_type, size=len(data)), self.assertRaises(BedrockError) as caught:
                bedrock.extract_document(data, media_type, 'bad')
            self.assertEqual(caught.exception.reason, 'invalid_input')
        self.assertEqual(runtime.calls, [])
        self.assertEqual(log.snapshot()['attempt_count'], 0)


class LedgerTests(unittest.TestCase):
    def test_success_finishes_ledger_with_usage_and_cost(self):
        log = ledger()
        bedrock, _ = client(converse(), log=log)
        trace = bedrock.extract_pdf(pdf_bytes(1), 'ok')
        [(run_id, state, usage, cost)] = rows(log)
        self.assertEqual((trace['run_id'], state, cost), (run_id, 'COMPLETED', '0.00415624'))
        self.assertEqual(json.loads(usage), {'input_tokens': 2728, 'output_tokens': 1184})
        self.assertEqual(log.snapshot()['reserved_authorization_usd'], '0.05')
        self.assertEqual(trace['usage'], {'input_tokens': 2728, 'output_tokens': 1184})
        self.assertEqual((trace['provider'], trace['attempts'], trace['cost_upper_estimate_usd']),
                         ('bedrock', 1, '0.00415624'))
        self.assertEqual((trace['prompt_version'], len(trace['prompt_sha256'])), ('amiga-doc-extract.v3', 64))
        self.assertEqual((trace['requested_model'], trace['returned_model'], trace['stop_reason']),
                         ('global.amazon.nova-2-lite-v1:0', None, 'tool_use'))
        self.assertIsNone(trace['payload']['invoice']['vendor_id'])
        text = json.dumps(trace)  # bytes (page images) would make this fail
        self.assertNotIn('HTTPHeaders', text)
        self.assertEqual(trace['response']['ResponseMetadata']['RequestId'], 'req-test')

    def test_access_denied_is_one_http_error_and_next_call_allowed(self):
        log = ledger()
        bedrock, runtime = client(access_denied(), converse(), log=log)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'denied')
        self.assertEqual(caught.exception.reason, 'access_denied')
        self.assertIn('access denied', str(caught.exception))
        self.assertNotIn('123456789012', str(caught.exception))
        self.assertEqual(log.snapshot()['states'], ['HTTP_ERROR'])
        bedrock.extract_pdf(pdf_bytes(1), 'after-denied')
        self.assertEqual(log.snapshot()['states'], ['HTTP_ERROR', 'COMPLETED'])
        self.assertEqual(len(runtime.calls), 2)

    def test_timeout_is_http_error_not_a_block(self):
        log = ledger()
        timeout = ReadTimeoutError(endpoint_url='https://bedrock-runtime.ap-southeast-1.amazonaws.com')
        bedrock, runtime = client(timeout, converse(), log=log)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'timeout')
        self.assertEqual(caught.exception.reason, 'timeout')
        self.assertEqual(log.snapshot()['states'], ['HTTP_ERROR'])
        self.assertTrue(bedrock.preflight()['ledger_ready'])
        bedrock.extract_pdf(pdf_bytes(1), 'after-timeout')
        self.assertEqual(log.snapshot()['states'], ['HTTP_ERROR', 'COMPLETED'])
        self.assertEqual(len(runtime.calls), 2)

    def test_throttling_has_its_own_reason(self):
        throttled = ClientError({'Error': {'Code': 'ThrottlingException', 'Message': 'slow down'}}, 'Converse')
        bedrock, _ = client(throttled)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'throttled')
        self.assertEqual(caught.exception.reason, 'throttled')

    def test_invalid_output_retried_once_then_rejected(self):
        log = ledger()
        bedrock, runtime = client(converse({'invoice': {}, 'evidence': 'x'}), converse(missing_tool=True), log=log)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'invalid')
        self.assertEqual(caught.exception.reason, 'invalid_output')
        self.assertEqual(len(runtime.calls), 2)
        self.assertEqual(log.snapshot()['states'], ['COMPLETED', 'COMPLETED'])
        self.assertEqual(log.snapshot()['reserved_authorization_usd'], '0.1')

    def test_missing_tool_call_then_valid_answer_is_accepted(self):
        log = ledger()
        bedrock, _ = client(converse(missing_tool=True), converse(), log=log)
        trace = bedrock.extract_pdf(pdf_bytes(1), 'second-try')
        self.assertEqual(trace['attempts'], 2)
        self.assertEqual([run['outcome'] for run in trace['attempt_runs']], ['INVALID_OUTPUT', 'ACCEPTED'])
        self.assertEqual(trace['run_id'], rows(log)[1][0])
        self.assertEqual(trace['cost_upper_estimate_usd'], '0.00831248')
        self.assertEqual(trace['usage'], {'input_tokens': 5456, 'output_tokens': 2368})

    def test_cost_above_reservation_blocks_further_calls(self):
        log = ledger()
        bedrock, runtime = client(converse(usage=(200_000, 4096)), converse(), log=log)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'expensive')
        self.assertEqual(caught.exception.reason, 'budget')
        self.assertEqual(log.snapshot()['states'], ['COST_BREACH'])
        with self.assertRaises(BudgetError):
            bedrock.extract_pdf(pdf_bytes(1), 'blocked')
        with self.assertRaises(BudgetError):
            bedrock.preflight()
        self.assertEqual(len(runtime.calls), 1)

    def test_missing_usage_is_unverified_billing(self):
        log = ledger()
        bedrock, _ = client(converse(drop=('usage',)), log=log)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'no-usage')
        self.assertEqual(caught.exception.reason, 'budget')
        self.assertEqual(log.snapshot()['states'], ['COST_BREACH'])

    def test_unknown_exception_is_uncertain_and_blocks(self):
        log = ledger()
        bedrock, _ = client(RuntimeError('boom'), log=log)
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'unknown')
        self.assertEqual(caught.exception.reason, 'uncertain')
        self.assertEqual(log.snapshot()['states'], ['UNCERTAIN'])
        with self.assertRaises(BudgetError):
            bedrock.preflight()

    def test_missing_ledger_fails_closed(self):
        absent = BudgetLedger(ROOT / ('absent-' + str(uuid4()) + '.sqlite3'), Decimal('2.00'), RESERVATION_MICRO_USD)
        bedrock, runtime = client(converse(), log=absent)
        with self.assertRaises(BudgetError):
            bedrock.preflight()
        with self.assertRaises(BudgetError):
            bedrock.extract_pdf(pdf_bytes(1), 'no-ledger')
        self.assertEqual(runtime.calls, [])
        self.assertFalse(absent.path.exists())

    def test_reservation_covers_a_botocore_resend_of_the_worst_request(self):
        self.assertLess(2 * worst_case_request_usd(), Decimal(RESERVATION_MICRO_USD) / 1_000_000)
        with self.assertRaises(LiveError):
            BedrockClient(config(), ledger(reservation=10_000), FakeRuntime())

    def test_botocore_resend_is_priced_as_a_worst_case_request(self):
        log = ledger()
        bedrock, _ = client(converse(retries=1), log=log)
        trace = bedrock.extract_pdf(pdf_bytes(1), 'resent')
        self.assertEqual(Decimal(trace['cost_upper_estimate_usd']), Decimal('0.00415624') + worst_case_request_usd())
        self.assertEqual(log.snapshot()['states'], ['COMPLETED'])


class NormalizeTests(unittest.TestCase):
    def test_normalize_returns_metadata_and_document_id(self):
        bedrock, _ = client(converse())
        result = bedrock.normalize(bedrock.extract_pdf(pdf_bytes(1), 'meta'), 'doc_bedrock_001')
        invoice = result['invoice']
        self.assertEqual({key: invoice[key] for key in METADATA}, METADATA)
        self.assertIsNone(invoice['vendor_id'])
        self.assertEqual(invoice['payment']['account_number'], '00123456')
        self.assertEqual(result['source_evidence']['faktur_number']['document_id'], 'doc_bedrock_001')

    def test_zero_based_rows_and_absent_keys_adapted_without_new_values(self):
        payload = tool_payload()
        for index, item in enumerate(payload['invoice']['line_items']):
            item['line_number'] = index
        payload['invoice'].pop('due_date')
        payload['evidence'].append({'field': 'due_date', 'page': 1, 'raw_value': None})
        bedrock, _ = client(converse(payload))
        trace = bedrock.extract_pdf(pdf_bytes(1), 'adapt')
        self.assertEqual(trace['adaptations'], ['line_numbers_zero_based_shifted', 'missing_keys_as_null:due_date',
                                                'blank_evidence_dropped:1'])
        result = bedrock.normalize(trace, 'doc')
        self.assertEqual([item['line_number'] for item in result['invoice']['line_items']], [1, 2, 3])
        self.assertIsNone(result['invoice']['due_date'])
        self.assertNotIn('due_date', result['source_evidence'])

    def test_printed_comma_decimals_convert_but_ambiguous_ones_do_not(self):
        payload = tool_payload()
        payload['invoice'].update({'stated_subtotal': '500.000,00', 'stated_total': '500.000,00',
                                   'stated_discount_total': '0,00'})
        payload['invoice']['line_items'][0]['unit_price'] = '150.000,00'
        bedrock, _ = client(converse(payload))
        trace = bedrock.extract_pdf(pdf_bytes(1), 'comma')
        self.assertEqual(trace['adaptations'], ['comma_decimals_converted:4'])
        invoice = bedrock.normalize(trace, 'doc')['invoice']
        self.assertEqual((invoice['stated_total'], invoice['stated_discount_total'],
                          invoice['line_items'][0]['unit_price']), ('500000.00', '0.00', '150000.00'))
        ambiguous = tool_payload()
        ambiguous['invoice']['line_items'][0]['quantity'] = '1,234'  # English thousands or Indonesian decimal
        bedrock, runtime = client(converse(ambiguous), converse(ambiguous))
        # Since 14 Okt 2026 an uncertain format becomes unread instead of rejecting the whole invoice, so the rules
        # flag that one value for a person (normalize_payload, _coerce_formats).
        trace = bedrock.extract_pdf(pdf_bytes(1), 'ambiguous')
        self.assertIsNone(bedrock.normalize(trace, 'doc')['invoice']['line_items'][0]['quantity'])
        self.assertEqual(len(runtime.calls), 1)

    def test_same_quote_on_two_pages_keeps_first_citation_but_different_quotes_fail(self):
        repeated = tool_payload()
        repeated['evidence'].append({'field': 'vendor_npwp', 'page': 2, 'raw_value': METADATA['vendor_npwp']})
        bedrock, _ = client(converse(repeated))
        trace = bedrock.extract_pdf(pdf_bytes(2), 'repeat')
        self.assertEqual(trace['adaptations'], ['repeated_quote_citations_dropped:1'])
        self.assertEqual(bedrock.normalize(trace, 'doc')['source_evidence']['vendor_npwp']['page'], 1)
        conflict = tool_payload()
        conflict['evidence'].append({'field': 'vendor_npwp', 'page': 2, 'raw_value': '11.111.111.1-111.111'})
        bedrock, _ = client(converse(conflict), converse(conflict))
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(2), 'conflict')
        self.assertIn('conflicting evidence for vendor_npwp', str(caught.exception))
        self.assertNotIn('11.111.111.1-111.111', str(caught.exception))
        self.assertEqual(len(caught.exception.responses), 2)  # kept for a trace store, never in the message
        self.assertEqual([run['outcome'] for run in caught.exception.attempt_runs], ['INVALID_OUTPUT'] * 2)

    def test_model_supplied_vendor_id_is_rejected(self):
        payload = tool_payload()
        payload['invoice']['vendor_id'] = 'vendor_from_model'
        bedrock, runtime = client(converse(payload), converse(payload))
        with self.assertRaises(BedrockError) as caught:
            bedrock.extract_pdf(pdf_bytes(1), 'vendor-id')
        self.assertEqual(caught.exception.reason, 'invalid_output')
        self.assertEqual(len(runtime.calls), 2)


class ConfigTests(unittest.TestCase):
    def test_repr_hides_secrets(self):
        text = repr(config(session_token='sessiontokensecret'))
        for secret in ('TESTACCESSKEY00000002', 'testsecretvalue', 'sessiontokensecret'):
            self.assertNotIn(secret, text)

    def test_wrong_region_unpriced_model_and_cap_rejected(self):
        for overrides in ({'region': 'us-east-1'}, {'model_id': 'apac.amazon.nova-pro-v1:0'},
                          {'stop_usd': Decimal('9')}, {'stop_usd': Decimal('0')}):
            with self.subTest(**{key: str(value) for key, value in overrides.items()}), self.assertRaises(LiveError):
                config(**overrides)
        base = {'AWS_ACCESS_KEY_ID': 'TESTACCESSKEY00000002', 'AWS_SECRET_ACCESS_KEY': 'testsecretvalue'}
        for extra in ({'AWS_REGION': 'us-east-1'}, {'AWS_ACCESS_KEY': 'TESTACCESSKEY00000001'},
                      {'AWS_SECRET_ACCESS_KEY': ''}, {'AMIGA_BEDROCK_STOP_USD': 'lots'}):
            with self.subTest(extra=sorted(extra)), self.assertRaises(LiveError) as caught:
                BedrockConfig.from_values(base | extra)
            self.assertNotIn('testsecretvalue', str(caught.exception))
            self.assertNotIn('AKIA', str(caught.exception))

    def test_values_alias_defaults_and_overrides(self):
        loaded = BedrockConfig.from_values({'AWS_ACCESS_KEY': 'TESTACCESSKEY00000002',
                                            'AWS_SECRET_ACCESS_KEY': 'testsecretvalue', 'AWS_SESSION_TOKEN': ''})
        self.assertEqual((loaded.access_key_id, loaded.session_token, loaded.model_id, loaded.stop_usd, loaded.region),
                         ('TESTACCESSKEY00000002', None, 'global.amazon.nova-2-lite-v1:0', Decimal('2.00'),
                          'ap-southeast-1'))
        custom = BedrockConfig.from_values({'AWS_ACCESS_KEY_ID': 'TESTACCESSKEY00000002',
                                            'AWS_SECRET_ACCESS_KEY': 'testsecretvalue', 'AWS_REGION': 'ap-southeast-1',
                                            'AMIGA_BEDROCK_MODEL_ID': 'apac.amazon.nova-2-lite-v1:0',
                                            'AMIGA_BEDROCK_STOP_USD': '1.50'})
        self.assertEqual((custom.model_id, custom.stop_usd), ('apac.amazon.nova-2-lite-v1:0', Decimal('1.50')))

    def test_load_reads_only_the_given_dotenv_file(self):
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        path = RUNTIME_DIR / (str(uuid4()) + '-dotenv.txt')
        path.write_text('# fake test values\nAWS_ACCESS_KEY_ID=TESTACCESSKEY00000002\n'
                        'AWS_SECRET_ACCESS_KEY="testsecretvalue"\nAMIGA_BEDROCK_STOP_USD=1.00\n', encoding='utf-8')
        self.assertEqual(BedrockConfig.load(path).stop_usd, Decimal('1.00'))
        with self.assertRaises(LiveError):
            BedrockConfig.load(RUNTIME_DIR / 'absent-dotenv.txt')

    def test_preflight_makes_no_call(self):
        bedrock, runtime = client()
        result = bedrock.preflight()
        self.assertEqual((result['network_calls'], result['remaining_calls'], result['region']),
                         (0, 40, 'ap-southeast-1'))
        self.assertEqual(runtime.calls, [])

    def test_default_runtime_is_regional_with_bounded_timeouts_and_retries(self):
        runtime = BedrockClient(config(), ledger()).runtime  # building a client sends nothing
        self.assertEqual(runtime.meta.service_model.service_name, 'bedrock-runtime')
        self.assertEqual(runtime.meta.region_name, 'ap-southeast-1')
        self.assertEqual((runtime.meta.config.read_timeout, runtime.meta.config.connect_timeout), (60, 10))
        # One request and no botocore resend: a failure goes to the logged fallback instead of a hidden retry.
        self.assertEqual(runtime.meta.config.retries, {'mode': 'standard', 'total_max_attempts': 1})

    def test_default_runtime_sends_a_failing_request_only_once(self):
        # A silent resend doubled the wall time past the 15 s brief target (18 s and 29 s on 14 Oct).
        from botocore.awsrequest import AWSResponse

        class Busy:
            def stream(self, **_):
                yield b'{"message":"busy"}'

        runtime, sent = BedrockClient(config(), ledger()).runtime, []

        def answer_busy(request, **_):
            sent.append(request.url)
            return AWSResponse(request.url, 503, {}, Busy())

        runtime.meta.events.register('before-send.bedrock-runtime.Converse', answer_busy)
        with self.assertRaises(ClientError):
            runtime.converse(modelId='global.amazon.nova-2-lite-v1:0',
                             messages=[{'role': 'user', 'content': [{'text': 'ping'}]}])
        self.assertEqual(len(sent), 1)


if __name__ == '__main__':
    unittest.main()
