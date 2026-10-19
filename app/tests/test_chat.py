"""Robot Admin chat: what it may read, how it finds invoices, and whose conversations it keeps. No paid request."""

from datetime import date
from decimal import Decimal
import json
import re
import time
import unittest
from unittest import mock
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from app import chat_agent, chat_api, chat_llm, chat_search
from app.chat_llm import ChatConfig, ChatUnavailable, Ledger, OpenAIChat
from app.database import Database
from app.settings import ROOT
from app.tests import test_app as fixtures

FAKE_ACCOUNT, FAKE_NPWP = '8800123456789', '01.234.567.8-901.000'
SEARCH_DESIGN = {'kata_kunci': 'desain design logo branding', 'vendor': None, 'klien': None, 'status': None,
                 'dari_tanggal': None, 'sampai_tanggal': None, 'nominal_min': None, 'nominal_maks': None,
                 'urutan': 'relevan', 'batas': 5}


def call(name, args, call_id='call_1'):
    return {'type': 'function_call', 'id': 'fc_' + call_id, 'call_id': call_id, 'name': name,
            'arguments': json.dumps(args), 'status': 'completed'}


def say(text):
    return {'type': 'message', 'id': 'msg_1', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}


class FakeLLM:
    """Scripted Responses calls: a list of output items, or an exception, per call. Keeps every payload it got."""

    def __init__(self, *steps):
        self.steps, self.payloads = list(steps), []

    def ready(self):
        return True

    def respond(self, payload, user_id, deadline):
        self.payloads.append(json.loads(json.dumps(payload)))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return {'status': 'completed', 'output': step, '_cost_usd': Decimal('0.0001')}


class MemoryLedger:
    def __init__(self):
        self.rows = []

    def reserve(self, user_id, reserve_usd, stop_usd):
        self.rows.append('PENDING')
        return len(self.rows) - 1

    def finish(self, row, state, usage=None, cost=None, duration_ms=None):
        self.rows[row] = state


def invoice(number, vendor, items, total, day='2026-10-01'):
    return {'vendor_name': vendor, 'invoice_number': number, 'invoice_date': day, 'due_date': None, 'currency': 'IDR',
            'stated_subtotal': total, 'stated_discount_total': None, 'stated_tax_total': None, 'stated_total': total,
            'vendor_id': None, 'vendor_npwp': FAKE_NPWP,
            'line_items': [{'line_number': n, 'description': text, 'quantity': '1', 'unit_price': total,
                            'stated_line_total': total} for n, text in enumerate(items, 1)],
            'payment': {'bank_name': 'Bank Contoh', 'account_holder': vendor, 'account_number': FAKE_ACCOUNT}}


def seed_invoice(conn, client_id, uploader, data, status, submitted=True, events=(), checks=()):
    """A read and checked invoice written straight to the database, so tests and QA get many topics without extraction."""
    request_id = uuid4()
    conn.execute('INSERT INTO requests(id,client_id,uploaded_by,filename,document_key,pdf_sha256,page_count,pages,mode,'
                 'status,current_version,idempotency_key,submitted_at,submitted_by,submitted_version) '
                 "VALUES (%s,%s,%s,%s,%s,%s,1,%s,'REPLAY',%s,1,%s,CASE WHEN %s THEN now() END,%s,%s)",
                 (request_id, client_id, uploader, data['invoice_number'] + '.pdf', f'seed/{request_id}', '0' * 64,
                  Jsonb([]), status, str(request_id), submitted, uploader if submitted else None, 1 if submitted else None))
    conn.execute('INSERT INTO invoice_versions(request_id,version,snapshot,actor_id) VALUES (%s,1,%s,%s)',
                 (request_id, Jsonb({'invoice': data, 'source_evidence': {},
                                     'tax': {'status': 'COMPUTED', 'net_payable': data['stated_total']},
                                     'validation': {'checks': list(checks)}}), uploader))
    for action, actor, reason, *changes in events:
        Database.audit(conn, request_id, actor, action, reason, changes[0] if changes else {}, 1)
    return str(request_id)


