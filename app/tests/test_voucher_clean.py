"""V6 print contract: frozen branding, concise content, unchanged amounts and working QR links."""
from copy import deepcopy
import hashlib
from io import BytesIO
import re
import unittest

from pypdf import PdfReader

from app import taxes
from app.tests.test_tax_adjustments import addition
from app.tests.test_tax_flow import SIGNOFF, pdf_text, v4_payload, with_lines
from app.voucher_clean import BRAND, LOGO, LOGO_SHA256
from app.voucher_pdf import render_voucher


def clean_payload():
    payload = deepcopy(v4_payload())
    payload['template_version'] = 'amiga-demo-v6'
    payload['invoice'].update(stated_tax_total='0.00', stated_total='500000.00')
    payload['tax_selection'] = addition()
    payload['tax'], _ = taxes.compute(payload['invoice'], payload['tax_selection'])
    return payload


class CleanVoucherTests(unittest.TestCase):
    def test_brand_palette_matches_the_application_and_official_logo_is_unchanged(self):
        css = (LOGO.parents[1]/'app.css').read_text(encoding='utf-8')
        for key, color in BRAND.items():
            token = re.search(r'--amiga-'+key.replace('_','-')+r':(#[a-fA-F0-9]{6})', css)
            self.assertIsNotNone(token, key)
            self.assertEqual(token.group(1).upper(), color.upper())
        self.assertEqual(hashlib.sha256(LOGO.read_bytes()).hexdigest(), LOGO_SHA256)

    def test_print_has_one_summary_and_omits_the_crossed_out_technical_sections(self):
        payload = clean_payload()
        before = deepcopy(payload)
        pdf = render_voucher(payload, SIGNOFF)
        pages, text = pdf_text(pdf)
        self.assertEqual(pages, 1)
        for value in ('PPN tambahan', 'Potongan PPh 23', '500.000', '55.000', '10.000', '545.000',
                      'Diajukan Oleh', 'Disetujui Oleh', 'ABCD2345', 'WXYZ6789', 'Klik / pindai QR'):
            self.assertIn(value, text)
        self.assertEqual(text.count('JUMLAH KE VENDOR'), 1)
        for removed in ('SHA-256', 'Request:', 'Template:', 'Pajak dihitung sistem', 'BATAS OTORISASI',
                        'CATATAN KONFIRMASI', 'Alasan penyesuaian', 'Jejak review', 'pajak-poc.v', 'http://'):
            self.assertNotIn(removed, text)
        self.assertEqual(payload, before)
        self.assertGreaterEqual(len(PdfReader(BytesIO(pdf)).pages[0].images), 1)

    def test_final_qr_is_clickable_and_keeps_the_frozen_verification_destination(self):
        reader = PdfReader(BytesIO(render_voucher(clean_payload(), SIGNOFF)))
        destinations = [annotation.get_object().get('/A', {}).get('/URI') for page in reader.pages
                        for annotation in page.get('/Annots', [])]
        self.assertIn(SIGNOFF['verify_url'], destinations)

    def test_draft_has_no_director_signature_or_verification_link(self):
        data = render_voucher(clean_payload())
        _, text = pdf_text(data)
        self.assertIn('DRAF', text)
        self.assertIn('Menunggu tanda tangan', text)
        self.assertNotIn('WXYZ6789', text)
        self.assertNotIn('Klik / pindai QR', text)

    def test_six_lines_fit_one_page_and_long_invoices_keep_every_line(self):
        for count in (1, 3, 6):
            with self.subTest(lines=count):
                self.assertEqual(pdf_text(render_voucher(with_lines(clean_payload(), count, 'QA'), SIGNOFF))[0], 1)
        payload = clean_payload()
        item = payload['invoice']['line_items'][0]
        payload['invoice']['line_items'] = [dict(item, line_number=i, description=f'Baris {i:03d} <uji> & '+('rincian '*8))
                                          for i in range(1,61)]
        data = render_voucher(payload)
        reader = PdfReader(BytesIO(data))
        text = ' '.join(page.extract_text() for page in reader.pages)
        for i in range(1,61):
            self.assertIn(f'Baris {i:03d} <uji> &', text)
        for page in reader.pages:
            self.assertIn('Halaman ', page.extract_text())
            self.assertGreaterEqual(len(page.images), 1)
        self.assertEqual(data, render_voucher(payload))

    def test_v5_draft_and_final_remain_byte_identical(self):
        payload = v4_payload() | {'template_version': 'amiga-demo-v5'}
        self.assertEqual(hashlib.sha256(render_voucher(payload)).hexdigest(),
                         'c3ca40fca71efa8faf295b0c1863c6118873188d1c0c50f075b12c590fa427da')
        self.assertEqual(hashlib.sha256(render_voucher(payload, SIGNOFF)).hexdigest(),
                         '453892c84503b35a2d46aae748001a8b86aebf6f530245fccc163805c9df29a7')

    def test_v7_draft_and_final_remain_byte_identical(self):
        # Recorded from the unchanged v7 renderer on 2026-10-17, before amiga-demo-v8 branched the signature boxes.
        payload = clean_payload() | {'template_version': 'amiga-demo-v7'}
        self.assertEqual(hashlib.sha256(render_voucher(payload)).hexdigest(),
                         'e0f3dff66454d7ea2e6f4b8fae3f494fee7682f79e308467c8170d7f9342d243')
        self.assertEqual(hashlib.sha256(render_voucher(payload, SIGNOFF)).hexdigest(),
                         'b19d94d30388173e829b1375c1b0557203201c973d20071c2250df57fb3ed061')

    def test_v8_prints_only_the_pic_and_vendor_boxes(self):
        payload = clean_payload() | {'template_version': 'amiga-demo-v8'}
        for signoff in (None, SIGNOFF):
            pages, text = pdf_text(render_voucher(payload, signoff))
            self.assertEqual(pages, 1)
            for expected in ('Diajukan Oleh', 'Diterima Oleh', 'PT Contoh Demo', 'Vendor penerima pembayaran'):
                self.assertIn(expected, text)
            for absent in ('Diperiksa Oleh', 'Disetujui Oleh', 'Finance Reviewer AMIGA', 'Manajer Keuangan AMIGA'):
                self.assertNotIn(absent, text)

    def test_v6_draft_and_final_remain_byte_identical(self):
        # Recorded from the unchanged v6 renderer on 2026-10-15, before amiga-demo-v7 branched inside render_clean.
        from app.specimen import synthetic_specimen
        digest = lambda data: hashlib.sha256(data).hexdigest()
        payload = clean_payload()
        self.assertEqual(digest(render_voucher(payload)),
                         '7cb397ae237ed0ceb1f3951e38ca4a4f6863f3a34346b123fb56a423a7b4cb46')
        self.assertEqual(digest(render_voucher(payload, SIGNOFF)),
                         '3805e7c6934611eb2c251a2c4848fa417bb118f84fb08b8f701ce2c1701b9a76')
        reviewer, director = synthetic_specimen('Dian Pratama'), synthetic_specimen('Bagas Wiratama')
        signoff = deepcopy(SIGNOFF)
        payload['signatures']['reviewer']['specimen_sha256'] = digest(reviewer)
        signoff['director']['specimen_sha256'] = digest(director)
        self.assertEqual(digest(render_voucher(payload, signoff, specimens={digest(png): png for png in (reviewer, director)})),
                         '9db58cab1c477bebf4ab57b8e012f2a2c722da05990c3e35c0c3b57bf6b7b1ff')
