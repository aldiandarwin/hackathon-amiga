"""Stage 6: originals in the database, photos, tax identity read from the document, Bedrock with OpenAI fallback.

No network: readers are fakes shaped like BedrockClient and OpenAIClient. Each test uses its own schema.
"""

from decimal import Decimal
import hashlib
from io import BytesIO
import json
import unittest
from uuid import uuid4

from pypdf import PdfReader
from psycopg.types.json import Jsonb

from app.settings import ROOT
from app.tests import test_app as fixtures
from amiga_ocr.openai_live import LiveError, normalize_payload

DEMO = ROOT / 'output/pdf/demo-final'
MANIFEST = {entry.get('file') or entry['pdf']: entry
            for entry in json.loads((DEMO / 'manifest.json').read_text(encoding='utf-8'))}
PIC = {'id': 'pic_a', 'role': 'PIC', 'clients': [{'id': 'client_a', 'name': 'Arunika Sejahtera'}]}
PPN_PPH23 = {'pph': 'PPH23', 'ppn': True, 'recipient_has_npwp': True, 'faktur_number': None}


def printed(value):
    """Amounts as the demo invoices print them: 4.000.000,00."""
    whole, cents = f'{Decimal(value):.2f}'.split('.')
    return f'{int(whole):,}'.replace(',', '.') + ',' + cents


def payload_for(name, **changes):
    """The {invoice, evidence} a perfect reader returns for a demo file, quoting the printed text."""
    invoice = json.loads(json.dumps(MANIFEST['output/pdf/demo-final/' + name]['expected_invoice'])) | changes
    invoice = {'vendor_id': None, **invoice}
    evidence = []
    for key, value in invoice.items():
        if value is None or key in ('vendor_id', 'line_items', 'payment'):
            continue
        page = 2 if key.startswith('faktur_') else 1
        evidence.append({'field': key, 'page': page, 'raw_value': printed(value) if key.startswith('stated_') else value})
    for key, value in invoice['payment'].items():
        evidence.append({'field': 'payment.' + key, 'page': 1, 'raw_value': value})
    for index, item in enumerate(invoice['line_items']):
        item['line_number'] = index + 1
        for key in ('description', 'quantity', 'unit_price', 'stated_line_total'):
            raw = printed(item[key]) if key in ('unit_price', 'stated_line_total') else item[key]
            evidence.append({'field': f'line_items[{index}].{key}', 'page': 1, 'raw_value': raw})
    return {'invoice': invoice, 'evidence': evidence}


class Reader:
    """Shaped like BedrockClient: extract_document plus normalize."""
    provider, model = 'bedrock', 'fake-nova-2-lite'

    def __init__(self, payload=None, error=None, calls=None):
        self.payload, self.error, self.calls = payload, error, calls if calls is not None else []

    def preflight(self):
        return {}

    def extract_document(self, data, media_type, case_id):
        self.calls.append((self.provider, media_type))
        if self.error:
            raise self.error
        return {'provider': self.provider, 'run_id': str(uuid4()), 'duration_ms': 7, 'cost_upper_estimate_usd': '0.0042',
                'usage': {'input_tokens': 2728, 'output_tokens': 1184}, 'prompt_version': 'TEST_NO_NETWORK',
                'returned_model': self.model, 'payload': self.payload, 'response': {'stopReason': 'tool_use'}}

    def normalize(self, trace, document_id):
        return normalize_payload(trace['payload'], document_id)


class Fallback(Reader):
    provider, model = 'openai', 'fake-gpt'


class StorageTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    detail = fixtures.DatabaseAcceptanceTests.detail
    edit = fixtures.DatabaseAcceptanceTests.edit
    pic_submit = fixtures.DatabaseAcceptanceTests.pic_submit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def use(self, primary, *fallbacks):
        service = self.api.state.service
        service.live_client_factory, service.fallback_factories = (lambda: primary), [lambda f=f: f for f in fallbacks]

    def intake(self, name, selection=PPN_PPH23):
        data = (DEMO / name).read_bytes()
        identifier, created = self.api.state.service.intake(data, PIC, 'client_a', name, str(uuid4()), tax_selection=selection)
        self.assertTrue(created)
        self.assertTrue(self.api.state.service.process_next())
        return identifier, data

    def runs(self, identifier):
        with self.api.state.db.transaction() as conn:
            return conn.execute('SELECT provider,status,fallback_from,input_tokens FROM extraction_runs '
                                'WHERE request_id=%s ORDER BY id', (identifier,)).fetchall()

    def codes(self, detail):
        return {c['code']: c for c in detail['draft']['validation']['checks']}

    def test_pdf_with_faktur_page_fills_tax_identity_without_typing(self):
        self.use(Reader(payload_for('inv-demo-005.pdf')))
        identifier, data = self.intake('inv-demo-005.pdf')
        detail = self.detail(identifier)
        self.assertEqual(detail['status'], 'READY_FOR_REVIEW', [c for c in detail['draft']['validation']['checks']
                                                                if c['blocking'] and c['status'] != 'PASSED'])
        self.assertEqual(detail['draft']['invoice']['faktur_number'], '010.000-26.00000005')
        self.assertEqual((detail['draft']['tax']['faktur_number'], detail['draft']['tax']['faktur_source']),
                         ('010.000-26.00000005', 'DOKUMEN'))
        checks = self.codes(detail)
        self.assertEqual(checks['NPWP_MATCH']['status'], 'PASSED')
        self.assertNotIn('TAX_FAKTUR_NOT_FOUND', checks)
        self.assertEqual(checks['SOURCE_EVIDENCE_MATCH']['status'], 'PASSED')
        self.assertEqual(detail['draft']['source']['provider'], 'bedrock')
        self.assertTrue(detail['original_file']['verified'])
        self.assertEqual([dict(r) for r in self.runs(identifier)],
                         [{'provider': 'bedrock', 'status': 'COMPLETED', 'fallback_from': None, 'input_tokens': 2728}])
        self.login('pic@amiga.local')
        self.pic_submit(identifier)
        self.login('finance@amiga.local')
        response = self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': 1, 'source_reviewed': True, 'reason': 'Faktur dan invoice sintetis sudah dicocokkan',
            'password': 'test-password-only', 'consent': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.api.state.review.process_next())
        voucher = self.client.get(f'/api/v1/requests/{identifier}/voucher?version=1')
        self.assertEqual(voucher.status_code, 200, voucher.text)
        text = ' '.join(page.extract_text() for page in PdfReader(BytesIO(voucher.content)).pages)
        self.assertIn(detail['draft']['tax']['faktur_number'], ' '.join(text.split()))

    def test_wrong_npwp_and_missing_faktur_hold_approval(self):
        self.use(Reader(payload_for('inv-demo-007.pdf', faktur_number=None, faktur_date=None)))
        identifier, _ = self.intake('inv-demo-007.pdf')
        checks = self.codes(self.detail(identifier))
        self.assertEqual(checks['TAX_FAKTUR_NOT_FOUND']['status'], 'FAILED')
        self.assertTrue(checks['TAX_FAKTUR_NOT_FOUND']['blocking'])
        with self.api.state.db.transaction() as conn:
            conn.execute("UPDATE vendors SET npwp=%s WHERE client_id='client_a'", ('01.234.567.8-999.000',))
        self.use(Reader(payload_for('inv-demo-005.pdf')))
        other, _ = self.intake('inv-demo-005.pdf')
        detail = self.detail(other)
        self.assertEqual(self.codes(detail)['NPWP_MISMATCH']['status'], 'FAILED')
        self.assertEqual(detail['status'], 'EXCEPTION')

    def test_photo_upload_is_kept_in_database_and_previewed(self):
        self.login('pic@amiga.local')
        data = (DEMO / 'inv-demo-006.jpg').read_bytes()
        calls = []
        self.use(Reader(payload_for('inv-demo-006.jpg'), calls=calls))
        response = self.client.post('/api/v1/requests?client_id=client_a&filename=foto-invoice.jpg', content=data,
                                    headers={'Content-Type': 'image/jpeg', 'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 202, response.text)
        identifier = response.json()['request_id']
        self.assertTrue(self.api.state.service.process_next())
        self.assertEqual(calls, [('bedrock', 'image/jpeg')])
        detail = self.detail(identifier)
        self.assertEqual((detail['media_type'], detail['page_count']), ('image/jpeg', 1))
        self.assertEqual(detail['original_file'], {'media_type': 'image/jpeg', 'byte_size': len(data), 'verified': True,
                                                   'stored_in_database': True})
        # A photo has no text layer, so a person still compares the values with the image, like a scanned PDF.
        self.assertIn('VISUAL_REVIEW_REQUIRED', self.codes(detail))
        self.assertEqual(detail['draft']['invoice']['vendor_npwp'], '99.123.456.7-012.000')
        document = self.client.get(f'/api/v1/requests/{identifier}/document')
        self.assertEqual((document.headers['content-type'], document.content), ('image/jpeg', data))
        preview = self.client.get(f'/api/v1/requests/{identifier}/preview/1')
        self.assertEqual((preview.status_code, preview.content[:8]), (200, b'\x89PNG\r\n\x1a\n'))
        png = (DEMO / 'inv-demo-008.png').read_bytes()
        renamed = self.client.post('/api/v1/requests?client_id=client_a&filename=bukan-pdf.pdf', content=png,
                                   headers={'Content-Type': 'image/png', 'Idempotency-Key': str(uuid4())})
        self.assertEqual((renamed.status_code, renamed.json()['code']), (422, 'INVALID_FILENAME'))

    def test_bedrock_failure_falls_back_to_openai_and_both_runs_are_kept(self):
        self.use(Reader(error=LiveError('Bedrock timeout')), Fallback(payload_for('inv-demo-005.pdf')))
        identifier, _ = self.intake('inv-demo-005.pdf')
        source = self.detail(identifier)['draft']['source']
        self.assertEqual((source['provider'], source['fallback_from'], source['live_calls']), ('openai', 'bedrock', 2))
        self.assertEqual([(r['provider'], r['status'], r['fallback_from']) for r in self.runs(identifier)],
                         [('bedrock', 'FAILED', None), ('openai', 'COMPLETED', 'bedrock')])

    def test_corrected_field_shows_original_value(self):
        self.use(Reader(payload_for('inv-demo-005.pdf')))
        identifier, _ = self.intake('inv-demo-005.pdf')
        invoice = self.detail(identifier)['draft']['invoice']
        invoice['po_number'] = 'PO-ARS-2026-999'
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        detail = self.detail(identifier)
        self.assertEqual(detail['original_values'], {'po_number': 'PO-ARS-2026-005'})
        self.assertEqual(detail['draft']['invoice']['po_number'], 'PO-ARS-2026-999')

    def test_backfill_copies_older_files_only_when_hash_matches(self):
        service = self.api.state.service
        good, bad = b'%PDF-1.4 older upload', b'%PDF-1.4 changed on disk'
        with self.api.state.db.transaction() as conn:
            for name, data, digest in (('lama.pdf', good, hashlib.sha256(good).hexdigest()),
                                       ('berubah.pdf', bad, '0' * 64)):
                identifier = str(uuid4())
                conn.execute('INSERT INTO requests(id,client_id,uploaded_by,filename,document_key,pdf_sha256,page_count,pages,'
                             "mode,status,idempotency_key) VALUES (%s,'client_a','pic_a',%s,%s,%s,1,%s,'OPENAI','EXCEPTION',%s)",
                             (identifier, name, identifier + '.pdf', digest, Jsonb(['']), str(uuid4())))
                service.document_path(identifier + '.pdf').write_bytes(data)
        self.assertEqual(service.backfill_files(), (1, 1))
        self.assertEqual(service.backfill_files(), (0, 1))

    def test_dashboard_origin_may_write_with_csrf(self):
        for origin, status in (('http://127.0.0.1:3000', 200), ('http://localhost:3000', 200), ('http://127.0.0.1:4000', 403)):
            with self.subTest(origin=origin):
                response = self.client.post('/api/v1/login', headers={'Origin': origin},
                                            json={'email': 'pic@amiga.local', 'password': 'test-password-only'})
                self.assertEqual(response.status_code, status)


if __name__ == '__main__':
    unittest.main()