def director_id(conn):
    return conn.execute("SELECT id,email FROM users WHERE role='AMIGA_DIRECTOR' AND disabled_at IS NULL "
                        'ORDER BY id LIMIT 1').fetchone()


def seed_portfolio(conn):
    """Team A holds five invoices on client_a, team B two on client_b. Two of team A's are about design work."""
    director = director_id(conn)['id']
    return {
        'logo': seed_invoice(conn, 'client_a', 'pic_a', invoice('INV-DSN-01', 'PT Kreasi Visual Nusantara',
                                                               ['Jasa desain logo dan brand guideline'], '18500000'),
                             'AMIGA_APPROVED'),
        'sosmed': seed_invoice(conn, 'client_a', 'pic_a', invoice('INV-DSN-02', 'Studio Garis Kreatif',
                                                                 ['Desain materi promosi media sosial 12 konten'], '7200000'),
                               'READY_FOR_REVIEW'),
        'mobil': seed_invoice(conn, 'client_a', 'pic_a', invoice('INV-SWA-01', 'PT Armada Sewa Mobil',
                                                                ['Sewa kendaraan operasional Oktober'], '12000000'),
                              'AMIGA_REVIEWED'),
        'katering': seed_invoice(conn, 'client_a', 'pic_a', invoice('INV-CAT-01', 'PT Dapur Nusantara Catering',
                                                                   ['Konsumsi rapat kerja 50 pax'], '3750000'),
                                 'READY_FOR_REVIEW', submitted=False),
        'pajak': seed_invoice(conn, 'client_a', 'pic_a', invoice('INV-PJK-01', 'Konsultan Pajak Sentosa',
                                                                ['Jasa konsultasi pajak bulanan'], '9000000'), 'RETURNED',
                              events=[('DIRECTOR_RETURNED', director, 'Nilai PPN perlu dicek ulang dengan faktur.')]),
        'maskot': seed_invoice(conn, 'client_b', 'pic_b', invoice('INV-ILU-01', 'Ilustra Design House',
                                                                 ['Ilustrasi maskot dan desain kemasan produk'], '22000000'),
                               'AMIGA_APPROVED'),
        'ac': seed_invoice(conn, 'client_b', 'pic_b', invoice('INV-AC-01', 'PT Sejuk Teknik',
                                                             ['Perawatan AC kantor 3 lantai'], '2800000'), 'READY_FOR_REVIEW'),
    }


