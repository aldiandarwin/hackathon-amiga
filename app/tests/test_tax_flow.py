"""Tax selection from intake to voucher, against PostgreSQL, with no real provider calls."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import unittest
from uuid import uuid4

from pypdf import PdfReader

from app import taxes
from app.review import voucher_number
from app.service import AppError, sample_input
from app.settings import ROOT
from app.tests import test_app as fixtures
from app.tests import test_batches as batch_fixtures
from app.tests.test_taxes import pick
from app.voucher_pdf import TEMPLATE_VERSION, render_voucher, terbilang

# Recorded from the unchanged amiga-demo-v1 renderer on 2026-10-13; pending v1 vouchers must re-render identically.
V1_GOLDEN_SHA256 = '56037f29a74454489e4b4ec0e37559909f981ff85a114d5d5b590135a356b6a9'
# Recorded from the unchanged v2 and v3 renderers on 2026-10-14, before amiga-demo-v4 existed.
V2_GOLDEN_SHA256 = 'd78fd4f37d37d785a67535534ab0f07a7c4a032a2d8dfee3e9338b6956c34298'
V3_GOLDEN_SHA256 = '76344349aa93a8f7a143fda90655e0cb1046e7373432f4ca518de87bc832dcf0'
REVIEWER_SIGNATURE = {'id': 'finance_a', 'name': 'Dian Pratama', 'title': 'Finance Reviewer AMIGA',
                      'signed_at': '2026-10-13T10:00:00+00:00', 'code': 'ABCD2345'}
SIGNOFF = {'verify_url': 'http://127.0.0.1:8787/verifikasi/11111111-1111-1111-1111-111111111111',
           'content_sha256': 'a' * 64,
           'director': {'name': 'Bagas Wiratama', 'title': 'Direktur Utama AMIGA',
                        'signed_at': '2026-10-13T11:30:00+00:00', 'code': 'WXYZ6789'}}


def v1_payload():
    invoice = json.loads((ROOT / 'app/sample-results.json').read_text(encoding='utf-8'))['normal']['invoice']
    return {'number': 'DEMO-A-2026-000001', 'template_version': 'amiga-demo-v1',
            'request_id': '00000000-0000-0000-0000-000000000001', 'invoice_version': 1, 'invoice': invoice,
            'client': {'id': 'client_a', 'name': 'Klien A'}, 'uploader': {'id': 'pic_a', 'name': 'Nadia Putri'},
            'reviewer': {'id': 'finance_a', 'name': 'Dian Pratama'}, 'approved_at': '2026-10-13T10:00:00+00:00',
            'review_note': 'Golden voucher v1',
            'source_review': {'confirmed': True, 'reviewed_checks': [],
                              'statement': 'Reviewer mencocokkan seluruh field dan halaman dokumen asli.'},
            'source_document_sha256': '0' * 64, 'source_mode': 'REPLAY'}


def v2_payload(invoice_changes=None, selection=None):
    payload = v1_payload()
    payload['invoice'].update(invoice_changes or {})
    selection = selection or pick('PPH21')
    tax, _ = taxes.compute(payload['invoice'], selection)
    return payload | {'template_version': 'amiga-demo-v2', 'tax_selection': selection, 'tax': tax}


def v4_payload():
    selection = pick('PPH23', ppn=True, faktur='0400250012345678')
    payload = v2_payload({'stated_tax_total': '55000.00', 'stated_total': '555000.00',
                          'vendor_npwp': '99.123.456.7-012.000', 'po_number': 'PO-ARS-0042', 'due_date': '2026-10-30'},
                         selection)
    return payload | {'template_version': 'amiga-demo-v4', 'number': 'ARS-00001-10-2026',
                      'assigned_director': {'name': 'Bagas Wiratama', 'title': 'Direktur Utama AMIGA'},
                      'signatures': {'reviewer': REVIEWER_SIGNATURE}}


def pdf_text(data):
    reader = PdfReader(BytesIO(data))
    return len(reader.pages), ' '.join(' '.join(page.extract_text() for page in reader.pages).split())


def pdf_images(data):
    return sum(len(page.images) for page in PdfReader(BytesIO(data)).pages)


def with_lines(payload, count, note):
    payload = deepcopy(payload)
    payload['invoice']['line_items'] = [{'line_number': i + 1, 'description': f'Barang contoh {i + 1}', 'quantity': '1',
                                         'unit_price': '100000.00', 'stated_line_total': '100000.00'} for i in range(count)]
    payload['review_note'] = note
    return payload


class TerbilangTests(unittest.TestCase):
    def test_amounts_in_words(self):
        cases = {'0': 'Nol rupiah', '11': 'Sebelas rupiah', '100': 'Seratus rupiah', '1000': 'Seribu rupiah',
                 '545000.00': 'Lima ratus empat puluh lima ribu rupiah',
                 '1250000': 'Satu juta dua ratus lima puluh ribu rupiah',
                 '4360000.00': 'Empat juta tiga ratus enam puluh ribu rupiah', '1000000000': 'Satu miliar rupiah',
                 '1500000.50': 'Satu juta lima ratus ribu rupiah lima puluh sen'}
        for amount, words in cases.items():
            with self.subTest(amount=amount):
                self.assertEqual(terbilang(amount), words)

    def test_voucher_number_follows_amiga_running_number_month_year_in_wib(self):
        self.assertEqual(voucher_number('client_a', 2, datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)),
                         'ARS-00002-10-2026')
        self.assertEqual(voucher_number('client_b', 17, datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)),
                         'BMP-00017-10-2026')
        # 20:00 UTC on 31 October is already 1 November in Jakarta.
        self.assertEqual(voucher_number('client_a', 3, datetime(2026, 10, 31, 20, 0, tzinfo=timezone.utc)),
                         'ARS-00003-11-2026')


class VoucherTemplateTests(unittest.TestCase):
    def test_v1_renders_byte_identical(self):
        self.assertEqual(hashlib.sha256(render_voucher(v1_payload())).hexdigest(), V1_GOLDEN_SHA256)

    def test_v2_and_v3_render_byte_identical(self):
        self.assertEqual(hashlib.sha256(render_voucher(v2_payload())).hexdigest(), V2_GOLDEN_SHA256)
        v3 = v2_payload() | {'template_version': 'amiga-demo-v3'}
        self.assertEqual(hashlib.sha256(render_voucher(v3)).hexdigest(), V3_GOLDEN_SHA256)

    def test_new_approvals_use_v8(self):
        self.assertEqual(TEMPLATE_VERSION, 'amiga-demo-v8')

    def test_v4_draft_waits_for_the_director(self):
        pages, text = pdf_text(render_voucher(v4_payload()))
        self.assertEqual(pages, 1)
        for expected in ('VOUCHER PENGELUARAN', 'DRAF', 'ARS-00001-10-2026', 'Terbilang',
                         'Lima ratus empat puluh lima ribu rupiah', 'Dibayarkan kepada', '99.123.456.7-012.000',
                         'Bank Contoh', '00123456', 'PO-ARS-0042', 'Jatuh tempo', '2 x IDR 150.000,00', 'Diajukan Oleh',
                         'Dian Pratama', 'Ditandatangani secara elektronik', 'ABCD2345', 'Disetujui Oleh',
                         'Bagas Wiratama', 'Menunggu tanda tangan', 'BATAS OTORISASI', 'di luar aplikasi',
                         'amiga-demo-v4'):
            self.assertIn(expected, text)
        self.assertNotIn('WXYZ6789', text)
        self.assertNotIn('/verifikasi/', text)

    def test_v4_draft_does_not_claim_the_bod_approval_yet(self):
        # The draft is what scenario 1 downloads; it must not say the BOD approved before the BOD signs.
        _, draft = pdf_text(render_voucher(v4_payload()))
        _, final = pdf_text(render_voucher(v4_payload(), SIGNOFF))
        self.assertNotIn('disetujui Direksi AMIGA', draft)
        self.assertIn('menunggu persetujuan Direksi AMIGA', draft)
        self.assertIn('disetujui Direksi AMIGA', final)
        for text in (draft, final):
            self.assertIn('di luar aplikasi', text)  # brief p8: the authorization limits stay on both copies

    def test_v4_stamps_a_specimen_only_in_signed_boxes(self):
        from app.specimen import synthetic_specimen
        reviewer_png, director_png = synthetic_specimen('Dian Pratama'), synthetic_specimen('Bagas Wiratama')
        specimens = {hashlib.sha256(png).hexdigest(): png for png in (reviewer_png, director_png)}
        payload, signoff = deepcopy(v4_payload()), deepcopy(SIGNOFF)
        payload['signatures']['reviewer']['specimen_sha256'] = hashlib.sha256(reviewer_png).hexdigest()
        signoff['director']['specimen_sha256'] = hashlib.sha256(director_png).hexdigest()
        self.assertEqual(pdf_images(render_voucher(v4_payload())), 0)  # no specimen: text-only boxes as before
        self.assertEqual(pdf_images(render_voucher(payload, specimens=specimens)), 1)  # draft: the BOD still waits
        self.assertEqual(pdf_images(render_voucher(payload, signoff, specimens=specimens)), 2)
        self.assertEqual(render_voucher(payload, signoff, specimens=specimens),
                         render_voucher(payload, signoff, specimens=specimens))

    def test_v4_final_prints_both_signatures_and_the_verification_link(self):
        pages, text = pdf_text(render_voucher(v4_payload(), SIGNOFF))
        self.assertEqual(pages, 1)
        for expected in ('FINAL', 'ABCD2345', 'WXYZ6789', 'Bagas Wiratama', '11111111-1111-1111-1111-111111111111'):
            self.assertIn(expected, text)
        self.assertNotIn('Menunggu tanda tangan', text)

    def test_v4_renders_deterministically(self):
        self.assertEqual(render_voucher(v4_payload()), render_voucher(v4_payload()))
        self.assertEqual(render_voucher(v4_payload(), SIGNOFF), render_voucher(v4_payload(), SIGNOFF))

    def test_v4_final_stays_on_one_page_up_to_six_lines(self):
        for count in range(1, 7):
            with self.subTest(lines=count):
                pages, _ = pdf_text(render_voucher(with_lines(v4_payload(), count, 'Dokumen diperiksa.'), SIGNOFF))
                self.assertEqual(pages, 1)

    def test_older_templates_refuse_a_signoff(self):
        with self.assertRaises(ValueError):
            render_voucher(v2_payload() | {'template_version': 'amiga-demo-v3'}, SIGNOFF)

    def test_v3_follows_amiga_voucher_pengeluaran(self):
        selection = pick('PPH23', ppn=True, faktur='0400250012345678')
        payload = v2_payload({'stated_tax_total': '55000.00', 'stated_total': '555000.00'}, selection)
        pages, text = pdf_text(render_voucher(payload | {'template_version': 'amiga-demo-v3'}))
        self.assertEqual(pages, 1)
        for expected in ('VOUCHER PENGELUARAN', 'Peruntukan', 'Tanggal/Periode', 'Nominal', 'KETERANGAN', 'PPN (faktur',
                         'Potongan PPh 23', 'TOTAL IDR 545.000,00', 'Diajukan Oleh', 'Disetujui Oleh', 'Client Approver',
                         'BATAS OTORISASI', 'amiga-demo-v3'):
            self.assertIn(expected, text)

    def test_v3_needs_no_more_pages_than_v1(self):
        for note_length in (17, 190, 500):
            note = ('Dokumen diperiksa. ' * 40)[:note_length]
            for count in range(1, 9):
                with self.subTest(note=note_length, lines=count):
                    pages_v1, _ = pdf_text(render_voucher(with_lines(v1_payload(), count, note)))
                    v3 = with_lines(v2_payload(), count, note) | {'template_version': 'amiga-demo-v3'}
                    self.assertLessEqual(pdf_text(render_voucher(v3))[0], pages_v1)

    def test_v3_refuses_an_uncomputed_tax_block_and_v2_keeps_its_layout(self):
        payload = v2_payload() | {'template_version': 'amiga-demo-v3'}
        payload['tax'] = taxes.compute(payload['invoice'], None)[0]
        with self.assertRaises(ValueError):
            render_voucher(payload)
        self.assertIn('Voucher review invoice', pdf_text(render_voucher(v2_payload()))[1])

    def test_v2_prints_the_tax_lines_on_one_page(self):
        pages, text = pdf_text(render_voucher(v2_payload()))
        self.assertEqual(pages, 1)
        for expected in ('JUMLAH DIBAYARKAN', 'Potongan PPh 21', '12.500', '487.500', 'dasar PPh', 'pajak-poc.v2', 'Asumsi PoC'):
            self.assertIn(expected, text)

    def test_v2_notes_declared_zero_and_manual_faktur(self):
        _, text = pdf_text(render_voucher(v2_payload({'stated_tax_total': None})))
        self.assertIn('dihitung 0', text)
        selection = pick('PPH23', ppn=True, faktur='0400250012345678')
        pages, text = pdf_text(render_voucher(v2_payload({'stated_tax_total': '55000.00', 'stated_total': '555000.00'}, selection)))
        self.assertEqual(pages, 1)
        self.assertIn('0400250012345678', text)
        self.assertIn('input manual', text)
        self.assertIn('545.000', text)

    def test_v2_needs_no_more_pages_than_v1(self):
        for note_length in (17, 190, 500):
            note = ('Dokumen diperiksa. ' * 40)[:note_length]
            for count in range(1, 9):
                with self.subTest(note=note_length, lines=count):
                    pages_v1, _ = pdf_text(render_voucher(with_lines(v1_payload(), count, note)))
                    pages_v2, _ = pdf_text(render_voucher(with_lines(v2_payload(), count, note)))
                    self.assertLessEqual(pages_v2, pages_v1)

    def test_v2_refuses_an_uncomputed_tax_block(self):
        payload = v2_payload()
        payload['tax'] = taxes.compute(payload['invoice'], None)[0]
        with self.assertRaises(ValueError):
            render_voucher(payload)

    def test_unknown_template_is_still_refused(self):
        with self.assertRaises(ValueError):
            render_voucher(v1_payload() | {'template_version': 'amiga-demo-v9'})


class TaxFlowTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    sample = fixtures.DatabaseAcceptanceTests.sample
    detail = fixtures.DatabaseAcceptanceTests.detail
    edit = fixtures.DatabaseAcceptanceTests.edit
    pic_submit = fixtures.DatabaseAcceptanceTests.pic_submit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)
    install_fake = batch_fixtures.BatchAcceptanceTests.install_fake
    descriptor = staticmethod(batch_fixtures.BatchAcceptanceTests.descriptor)

    def user(self):
        return self.client.get('/api/v1/session').json()

    def audit(self, identifier, action):
        return [a for a in self.detail(identifier)['audit'] if a['action'] == action]

    def approve(self, identifier, version=1):
        return self.client.post('/api/v1/requests/' + identifier + '/review', json={
            'expected_version': version, 'source_reviewed': True, 'reason': 'Dokumen sintetis diperiksa seluruh halaman',
            'password': 'test-password-only', 'consent': True})

    def change_tax(self, identifier, selection, version, invoice=None):
        invoice = invoice or self.detail(identifier)['draft']['invoice']
        return self.client.patch('/api/v1/requests/' + identifier + '/draft', json={
            'expected_version': version, 'invoice': invoice, 'tax_selection': selection,
            'reason': 'Pilihan pajak disesuaikan dokumen'})

    def submitted_sample(self):
        self.login('pic@amiga.local')
        identifier = self.sample('normal')
        self.pic_submit(identifier)
        self.login('finance@amiga.local')
        return identifier

    def test_tax_rules_endpoint_needs_a_session_and_serves_the_table(self):
        response = self.client.get('/api/v1/tax/rules')
        self.assertEqual(response.status_code, 200, response.text)
        rules = response.json()
        self.assertEqual(rules['rules_version'], 'pajak-poc.v2')
        self.assertEqual([row['id'] for row in rules['pph']], ['TANPA', 'PPH21', 'PPH23', 'PPH4_2_SEWA'])
        self.assertEqual([p['id'] for p in rules['presets']], ['TANPA_PAJAK', 'PPN', 'PPH', 'PPN_PPH'])
        self.assertEqual(rules['pph'][1]['example'], {'gross': '2000000.00', 'withheld': '50000.00', 'net': '1950000.00'})
        self.assertIn('ref_ids', rules['ppn'])
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/tax/rules').status_code, 401)

    def test_manifest_selection_through_the_api(self):
        self.login('pic@amiga.local')
        data = sample_input('normal')[0]
        response = self.client.post('/api/v1/intake-batches', headers={'Idempotency-Key': str(uuid4())}, json={
            'client_id': 'client_a', 'items': [self.descriptor(data) | {'tax_selection': {
                'pph': 'PPH23', 'ppn': False, 'recipient_has_npwp': True}}]})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['items'][0]['tax_selection'], pick('PPH23'))

    def test_invalid_selections_are_rejected(self):
        self.login('pic@amiga.local')
        data = sample_input('normal')[0]
        bad = [{'pph': 'PPH23', 'ppn': True, 'recipient_has_npwp': True, 'faktur_number': '123456789012'},
               {'pph': 'PPH99', 'ppn': False, 'recipient_has_npwp': True},
               {'pph': 'PPH23', 'ppn': 'yes', 'recipient_has_npwp': True},
               {'pph': 'PPH23', 'ppn': False, 'recipient_has_npwp': True, 'faktur_number': '0400250012345678'},
               {'pph': 'PPH23', 'ppn': False, 'recipient_has_npwp': True, 'rate': '0.5'}]
        for selection in bad:
            with self.subTest(selection=selection):
                response = self.client.post('/api/v1/intake-batches', headers={'Idempotency-Key': str(uuid4())}, json={
                    'client_id': 'client_a', 'items': [self.descriptor(data) | {'tax_selection': selection}]})
                self.assertEqual((response.status_code, response.json()['code']), (422, 'INVALID_PAYLOAD'))
        # Since schema v2 the faktur number is read from the document, so PPN without a typed number is valid.
        for good in ({'pph': 'PPH23', 'ppn': True, 'recipient_has_npwp': True, 'faktur_number': '010.000-24.12345678'},
                     {'pph': 'PPH23', 'ppn': True, 'recipient_has_npwp': True}):
            with self.subTest(good=good):
                response = self.client.post('/api/v1/intake-batches', headers={'Idempotency-Key': str(uuid4())}, json={
                    'client_id': 'client_a', 'items': [self.descriptor(data) | {'tax_selection': good}]})
                self.assertEqual(response.status_code, 201, response.text)

    def test_missing_selection_holds_approval_until_finance_chooses(self):
        pdf, saved = sample_input('normal')
        self.install_fake()
        self.login('pic@amiga.local')
        response = self.client.post('/api/v1/requests?client_id=client_a&filename=tanpa-pilihan.pdf', content=pdf,
                                    headers={'Content-Type': 'application/pdf', 'Idempotency-Key': str(uuid4())})
        identifier = response.json()['request_id']
        self.assertTrue(self.api.state.service.process_next())
        self.pic_submit(identifier, note='Jenis pajak belum dipilih, Finance yang menentukan')
        self.login('finance@amiga.local')
        approval = self.detail(identifier)['approval']
        self.assertFalse(approval['can_approve'])
        self.assertIn('potongan pajak', approval['reason'])
        self.assertEqual(self.approve(identifier).status_code, 422)
        response = self.change_tax(identifier, {'pph': 'TANPA', 'ppn': False, 'recipient_has_npwp': True}, 1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['approval']['can_approve'])
        self.assertEqual(self.approve(identifier, 2).status_code, 200)

    def test_changing_the_selection_after_approval_invalidates_it(self):
        identifier = self.submitted_sample()
        self.assertEqual(self.approve(identifier).status_code, 200)
        response = self.change_tax(identifier, {'pph': 'PPH23', 'ppn': False, 'recipient_has_npwp': True}, 1)
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['current_version'], detail['approved_version']), (2, None))
        self.assertEqual(detail['draft']['tax']['withheld_total'], '10000.00')
        self.assertTrue(self.audit(identifier, 'APPROVAL_INVALIDATED'))
        self.assertIsNotNone(detail['voucher_history'][0]['superseded_at'])
        self.login('pic@amiga.local')
        response = self.change_tax(identifier, {'pph': 'PPH21', 'ppn': False, 'recipient_has_npwp': True}, 2)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'INTAKE_LOCKED'))

    def test_printed_tax_needs_ppn_selection_and_approval_freezes_the_tax(self):
        identifier = self.submitted_sample()
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice.update(stated_tax_total='55000.00', stated_total='555000.00')
        response = self.edit(identifier, invoice, reason='Pajak tercetak 55.000 di invoice')
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertIn('TAX_PPN_CONFLICT', [c['code'] for c in detail['approval']['blocking_checks']])
        # The conflict is Finance's call: the tax is still computed from the printed PPN, and approval stays open.
        self.assertEqual((detail['draft']['tax']['status'], detail['draft']['tax']['net_payable']), ('COMPUTED', '555000.00'))
        self.assertTrue(detail['approval']['can_approve'])
        selection = {'pph': 'PPH23', 'ppn': True, 'recipient_has_npwp': True, 'faktur_number': '0400250012345678'}
        response = self.change_tax(identifier, selection, 2)
        self.assertEqual(response.status_code, 200, response.text)
        tax = response.json()['draft']['tax']
        self.assertEqual((tax['ppn_expected'], tax['withheld_total'], tax['net_payable']),
                         ('55000.00', '10000.00', '545000.00'))
        response = self.approve(identifier, 3)
        self.assertEqual(response.status_code, 200, response.text)
        with self.api.state.db.transaction() as conn:
            payload = conn.execute('SELECT payload FROM vouchers WHERE request_id=%s', (identifier,)).fetchone()['payload']
        self.assertEqual(payload['tax'], tax)
        self.assertEqual(payload['tax_selection'], selection)
        approved = self.audit(identifier, 'REVIEW_APPROVED')[0]['changes']['tax']
        self.assertEqual((approved['pph_id'], approved['net_payable'], approved['rules_version']),
                         ('PPH23', '545000.00', 'pajak-poc.v2'))

    def test_ppn_on_an_invoice_printing_zero_tax_is_flagged_and_left_to_finance(self):
        identifier = self.submitted_sample()
        selection = {'pph': 'PPH23', 'ppn': True, 'recipient_has_npwp': True, 'faktur_number': '0400250012345678'}
        response = self.change_tax(identifier, selection, 1)
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual(detail['status'], 'EXCEPTION')
        self.assertIn('TAX_PPN_MISSING', [c['code'] for c in detail['approval']['blocking_checks']])
        self.assertEqual((detail['draft']['tax']['status'], detail['draft']['tax']['ppn_amount']), ('COMPUTED', '0.00'))
        self.assertEqual(self.approve(identifier, 2).status_code, 200)
        [approved] = self.audit(identifier, 'REVIEW_APPROVED')
        self.assertIn('TAX_PPN_MISSING', [c['code'] for c in approved['changes']['open_checks']])

    def test_approved_voucher_prints_net_payable(self):
        identifier = self.submitted_sample()
        response = self.change_tax(identifier, {'pph': 'PPH23', 'ppn': False, 'recipient_has_npwp': True}, 1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.approve(identifier, 2).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())
        voucher = self.client.get(f'/api/v1/requests/{identifier}/voucher?version=2')
        self.assertEqual(voucher.status_code, 200, voucher.text[:200])
        pages, text = pdf_text(voucher.content)
        self.assertEqual(pages, 1)
        for expected in ('VOUCHER PENGELUARAN', 'Potongan PPh 23', '10.000', '490.000'):
            self.assertIn(expected, text)

    def test_queue_listing_shows_net_payable(self):
        identifier = self.submitted_sample()
        response = self.client.get('/api/v1/requests?client_id=client_a')
        row = next(item for item in response.json()['items'] if str(item['id']) == identifier)
        self.assertEqual(row['net_payable'], '500000.00')

    def test_schema_reinitializes_without_error(self):
        self.api.state.db.initialize()
        self.api.state.db.initialize()

    def test_batch_item_selection_reaches_request_snapshot_and_audit(self):
        self.install_fake()
        self.login('pic@amiga.local')
        data = sample_input('normal')[0]
        item = self.descriptor(data) | {'tax_selection': pick('PPH23')}
        batch = self.api.state.batches.create(self.user(), 'client_a', [item], 'tax-' + uuid4().hex)
        self.assertEqual(batch['items'][0]['tax_selection'], pick('PPH23'))
        batch = self.api.state.batches.receive(batch['id'], 1, self.user(), data)
        identifier = str(batch['items'][0]['request_id'])
        self.assertTrue(self.api.state.service.process_next())
        draft = self.detail(identifier)['draft']
        self.assertEqual(draft['tax_selection'], pick('PPH23'))
        self.assertEqual((draft['tax']['status'], draft['tax']['withheld_total'], draft['tax']['net_payable']),
                         ('COMPUTED', '10000.00', '490000.00'))
        with self.api.state.db.transaction() as conn:
            stored = conn.execute('SELECT tax_selection FROM requests WHERE id=%s', (identifier,)).fetchone()
        self.assertEqual(stored['tax_selection'], pick('PPH23'))
        self.assertEqual(self.audit(identifier, 'UPLOADED')[0]['changes']['tax_selection'], pick('PPH23'))

    def test_manifest_without_selection_keeps_old_digest_and_null_column(self):
        self.login('pic@amiga.local')
        data = sample_input('normal')[0]
        batch = self.api.state.batches.create(self.user(), 'client_a', [self.descriptor(data)], 'plain-' + uuid4().hex)
        self.assertIsNone(batch['items'][0]['tax_selection'])

    def test_demo_sample_carries_default_selection(self):
        identifier = self.sample('normal')
        detail = self.detail(identifier)
        self.assertEqual(detail['status'], 'READY_FOR_REVIEW')
        self.assertEqual(detail['draft']['tax_selection'], taxes.SAMPLE_SELECTION)
        self.assertEqual(detail['draft']['tax']['net_payable'], detail['draft']['invoice']['stated_total'])

    def test_finance_can_change_only_the_selection(self):
        identifier = self.sample('normal')
        draft = self.detail(identifier)['draft']
        changed = self.api.state.service.edit(identifier, self.user(), 1, draft['invoice'],
                                              'Ganti jenis potongan pajak', tax_selection=pick('PPH21'))
        self.assertEqual(changed['current_version'], 2)
        tax = changed['draft']['tax']
        self.assertEqual((tax['pph_id'], tax['withheld_total'], tax['net_payable']), ('PPH21', '12500.00', '487500.00'))
        self.assertIn('PPh 21 untuk orang pribadi; nama vendor tampak badan usaha.', tax['warnings'])
        edited = self.audit(identifier, 'DRAFT_EDITED')[0]['changes']
        self.assertEqual(edited['tax_selection.pph'], {'before': 'TANPA', 'after': 'PPH21'})
        with self.assertRaises(AppError) as caught:
            self.api.state.service.edit(identifier, self.user(), 2, draft['invoice'], 'Tidak ada yang berubah',
                                        tax_selection=pick('PPH21'))
        self.assertEqual(caught.exception.code, 'NO_CHANGES')
        # The PIC may change the selection during intake; once submitted, changes are Finance's.
        self.login('pic@amiga.local')
        self.pic_submit(identifier, version=2)
        with self.assertRaises(AppError) as caught:
            self.api.state.service.edit(identifier, self.user(), 2, draft['invoice'], 'PIC mencoba mengganti',
                                        tax_selection=pick('PPH23'))
        self.assertEqual(caught.exception.code, 'INTAKE_LOCKED')

    def test_empty_tax_with_no_ppn_is_counted_as_declared_zero(self):
        identifier = self.sample('normal')
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['stated_tax_total'] = None
        response = self.edit(identifier, invoice, reason='Pajak tidak tercetak di invoice')
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()['draft']
        found = {c['code'] for c in draft['validation']['checks']}
        self.assertTrue({'DECLARED_ZERO', 'TOTAL_MATCH'} <= found)
        self.assertTrue(draft['tax']['ppn_declared_zero'])

    def test_request_without_selection_keeps_its_status(self):
        pdf, saved = sample_input('normal')

        class FakeClient:
            def preflight(self):
                pass

            def extract_pdf(self, data, case_id):
                raw = {'invoice': saved['invoice'], 'evidence': [{'field': path, 'page': entry['page'], 'raw_value': entry['raw_value']}
                       for path, entry in saved['source_evidence'].items() if entry]}
                return {'run_id': str(uuid4()), 'duration_ms': 0, 'cost_upper_estimate_usd': '0', 'usage': {},
                        'prompt_version': 'TEST_NO_NETWORK',
                        'response': {'status': 'completed', 'output': [{'type': 'message', 'content': [
                            {'type': 'output_text', 'text': json.dumps(raw)}]}]}}

        self.api.state.service.live_client_factory = FakeClient
        self.login('pic@amiga.local')  # since 15 Oct only the PIC uploads
        response = self.client.post('/api/v1/requests?client_id=client_a&filename=tanpa-pajak.pdf', content=pdf,
                                    headers={'Content-Type': 'application/pdf', 'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 202, response.text)
        identifier = response.json()['request_id']
        self.assertTrue(self.api.state.service.process_next())
        detail = self.detail(identifier)
        self.assertEqual(detail['status'], 'READY_FOR_REVIEW')
        self.assertEqual(detail['draft']['tax']['status'], 'NOT_SELECTED')
        required = [c for c in detail['draft']['validation']['checks'] if c['code'] == 'TAX_SELECTION_REQUIRED']
        self.assertEqual([(c['status'], c['blocking']) for c in required], [('NOT_CHECKED', False)])


if __name__ == '__main__':
    unittest.main()
