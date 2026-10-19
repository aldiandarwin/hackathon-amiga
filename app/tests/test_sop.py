"""SOP guidance endpoints: cards come from the local corpus, Bedrock is always mocked, never called."""

import re
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.service import AppError
from app.settings import ROOT
from app.sop_api import (FALLBACK_NOTICE, SCREEN_CODE, STATUS_WORDS, TEXT_WORDS, card_label, plain_title, rag_module,
                         screen_text, sop_router)
from app.tests import test_app as fixtures


def standalone_client():
    api = FastAPI()

    @api.exception_handler(AppError)
    async def application_error(request, error):
        return JSONResponse({'code': error.code, 'message': str(error)}, status_code=error.status)

    api.include_router(sop_router(lambda: {'id': 'finance_a'}))
    return TestClient(api)


class SopEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = standalone_client()
        self.rag = rag_module()

    def test_card_by_code_comes_from_the_local_corpus(self):
        response = self.client.get('/api/v1/sop/kartu?kode=TAX_PPN_DIFFERENT')
        self.assertEqual(response.status_code, 200, response.text)
        card = response.json()
        self.assertEqual(card['sop_id'], 'EXC-TAX_PPN_DIFFERENT')
        self.assertIn('PPN tertulis berbeda dari hitungan faktur', card['teks'])

    def test_card_by_sop_id(self):
        response = self.client.get('/api/v1/sop/kartu?sop_id=ALUR-POTONGAN-PAJAK')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()['kode'])

    def test_unknown_code_and_bad_selectors_are_rejected(self):
        self.assertEqual(self.client.get('/api/v1/sop/kartu?kode=NO_SUCH_CODE').json()['code'], 'NOT_FOUND')
        for query in ('', '?kode=TAX_PPN_MISSING&sop_id=EXC-TAX_PPN_MISSING'):
            with self.subTest(query=query):
                response = self.client.get('/api/v1/sop/kartu' + query)
                self.assertEqual((response.status_code, response.json()['code']), (422, 'INVALID_PAYLOAD'))
        self.assertEqual(self.client.get('/api/v1/sop/kartu?kode=lowercase').status_code, 422)

    def test_only_question_and_code_reach_the_model(self):
        answer = {'jawaban': '1. Cocokkan dengan faktur pajak. [EXC-TAX_PPN_DIFFERENT]', 'model': 'fake-model',
                  'peringatan': [], 'referensi': [{'sop_id': 'EXC-TAX_PPN_DIFFERENT', 'judul': 'Judul',
                                                   'bagian': ['Langkah penanganan'], 'skor': 0.8, 'skor_kata': 0.4,
                                                   'lokasi': 'knowledge-base/sop/exc-tax-ppn-different.md'}]}
        with mock.patch.object(self.rag, 'jawab', return_value=answer) as jawab:
            response = self.client.post('/api/v1/sop/tanya', json={'pertanyaan': ' Apa langkahnya? ',
                                                                    'kode': 'TAX_PPN_DIFFERENT'})
        self.assertEqual(response.status_code, 200, response.text)
        jawab.assert_called_once_with('Kode TAX_PPN_DIFFERENT. Apa langkahnya?')
        body = response.json()
        self.assertEqual(body['mode'], 'rag')
        self.assertEqual(body['referensi'], [{'sop_id': 'EXC-TAX_PPN_DIFFERENT', 'judul': 'Judul', 'label': 'Judul'}])

    def test_bedrock_failure_falls_back_to_nearest_cards(self):
        with mock.patch.object(self.rag, 'jawab', side_effect=RuntimeError('no credentials')):
            response = self.client.post('/api/v1/sop/tanya', json={'pertanyaan': 'PPN dipilih tapi pajak kosong'})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body['mode'], body['jawaban']), ('cadangan', None))
        self.assertEqual(len(body['referensi']), 3)
        self.assertIn('EXC-TAX_PPN_MISSING', [r['sop_id'] for r in body['referensi']])
        self.assertEqual(body['peringatan'], [FALLBACK_NOTICE])
        missing = next(r for r in body['referensi'] if r['sop_id'] == 'EXC-TAX_PPN_MISSING')
        self.assertEqual(missing['label'], 'PPN dipilih tapi nominal pajak kosong')

    def test_labels_turn_card_headings_into_plain_titles(self):
        response = self.client.get('/api/v1/sop/label')
        self.assertEqual(response.status_code, 200, response.text)
        labels = response.json()['labels']
        self.assertEqual(labels['BANK_MISMATCH'], 'Nomor rekening di invoice berbeda dari master vendor')
        self.assertEqual(labels['DUPLICATE_CHECK'], 'Pencarian invoice kembar tidak bisa jalan')
        cards, _ = self.rag.muat_kartu()
        self.assertEqual(set(labels), {c['kode'] for c in cards if c['kode']})
        for kode, label in labels.items():
            with self.subTest(kode=kode):
                self.assertNotIn(kode, label)
                self.assertFalse(label.endswith('.'))
                self.assertEqual(label[0], label[0].upper())

    def test_plain_title_rule(self):
        cases = [('BANK_MISMATCH: nomor rekening berbeda.', 'BANK_MISMATCH', 'Nomor rekening berbeda'),
                 ('DUPLICATE_CHECK belum diperiksa: pencarian kembar', 'DUPLICATE_CHECK', 'Pencarian kembar'),
                 ('Antrean: memantau invoice yang masuk', None, 'Antrean: memantau invoice yang masuk'),
                 ('pajak: catatan', 'TAX_X', 'Pajak: catatan'),
                 ('TAX_X', 'TAX_X', 'Tax x')]
        for heading, kode, expected in cases:
            with self.subTest(heading=heading):
                self.assertEqual(plain_title(heading, kode), expected)

    def test_cards_reach_the_screen_without_machine_codes(self):
        cards, _ = self.rag.muat_kartu()
        labels = {c['kode']: card_label(c) for c in cards if c['kode']}
        for card in cards:
            with self.subTest(sop_id=card['sop_id']):
                shown = screen_text(card['teks'], labels)
                self.assertEqual(SCREEN_CODE.findall(shown), [])
                self.assertEqual([text for text in TEXT_WORDS if text in shown], [])
        card = self.client.get('/api/v1/sop/kartu?kode=INSUFFICIENT_CALCULATION_EVIDENCE').json()
        self.assertIn('Statusnya belum bisa diperiksa, dan di versi demo status itu tetap menahan request di '
                      '"Perlu perhatian".', card['teks_layar'])
        self.assertIn('NOT_CHECKED', card['teks'])  # retrieval and the AI keep reading the codes

    def test_a_code_next_to_its_screen_words_is_dropped_not_doubled(self):
        labels = {'BANK_MISMATCH': 'Nomor rekening beda'}
        cases = [('- VERSION_CONFLICT, "Versi sudah berubah."', '- "Versi sudah berubah."'),
                 ('- NOT_FOUND: akun tidak ditugaskan.', '- Akun tidak ditugaskan.'),
                 ('Server menolak dengan INTAKE_LOCKED.', 'Server menolak.'),
                 ('Request masuk EXCEPTION dan tampil "Perlu perhatian".', 'Request masuk "Perlu perhatian".'),
                 ('lolos sebagai LINE_TOTAL_MATCH, SUBTOTAL_MATCH, dan TOTAL_MATCH kalau cocok', 'lolos kalau cocok'),
                 ('- BANK_MISMATCH: rekening beda.', '- "Nomor rekening beda": rekening beda.'),
                 ('Muncul HANDOVER_FAILED? Artinya "Pengiriman gagal."', 'Muncul pesan "Pengiriman gagal"?'),
                 ('Statusnya NOT_CHECKED. Aturan: demo-rules.v1.', 'Statusnya belum bisa diperiksa. Aturan: versi demo.')]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(screen_text(raw, labels), expected)

    def test_status_words_match_the_review_screen(self):
        source = (ROOT / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
        shown = dict(re.findall(r"([A-Z_]+):\['([^']+)'", re.search(r'const statuses = \{(.*?)\};', source)[1]))
        self.assertGreaterEqual(len(shown), 8)
        for code, label in shown.items():
            with self.subTest(code=code):
                self.assertEqual(STATUS_WORDS[code], label)

    def test_card_and_references_carry_plain_labels(self):
        card = self.client.get('/api/v1/sop/kartu?kode=TAX_PPN_DIFFERENT').json()
        self.assertEqual(card['label'], 'PPN tertulis beda dari hitungan faktur')
        self.assertEqual(self.client.get('/api/v1/sop/kartu?sop_id=ALUR-POTONGAN-PAJAK').json()['label'],
                         'Potongan pajak: memilih, menghitung, dan mencetak di voucher')
        answer = {'jawaban': '1. Cek rekening. [EXC-BANK_MISMATCH]', 'model': 'fake-model', 'peringatan': [],
                  'referensi': [{'sop_id': 'EXC-BANK_MISMATCH', 'judul': 'BANK_MISMATCH: nomor rekening beda'}]}
        with mock.patch.object(self.rag, 'jawab', return_value=answer):
            body = self.client.post('/api/v1/sop/tanya', json={'pertanyaan': 'Rekening beda?'}).json()
        self.assertEqual(body['referensi'][0]['label'], 'Nomor rekening beda')

    def test_engineering_warnings_reach_the_reviewer_in_plain_words(self):
        answer = {'jawaban': '1. Cek PDF.', 'model': 'fake-model', 'referensi': [],
                  'peringatan': ['stopReason max_tokens, jawaban mungkin terpotong',
                                 'sitasi salah ejaan: EXC-BANK-MISMATCH', 'sitasi di luar kartu konteks: EXC-X_Y',
                                 'jawaban tanpa sitasi kartu']}
        with mock.patch.object(self.rag, 'jawab', return_value=answer):
            body = self.client.post('/api/v1/sop/tanya', json={'pertanyaan': 'Apa langkahnya?'}).json()
        self.assertEqual(len(body['peringatan']), 3)
        for text in body['peringatan']:
            with self.subTest(text=text):
                self.assertNotRegex(text, r'stopReason|sitasi|EXC-|_')

    def test_question_payload_is_bounded(self):
        for payload in ({'pertanyaan': 'ok'}, {'pertanyaan': 'x' * 501}, {'pertanyaan': 'Apa?', 'extra': 1}):
            with self.subTest(payload=list(payload)):
                self.assertEqual(self.client.post('/api/v1/sop/tanya', json=payload).status_code, 422)


class SopSessionTests(unittest.TestCase):
    """The SOP routes share the app's session and CSRF guard."""
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def test_session_and_csrf_are_required(self):
        self.assertEqual(self.client.get('/api/v1/sop/kartu?kode=BANK_UNVERIFIED').status_code, 200)
        token = self.client.headers.pop('X-CSRF-Token')
        response = self.client.post('/api/v1/sop/tanya', json={'pertanyaan': 'Apa arti BANK_UNVERIFIED?'})
        self.assertEqual(response.json()['code'], 'CSRF_REJECTED')
        self.client.headers['X-CSRF-Token'] = token
        self.client.post('/api/v1/logout')
        response = self.client.get('/api/v1/sop/kartu?kode=BANK_UNVERIFIED')
        self.assertEqual((response.status_code, response.json()['code']), (401, 'UNAUTHENTICATED'))

    def test_labels_need_a_session(self):
        self.assertIn('BANK_MISMATCH', self.client.get('/api/v1/sop/label').json()['labels'])
        self.client.post('/api/v1/logout')
        response = self.client.get('/api/v1/sop/label')
        self.assertEqual((response.status_code, response.json()['code']), (401, 'UNAUTHENTICATED'))


if __name__ == '__main__':
    unittest.main()