class ChatUnitTests(unittest.TestCase):
    def test_status_labels_cover_every_queue_status(self):
        source = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
        codes = set(re.findall(r'([A-Z_]+):\[', re.search(r'const statuses = \{(.*?)\};', source).group(1)))
        self.assertTrue(codes)
        self.assertLessEqual(codes, set(chat_search.STATUS_LABELS))

    def test_money_and_untrusted_text(self):
        self.assertEqual(chat_search.money('18500000.00'), 'Rp 18.500.000')
        self.assertEqual(chat_search.money('1250.5', 'USD'), 'USD 1.250,50')
        self.assertIsNone(chat_search.money(None))
        text = chat_search.clean('Transfer\n\nke rekening 8800123456789 ' + 'x' * 300)
        self.assertNotIn('8800123456789', text)
        self.assertNotIn('\n', text)
        self.assertLessEqual(len(text), 201)
        self.assertEqual(chat_search.clean('INV/2026/100000001', 60, mask=False), 'INV/2026/100000001')
        self.assertEqual(chat_search.topic('Invoice jasa desain apa saja?'), 'desain')

    def test_answers_carry_no_long_dashes(self):
        dash = '\u2014'
        self.assertEqual(chat_agent.plain_dashes(f'INV/KVN/2026/0815 {dash} PT Kreasi Visual Nusantara, Rp 18.500.000 {dash} Disetujui final.'),
                         'INV/KVN/2026/0815, PT Kreasi Visual Nusantara, Rp 18.500.000, Disetujui final.')
        self.assertEqual(chat_agent.plain_dashes(f'{dash} Cocokkan rekening.\nLangkah 2\u20133 selesai {dash}.'),
                         '- Cocokkan rekening.\nLangkah 2-3 selesai.')
        # A turn without tool calls never opens the database, so the stored answer is checked without one.
        reply = chat_agent.answer(None, FakeLLM([say(f'Ada 2 invoice desain {dash} INV-DSN-01 dan INV-DSN-02.')]),
                                  {'id': 'pic', 'name': 'Dian Pratama', 'role': 'PIC'}, 'Invoice desain?', [])
        self.assertEqual(reply['isi'], 'Ada 2 invoice desain, INV-DSN-01 dan INV-DSN-02.')

    def test_answers_never_repeat_the_card_note(self):
        # A Finance answer of 16 Okt 2026 copied the note history_text gives earlier answers, invoice id included.
        note = ('[Kartu invoice yang tampil: 2244422/INV/PO6524C45D07EB2 · SIPLah Toko Ladang · Rp 7.950.000 · '
                'Disetujui final · id a2e9e11f-6bf5-4956-8483-71bd75c6e170]')
        reply = chat_agent.answer(None, FakeLLM([say('Selesai. Voucher final untuk invoice ini sudah tersedia.\n\n' + note)]),
                                  {'id': 'fin', 'name': 'Nadia Putri', 'role': 'FINANCE_REVIEWER'}, 'Langkah saya?', [])
        self.assertEqual(reply['isi'], 'Selesai. Voucher final untuk invoice ini sudah tersedia.')

    def test_answers_breathe(self):
        # The SIPLah answer of 16 Okt was one block of four sentences. The panel makes every line a paragraph.
        text = ('Angkanya sudah sesuai. Subtotal Rp 7.162.162 ditambah PPN Rp 787.838 menjadi Rp 7.950.000. '
                'Finance sudah menyetujuinya dengan tiga catatan. Faktur pajak belum dilampirkan. '
                '[EXC-TAX_FAKTUR_NOT_FOUND] Keputusan ada di Anda.\n- Total baris sudah termasuk PPN. Subtotal tetap.\n'
                'Pembelinya SRI NURHAYATI, S.Pd. lewat PT. Ladang Karya Husada.')
        self.assertEqual(chat_agent.airy(text).split('\n'), [
            'Angkanya sudah sesuai. Subtotal Rp 7.162.162 ditambah PPN Rp 787.838 menjadi Rp 7.950.000.',
            'Finance sudah menyetujuinya dengan tiga catatan. Faktur pajak belum dilampirkan. [EXC-TAX_FAKTUR_NOT_FOUND]',
            'Keputusan ada di Anda.',
            '- Total baris sudah termasuk PPN. Subtotal tetap.',
            'Pembelinya SRI NURHAYATI, S.Pd. lewat PT. Ladang Karya Husada.'])
        # Two sentences past about three lines of the panel go on lines of their own.
        long = 'Kalimat ini sengaja dibuat cukup panjang supaya dua kalimat sekaligus melewati batas tiga baris di panel. '
        self.assertEqual(len(chat_agent.airy((long * 2).strip()).split('\n')), 2)

    def test_sums_name_a_price_that_already_holds_the_ppn(self):
        # SIPLah laptop, 16 Okt: the price with PPN was copied into the line total, while the invoice itself adds up.
        siplah = {'currency': 'IDR', 'stated_subtotal': '7162162.00', 'stated_discount_total': None,
                  'stated_other_charges_total': '0.00', 'stated_tax_total': '787838.00', 'stated_total': '7950000.00',
                  'line_items': [{'quantity': '1.00', 'unit_price': '7950000.00', 'stated_line_total': '7950000'}]}
        self.assertEqual(chat_search.arithmetic(siplah), {'total_cocok': True, 'catatan': [
            'Subtotal Rp 7.162.162 ditambah PPN Rp 787.838 menjadi Rp 7.950.000, sama dengan total tertulis.',
            'Diskon tidak tertulis di invoice, dan totalnya tetap cocok tanpa diskon.',
            'Jumlah total baris Rp 7.950.000 sudah termasuk PPN, karena sama dengan subtotal ditambah PPN. '
            'Subtotal tidak perlu diubah.']})
        # As the AI read it: the unit price held the PPN, the line total did not.
        siplah['line_items'][0]['stated_line_total'] = '7162162.00'
        self.assertEqual(chat_search.arithmetic(siplah)['catatan'][-1],
                         'Harga satuan tertulis sudah termasuk PPN, sedangkan total baris sudah nilai sebelum PPN.')
        wrong = siplah | {'stated_total': '8000000.00', 'stated_discount_total': '0.00'}
        self.assertEqual(chat_search.arithmetic(wrong)['catatan'][0],
                         'Subtotal Rp 7.162.162 ditambah PPN Rp 787.838 menjadi Rp 7.950.000, sedangkan total tertulis '
                         'Rp 8.000.000, selisih Rp 50.000.')
        self.assertFalse(chat_search.arithmetic(wrong)['total_cocok'])

    def test_next_step_follows_role_and_stage(self):
        def row(status, submitted=True, returned=False):
            return {'status': status, 'submitted_at': '2026-10-16' if submitted else None, 'returned_to_pic': returned}

        director, finance, pic = ({'role': role} for role in ('AMIGA_DIRECTOR', 'FINANCE_REVIEWER', 'PIC'))
        self.assertIn('kembalikan ke Finance', chat_search.next_step(director, row('AMIGA_REVIEWED')))
        self.assertNotIn('koreksi', chat_search.next_step(director, row('AMIGA_REVIEWED')))
        self.assertIn('Tidak ada tindakan untuk Finance', chat_search.next_step(finance, row('AMIGA_REVIEWED')))
        self.assertIn('kembalikan ke PIC', chat_search.next_step(finance, row('EXCEPTION')))
        self.assertIn('ajukan ke Finance', chat_search.next_step(pic, row('READY_FOR_REVIEW', submitted=False)))
        self.assertIn('alasan Finance', chat_search.next_step(pic, row('EXCEPTION', submitted=False, returned=True)))
        self.assertEqual(chat_search.next_step(director, row('AMIGA_APPROVED')), chat_search.FINAL_STEP)
        # The PIC hands the final voucher to the client from Hubungi klien (16 Okt 2026); Finance and the Manajer are done.
        self.assertIn('menu Hubungi klien', chat_search.next_step(pic, row('AMIGA_APPROVED')))
        self.assertEqual(chat_search.next_step(finance, row('AMIGA_APPROVED')), chat_search.FINAL_STEP)

    def test_a_voucher_send_is_named_in_the_trail_and_the_prompt(self):
        self.assertEqual(chat_search.ACTION_LABELS['VOUCHER_SENT'], 'Voucher final dikirim ke klien lewat Telegram')
        self.assertEqual(chat_search.ACTION_LABELS['VOUCHER_SEND_FAILED'], 'Pengiriman voucher ke klien belum berhasil')
        # Rule 10 sends every action to the invoice screen; a send to the client happens in its own menu.
        self.assertIn('menu Hubungi klien', chat_agent.INSTRUCTIONS)

    def test_sop_cards_name_their_roles(self):
        self.assertEqual(chat_search.sop_card('TAX_FAKTUR_NOT_FOUND')['kartu'][0]['peran'], ['Finance', 'PIC'])

    def test_tools_are_five_strict_and_read_only(self):
        self.assertEqual([tool['name'] for tool in chat_agent.TOOLS],
                         ['cari_invoice', 'invoice_serupa', 'detail_invoice', 'cari_sop', 'kartu_sop'])
        for tool in chat_agent.TOOLS:
            self.assertTrue(tool['strict'])
            self.assertEqual(tool['parameters']['required'], list(tool['parameters']['properties']))
            self.assertFalse(tool['parameters']['additionalProperties'])

    def test_openai_client_prices_usage_retries_once_and_stores_nothing(self):
        sent, replies = [], [httpx.Response(429, json={'error': {'message': 'slow down'}}),
                             httpx.Response(200, json={'status': 'completed', 'output': [say('Halo')], 'usage': {
                                 'input_tokens': 1000, 'input_tokens_details': {'cached_tokens': 200}, 'output_tokens': 100}})]

        def handler(request):
            sent.append(json.loads(request.content))
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        ledger = MemoryLedger()
        llm = OpenAIChat(ChatConfig('sk-test'), ledger, httpx.MockTransport(handler))
        result = llm.respond({'input': 'halo'}, 'pic_a', time.monotonic() + 25)
        # 800 fresh input tokens at 0.10, 200 cached at 0.01 and 100 output at 0.50 per million.
        self.assertEqual(result['_cost_usd'], Decimal('0.000132'))
        self.assertEqual(ledger.rows, ['FAILED', 'DONE'])
        # A stalled call is retried once; a second stall gives up so the turn can answer by search.
        replies[:] = [httpx.ReadTimeout('stalled'), httpx.Response(200, json={'output': [], 'usage': {
            'input_tokens': 10, 'output_tokens': 1}})]
        llm.respond({'input': 'halo'}, 'pic_a', time.monotonic() + 25)
        replies[:] = [httpx.ReadTimeout('stalled'), httpx.ReadTimeout('stalled again')]
        with self.assertRaises(ChatUnavailable) as stalled:
            llm.respond({'input': 'halo'}, 'pic_a', time.monotonic() + 25)
        self.assertEqual(stalled.exception.reason, 'TIMEOUT')
        self.assertEqual(ledger.rows[2:], ['FAILED', 'DONE', 'FAILED', 'FAILED'])
        self.assertEqual((sent[0]['store'], sent[0]['model']), (False, 'gpt-6-luna'))
        with mock.patch.object(chat_llm, 'PRICE_EXPIRES', date(2000, 1, 1)), self.assertRaises(ChatUnavailable) as caught:
            llm.respond({'input': 'halo'}, 'pic_a', time.monotonic() + 25)
        self.assertEqual(caught.exception.reason, 'PRICE_EXPIRED')

    def test_config_needs_a_key_and_caps_the_budget_at_two_dollars(self):
        path = ROOT / 'app/test-output' / f'chat-{uuid4().hex}.env'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text('AMIGA_LIVE_ENABLED=true\nOPENAI_API_KEY=sk-test\n', encoding='utf-8')
        self.assertEqual(ChatConfig.load(path).stop_usd, Decimal('2.00'))
        path.write_text('AMIGA_LIVE_ENABLED=true\nOPENAI_API_KEY=sk-test\nAMIGA_CHAT_STOP_USD=5\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            ChatConfig.load(path)
        path.write_text('AMIGA_LIVE_ENABLED=false\nOPENAI_API_KEY=sk-test\n', encoding='utf-8')
        self.assertIsNone(ChatConfig.load(path))


class ChatSearchTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def seed(self):
        with self.api.state.db.transaction() as conn:
            return seed_portfolio(conn), director_id(conn)['email']

    def user(self, email):
        self.login(email)
        return self.api.state.db.session(self.client.cookies.get('amiga_session'))

    def test_chat_sees_exactly_the_queue_for_every_role(self):
        ids, director = self.seed()
        for email in ('pic@amiga.local', 'pic.b@amiga.local', 'finance@amiga.local', director):
            with self.subTest(email=email):
                user = self.user(email)
                queue = {item['id'] for item in self.client.get('/api/v1/requests').json()['items']}
                with self.api.state.db.transaction() as conn:
                    chat = {str(row['id']) for row in chat_search.visible_rows(conn, user)}
                self.assertEqual(chat, queue)
        # The director's queue holds signing work only, so an invoice still with the PIC stays closed in the chat too.
        user = self.user(director)
        with self.api.state.db.transaction() as conn:
            self.assertEqual(chat_search.invoice_detail(conn, user, ids['katering']), {'galat': chat_search.NOT_FOUND})
            returned = chat_search.invoice_detail(conn, user, ids['pajak'])
            design = chat_search.search_invoices(conn, user, kata_kunci='desain')
        self.assertEqual(returned['status_label'], 'Dikembalikan ke Finance')
        self.assertIn('Nilai PPN perlu dicek ulang dengan faktur.', [event.get('alasan') for event in returned['riwayat']])
        self.assertEqual({card['id'] for card in design['hasil']}, {ids['logo'], ids['maskot']})

    def test_topic_search_similar_invoices_and_nothing_sensitive_leaves(self):
        ids, _ = self.seed()
        user = self.user('pic@amiga.local')
        with self.api.state.db.transaction() as conn:
            found = chat_search.search_invoices(conn, user, kata_kunci='jasa desain')
            similar = chat_search.similar_invoices(conn, user, ids['logo'])
            detail = chat_search.invoice_detail(conn, user, ids['logo'])
            other_team = chat_search.invoice_detail(conn, user, ids['maskot'])
            waiting = chat_search.search_invoices(conn, user, status='AMIGA_REVIEWED')
            intake = chat_search.search_invoices(conn, user, status='INTAKE')
            biggest = chat_search.search_invoices(conn, user, urutan='terbesar', batas=1)
            by_number = chat_search.invoice_detail(conn, user, ' inv-dsn-01 ')
            other_team_number = chat_search.invoice_detail(conn, user, 'INV-ILU-01')
            yesterday = chat_search.search_invoices(conn, user, kata_kunci='katering', dari_tanggal='2026-10-14')
        self.assertEqual((yesterday['jumlah_cocok'], [card['id'] for card in yesterday['tanpa_filter']['hasil']]),
                         (0, [ids['katering']]))
        self.assertEqual(by_number['id'], ids['logo'])
        self.assertEqual(other_team_number, {'galat': chat_search.NOT_FOUND})
        self.assertEqual({card['id'] for card in found['hasil']}, {ids['logo'], ids['sosmed']})
        self.assertEqual(found['total_semua'], ['Rp 25.700.000'])
        self.assertEqual(similar['hasil'][0]['id'], ids['sosmed'])
        self.assertEqual(other_team, {'galat': chat_search.NOT_FOUND})
        self.assertEqual([card['id'] for card in waiting['hasil']], [ids['mobil']])
        self.assertEqual([card['id'] for card in intake['hasil']], [ids['katering']])
        self.assertEqual(biggest['hasil'][0]['id'], ids['logo'])
        self.assertEqual(detail['nilai_bayar_teks'], 'Rp 18.500.000')
        payload = json.dumps([found, similar, detail, waiting, biggest], ensure_ascii=False)
        for secret in (FAKE_ACCOUNT, FAKE_NPWP, 'Bank Contoh'):
            self.assertNotIn(secret, payload)

    def test_detail_gives_the_sums_finance_decision_and_the_askers_step(self):
        # The SIPLah laptop as the Manajer Keuangan met it on 16 Okt: Finance approved with three checks still open.
        open_checks = [{'code': 'SUBTOTAL_MISMATCH', 'field': None},
                       {'code': 'INSUFFICIENT_CALCULATION_EVIDENCE', 'field': None},
                       {'code': 'TAX_FAKTUR_NOT_FOUND', 'field': 'faktur_number'}]
        data = invoice('2244422/INV/PO6524C45D07EB2', 'SIPLah', ['Laptop'], '7950000') | {
            'stated_subtotal': '7162162.00', 'stated_tax_total': '787838.00', 'stated_other_charges_total': '0.00'}
        with self.api.state.db.transaction() as conn:
            director = director_id(conn)['email']
            finance = conn.execute("SELECT id FROM users WHERE email='finance@amiga.local'").fetchone()['id']
            siplah = seed_invoice(conn, 'client_a', 'pic_a', data, 'AMIGA_REVIEWED',
                                  events=[('REVIEW_APPROVED', finance, 'Catatan review Finance.', {'open_checks': open_checks})],
                                  checks=[{'code': check['code'], 'field': check['field'], 'status': 'FAILED',
                                           'blocking': True, 'message': ''} for check in open_checks])
        user = self.user(director)
        with self.api.state.db.transaction() as conn:
            detail = chat_search.invoice_detail(conn, user, siplah)
        self.assertTrue(detail['cek_angka']['total_cocok'])
        self.assertIn('sudah termasuk PPN', detail['cek_angka']['catatan'][-1])
        # Each open check carries why it does not change the sums, so the chat explains instead of passing a verdict.
        subtotal, missing, faktur = detail['keputusan_finance']['catatan_terbuka']
        self.assertTrue(subtotal.endswith(': harga di baris sudah termasuk PPN, jadi subtotal tetap benar'))
        self.assertTrue(missing.endswith(': diskon tidak tertulis, dan totalnya tetap cocok tanpa diskon'))
        self.assertTrue(faktur.endswith(': pengingat bukti PPN dari faktur pajak, angka invoice tidak terpengaruh'))
        self.assertEqual(detail['kendala_terbuka'], detail['keputusan_finance']['catatan_terbuka'])
        self.assertIn('kembalikan ke Finance', detail['langkah_anda'])
        # Finance's own note stays home: only return reasons leave the server.
        self.assertNotIn('Catatan review Finance.', json.dumps(detail, ensure_ascii=False))
        finance_user = self.user('finance@amiga.local')
        with self.api.state.db.transaction() as conn:
            step = chat_search.invoice_detail(conn, finance_user, siplah)['langkah_anda']
        self.assertIn('Tidak ada tindakan untuk Finance', step)


class ChatTurnTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def seed(self):
        with self.api.state.db.transaction() as conn:
            return seed_portfolio(conn)

    def send(self, llm, **body):
        with mock.patch.object(chat_api, 'make_llm', return_value=llm):
            return self.client.post('/api/v1/chat/messages', json=body)

    def test_conversations_are_remembered_and_private(self):
        ids = self.seed()
        self.login('pic@amiga.local')
        fake = FakeLLM([call('cari_invoice', SEARCH_DESIGN), call('detail_invoice', {'invoice_id': ids['maskot']}, 'call_2')],
                       [say('Ada 2 invoice desain: INV-DSN-01 dan INV-DSN-02.')],
                       [say('INV-DSN-01 sudah disetujui final.')])
        first = self.send(fake, pesan='Invoice jasa desain apa saja?', request_id=ids['mobil'])
        self.assertEqual(first.status_code, 200, first.text)
        reply = first.json()
        self.assertEqual(reply['pesan']['mode'], 'ai')
        self.assertEqual({card['id'] for card in reply['pesan']['invoice']}, {ids['logo'], ids['sosmed']})
        # Round two replays the calls without their status and answers both; team B's invoice only as an error.
        replay = fake.payloads[1]['input']
        outputs = {item['call_id']: json.loads(item['output']) for item in replay if item.get('type') == 'function_call_output'}
        self.assertEqual(outputs['call_2'], {'galat': chat_search.NOT_FOUND})
        self.assertTrue(all('status' not in item for item in replay if item.get('type') == 'function_call'))
        self.assertIn('<konteks_layar>', fake.payloads[0]['input'][-1]['content'])
        self.assertNotIn('<konteks_layar>', fake.payloads[0]['instructions'])
        self.assertNotIn(FAKE_ACCOUNT, json.dumps(fake.payloads))
        thread = reply['thread']['id']
        second = self.send(fake, pesan='Yang pertama sudah disetujui?', thread_id=thread)
        self.assertEqual(second.status_code, 200, second.text)
        asked, answered = (item['content'] for item in fake.payloads[2]['input'][:2])
        self.assertEqual(asked, 'Invoice jasa desain apa saja?')
        self.assertTrue(answered.startswith('Ada 2 invoice desain: INV-DSN-01 dan INV-DSN-02.\n[Kartu invoice yang tampil: '))
        self.assertIn(f"INV-DSN-01 · PT Kreasi Visual Nusantara · Rp 18.500.000 · Disetujui final · id {ids['logo']}", answered)
        self.assertEqual([(t['id'], t['judul']) for t in self.client.get('/api/v1/chat/threads').json()['threads']],
                         [(thread, 'Invoice jasa desain apa saja?')])
        self.assertEqual(len(self.client.get(f'/api/v1/chat/threads/{thread}').json()['pesan']), 4)
        # Another user can neither read nor continue the conversation.
        self.login('pic.b@amiga.local')
        self.assertEqual(self.client.get(f'/api/v1/chat/threads/{thread}').status_code, 404)
        self.assertEqual(self.send(FakeLLM(), pesan='Lanjut', thread_id=thread).status_code, 404)
        self.assertEqual(self.client.get('/api/v1/chat/threads').json()['threads'], [])

    def test_history_cards_show_the_current_status(self):
        # A card answered while the invoice waited must not keep saying so next to its final voucher.
        ids = self.seed()
        self.login('pic@amiga.local')
        fake = FakeLLM([call('detail_invoice', {'invoice_id': ids['mobil']})], [say('INV-SWA-01 menunggu manajer keuangan.')])
        reply = self.send(fake, pesan='Sewa mobil sudah sampai mana?').json()
        self.assertEqual([card['status_label'] for card in reply['pesan']['invoice']], ['Menunggu manajer keuangan'])
        with self.api.state.db.transaction() as conn:
            conn.execute("UPDATE requests SET status='AMIGA_APPROVED' WHERE id=%s", (ids['mobil'],))
        thread = reply['thread']['id']
        shown = self.client.get(f'/api/v1/chat/threads/{thread}').json()['pesan'][1]['invoice']
        self.assertEqual([card['status_label'] for card in shown], ['Disetujui final'])
        later = FakeLLM([say('Sudah disetujui final.')])
        self.send(later, pesan='Sekarang bagaimana?', thread_id=thread)
        self.assertIn('Disetujui final', later.payloads[0]['input'][1]['content'])

    def test_sop_citations_search_fallback_busy_guard_and_budget(self):
        ids = self.seed()
        self.login('pic.b@amiga.local')
        fake = FakeLLM([call('kartu_sop', {'kode': 'BANK_MISMATCH'})],
                       [say('1. Cocokkan rekening dengan data vendor. [EXC-BANK_MISMATCH]')])
        cited = self.send(fake, pesan='Rekening vendor beda, saya harus apa?').json()['pesan']
        self.assertEqual([ref['sop_id'] for ref in cited['sop']], ['EXC-BANK_MISMATCH'])
        self.assertEqual(cited['peringatan'], [])
        offline = self.send(None, pesan='desain kemasan').json()['pesan']
        self.assertEqual((offline['mode'], [card['id'] for card in offline['invoice']]), ('cari', [ids['maskot']]))
        slow = self.send(FakeLLM(ChatUnavailable('TIMEOUT')), pesan='perawatan AC').json()['pesan']
        self.assertIn('lambat', slow['isi'])
        self.assertEqual([card['id'] for card in slow['invoice']], [ids['ac']])
        with mock.patch.object(chat_api, 'make_llm', return_value=None):
            self.assertEqual(self.client.get('/api/v1/chat/threads').json()['mode'], 'cari')
        user = self.api.state.db.session(self.client.cookies.get('amiga_session'))
        with chat_api.one_turn(user['id']):
            self.assertEqual(self.send(None, pesan='desain').status_code, 409)
        # The ledger keeps a failed call's reservation and refuses the call that would cross the cap.
        db = self.api.state.db
        with db.transaction() as conn:
            conn.execute('CREATE TABLE chat_usage (LIKE public.chat_usage INCLUDING ALL)')
        ledger = Ledger(db, ('chat_usage',))
        ledger.finish(ledger.reserve('pic_b', Decimal('0.60'), Decimal('1.00')), 'DONE',
                      {'input_tokens': 10, 'output_tokens': 5}, Decimal('0.10'))
        ledger.finish(ledger.reserve('pic_b', Decimal('0.60'), Decimal('1.00')), 'FAILED')
        with self.assertRaises(ChatUnavailable) as caught:
            ledger.reserve('pic_b', Decimal('0.31'), Decimal('1.00'))
        self.assertEqual(caught.exception.reason, 'BUDGET')
        self.assertEqual(ledger.spent(), Decimal('0.70'))


if __name__ == '__main__':
    unittest.main()
