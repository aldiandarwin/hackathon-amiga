"""Hubungi klien: a PIC sends a final voucher to a client's Telegram contact through an n8n webhook (no live call)."""

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

import httpx

from app import handover_api, handover_n8n
from app.chat_search import WIB
from app.tests import test_signoff as signoff

CHAT_ID = '987654321'
WEBHOOK = 'https://n8n.example.test/webhook/amiga-voucher-final'


class HandoverConfigTests(unittest.TestCase):
    def test_config_needs_an_https_webhook_and_a_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('OPENAI_MODEL=gpt-6-luna\n', encoding='utf-8')
            self.assertIsNone(handover_n8n.HandoverConfig.load(path))
            path.write_text(f'AMIGA_N8N_VOUCHER_WEBHOOK_URL={WEBHOOK}\nAMIGA_N8N_WEBHOOK_SECRET=rahasia-uji\n',
                            encoding='utf-8')
            config = handover_n8n.HandoverConfig.load(path)
            self.assertEqual(config.webhook_url, WEBHOOK)
            self.assertNotIn('rahasia-uji', repr(config))
            # Plain http only to a local n8n; anywhere else the voucher would cross the network unencrypted.
            path.write_text('AMIGA_N8N_VOUCHER_WEBHOOK_URL=http://n8n.example.test/webhook/x\n'
                            'AMIGA_N8N_WEBHOOK_SECRET=rahasia-uji\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                handover_n8n.HandoverConfig.load(path)
            path.write_text('AMIGA_N8N_VOUCHER_WEBHOOK_URL=http://localhost:5678/webhook/x\n'
                            'AMIGA_N8N_WEBHOOK_SECRET=rahasia-uji\n', encoding='utf-8')
            self.assertEqual(handover_n8n.HandoverConfig.load(path).webhook_url, 'http://localhost:5678/webhook/x')

    def test_caption_is_plain_escaped_and_short(self):
        text = handover_api.caption({'number': 'ARS-00001-10-2026', 'client': 'PT Arunika Sejahtera',
                                     'invoice': 'INV/01', 'vendor': 'CV Maju & Jaya <Cabang>', 'amount': 'Rp 1.000',
                                     'approved': '16 Oktober 2026, 09.12 WIB', 'sender': 'Dian Pratama',
                                     'title': 'Admin Intake AMIGA'})
        self.assertIn('CV Maju &amp; Jaya &lt;Cabang&gt;', text)
        self.assertNotIn('—', text)
        self.assertLessEqual(len(text), 1024)
        long = handover_api.caption({'number': 'A', 'client': 'B', 'invoice': 'C', 'vendor': 'V' * 3000, 'amount': 'D',
                                     'approved': 'E', 'sender': 'F', 'title': 'G'})
        self.assertLessEqual(len(long), 1024)


class HandoverTests(unittest.TestCase):
    login = signoff.SignoffAcceptanceTests.login
    sample = signoff.SignoffAcceptanceTests.sample
    detail = signoff.SignoffAcceptanceTests.detail
    pic_submit = signoff.SignoffAcceptanceTests.pic_submit
    forbid_live = staticmethod(signoff.fixtures.DatabaseAcceptanceTests.forbid_live)
    submitted = signoff.SignoffAcceptanceTests.submitted
    approve = signoff.SignoffAcceptanceTests.approve
    signed_by_finance = signoff.SignoffAcceptanceTests.signed_by_finance
    director_approve = signoff.SignoffAcceptanceTests.director_approve
    signed_pdf = signoff.SignoffAcceptanceTests.signed_pdf

    def setUp(self):
        # Every test runs against a fake n8n. The real webhook in .env is never reached, also not by a mistake.
        self.connected, self.calls = True, []
        self.reply = lambda request: httpx.Response(200, json={'ok': True, 'message_id': 4242, 'chat_id': CHAT_ID})
        patcher = mock.patch.object(handover_api, 'make_sender', side_effect=self.fake_sender)
        patcher.start()
        self.addCleanup(patcher.stop)
        # The demo recipient in the real .env stays out of every test that does not ask for it.
        self.default_chat = None
        default = mock.patch.object(handover_api, 'default_chat_id', side_effect=lambda: self.default_chat)
        default.start()
        self.addCleanup(default.stop)
        signoff.fixtures.DatabaseAcceptanceTests.setUp(self)

    def fake_sender(self):
        if not self.connected:
            return None

        def handler(request):
            self.calls.append(request)
            return self.reply(request)
        config = handover_n8n.HandoverConfig(WEBHOOK, 'rahasia-uji')
        return handover_n8n.N8nSender(config, transport=httpx.MockTransport(handler))

    def final_voucher(self):
        identifier = self.signed_by_finance()
        self.login(signoff.MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())  # renders the signed copy
        self.login('pic@amiga.local')
        return identifier

    def add_contact(self, client='client_a', name='Bu Rina, Keuangan klien', chat_id=CHAT_ID):
        return self.client.post('/api/v1/handover/contacts',
                                json={'client_id': client, 'name': name, 'telegram_chat_id': chat_id})

    def contact(self, **kwargs):
        response = self.add_contact(**kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['contact']['id']

    def send(self, identifier, contact_id):
        return self.client.post('/api/v1/handover/send', json={'request_id': identifier, 'contact_id': contact_id})

    def rows(self, query, *params):
        with self.api.state.db.transaction() as conn:
            return conn.execute(query, params).fetchall()

    def test_every_client_starts_with_the_default_recipient_once(self):
        self.login('pic@amiga.local')
        mine = {client['id'] for client in self.client.get('/api/v1/session').json()['clients']}
        self.assertFalse(self.client.get('/api/v1/handover').json()['contacts'])  # unset: nothing is added
        self.default_chat = '555000111'
        first = [c for c in self.client.get('/api/v1/handover').json()['contacts'] if c['chat_id_masked'] == '••••0111']
        self.assertEqual({c['client_id'] for c in first}, mine)
        self.assertEqual({c['name'] for c in first}, {handover_api.DEFAULT_RECIPIENT})
        self.assertEqual(len(first), len(mine))
        self.assertEqual(len(self.client.get('/api/v1/handover').json()['contacts']), len(mine))  # not twice
        # A PIC who turns it off keeps it off.
        off = self.client.post(f"/api/v1/handover/contacts/{first[0]['id']}/disable")
        self.assertEqual(off.status_code, 200)
        again = self.client.get('/api/v1/handover').json()['contacts']
        self.assertNotIn(first[0]['client_id'], {c['client_id'] for c in again})
        events = self.rows("SELECT changes FROM client_events WHERE action='CONTACT_ADDED'")
        self.assertEqual(len(events), len(mine))
        self.assertTrue(all(row['changes']['default'] for row in events))

    def test_pic_sends_the_final_voucher_and_the_invoice_stays_approved(self):
        identifier = self.final_voucher()
        pdf = self.signed_pdf(identifier).content
        response = self.send(identifier, self.contact())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()['status'], response.json()['message_id']), ('SENT', '4242'))
        [call] = self.calls
        self.assertEqual(call.headers['x-amiga-secret'], 'rahasia-uji')
        body = json.loads(call.content)
        [voucher] = self.rows('SELECT number FROM vouchers WHERE request_id=%s AND superseded_at IS NULL', identifier)
        [step] = self.rows("SELECT signed_at FROM approval_steps WHERE request_id=%s AND kind='DIRECTOR_APPROVED'",
                           identifier)
        self.assertEqual(body['chat_id'], CHAT_ID)
        self.assertEqual(body['client'], {'code': 'ARS', 'name': 'PT Arunika Sejahtera'})
        self.assertEqual(body['voucher']['number'], voucher['number'])
        # The Manajer Keuangan's approval, not Finance's: the payload's own approved_at is the Finance step.
        self.assertEqual(body['voucher']['approved_at'], step['signed_at'].astimezone(WIB).isoformat())
        self.assertEqual(base64.b64decode(body['file']['base64']), pdf)
        self.assertEqual((body['file']['name'], body['file']['mime']), (voucher['number'] + '-final.pdf', 'application/pdf'))
        self.assertIn(voucher['number'], body['caption'])
        self.assertEqual(self.detail(identifier)['status'], 'AMIGA_APPROVED')
        [delivery] = self.rows('SELECT status, provider_message_id FROM voucher_deliveries WHERE request_id=%s', identifier)
        self.assertEqual((delivery['status'], delivery['provider_message_id']), ('SENT', '4242'))
        [event] = self.rows("SELECT changes FROM audit_events WHERE request_id=%s AND action='VOUCHER_SENT'", identifier)
        # Finance and the Manajer read the trail too, so it keeps only the last digits of the chat id.
        self.assertNotIn(CHAT_ID, json.dumps(event['changes']))
        self.assertIn(CHAT_ID[-4:], json.dumps(event['changes']))
        listed = self.client.get('/api/v1/handover').json()
        [row] = listed['vouchers']
        self.assertEqual((row['request_id'], row['last_delivery']['status'], row['last_delivery']['contact_name']),
                         (identifier, 'SENT', 'Bu Rina, Keuangan klien'))

    def test_the_list_holds_only_final_vouchers_of_assigned_clients(self):
        identifier = self.final_voucher()
        self.submitted('wrong_total')  # another invoice, still with Finance; the same file would reopen the first
        self.login('pic@amiga.local')
        listed = self.client.get('/api/v1/handover').json()
        self.assertTrue(listed['connected'])
        self.assertEqual([row['request_id'] for row in listed['vouchers']], [identifier])
        contact_id = self.contact()
        self.login('pic.b@amiga.local')
        self.assertEqual(self.client.get('/api/v1/handover').json()['vouchers'], [])
        response = self.send(identifier, contact_id)
        self.assertEqual((response.status_code, response.json()['code']), (404, 'NOT_FOUND'))
        self.assertEqual(self.calls, [])

    def test_finance_and_the_manager_cannot_use_it(self):
        identifier = self.final_voucher()
        contact_id = self.contact()
        for email in ('finance@amiga.local', signoff.MANAGER):
            for connected in (True, False):
                with self.subTest(email=email, connected=connected):
                    self.connected = connected
                    self.login(email)
                    self.assertEqual(self.client.get('/api/v1/handover').status_code, 403)
                    self.assertEqual(self.add_contact().status_code, 403)
                    self.assertEqual(self.client.post(f'/api/v1/handover/contacts/{contact_id}/disable').status_code, 403)
                    response = self.send(identifier, contact_id)
                    self.assertEqual((response.status_code, response.json()['code']), (403, 'FORBIDDEN'))
        self.assertEqual(self.calls, [])

    def test_a_voucher_that_is_not_final_is_refused(self):
        identifier = self.signed_by_finance()
        self.login('pic@amiga.local')
        response = self.send(identifier, self.contact())
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VOUCHER_NOT_SIGNED'))
        self.assertEqual(self.rows('SELECT id FROM voucher_deliveries'), [])
        self.assertEqual(self.calls, [])

    def test_without_n8n_settings_nothing_is_sent(self):
        identifier = self.final_voucher()
        contact_id = self.contact()
        self.connected = False
        self.assertFalse(self.client.get('/api/v1/handover').json()['connected'])
        response = self.send(identifier, contact_id)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'HANDOVER_NOT_CONFIGURED'))
        self.assertEqual(self.calls, [])

    def test_a_refused_delivery_is_recorded_as_failed(self):
        identifier = self.final_voucher()
        contact_id = self.contact()
        replies = {'n8n error': httpx.Response(502, json={'ok': False}),
                   'not ok': httpx.Response(200, json={'ok': False}),
                   'no message id': httpx.Response(200, json={'ok': True}),
                   'not json': httpx.Response(200, text='<html>')}
        for label, reply in replies.items():
            with self.subTest(label):
                self.reply = lambda request, reply=reply: reply
                response = self.send(identifier, contact_id)
                self.assertEqual((response.status_code, response.json()['code']), (424, 'HANDOVER_FAILED'))

        def refused(request):
            raise httpx.ConnectError('refused', request=request)
        self.reply = refused
        self.assertEqual(self.send(identifier, contact_id).json()['code'], 'HANDOVER_FAILED')
        statuses = [row['status'] for row in self.rows('SELECT status FROM voucher_deliveries WHERE request_id=%s',
                                                         identifier)]
        self.assertEqual(statuses, ['FAILED'] * 5)
        self.assertEqual(len(self.rows("SELECT id FROM audit_events WHERE request_id=%s AND action='VOUCHER_SEND_FAILED'",
                                       identifier)), 5)
        self.assertEqual(self.detail(identifier)['status'], 'AMIGA_APPROVED')

    def test_a_timeout_leaves_the_delivery_uncertain(self):
        identifier = self.final_voucher()

        def stalled(request):
            raise httpx.ReadTimeout('stalled', request=request)
        self.reply = stalled
        response = self.send(identifier, self.contact())
        # n8n may still deliver after the cut, so the PIC checks Telegram before sending again.
        self.assertEqual((response.status_code, response.json()['code']), (424, 'HANDOVER_UNCERTAIN'))
        [delivery] = self.rows('SELECT status FROM voucher_deliveries WHERE request_id=%s', identifier)
        self.assertEqual(delivery['status'], 'UNCERTAIN')
        [row] = self.client.get('/api/v1/handover').json()['vouchers']
        self.assertEqual(row['last_delivery']['status'], 'UNCERTAIN')

    def test_one_delivery_at_a_time_per_voucher(self):
        identifier = self.final_voucher()
        contact_id = self.contact()
        [voucher] = self.rows('SELECT v.id, r.approved_version FROM vouchers v JOIN requests r ON r.id=v.request_id '
                              'WHERE v.request_id=%s AND v.superseded_at IS NULL', identifier)
        pending = str(uuid4())
        with self.api.state.db.transaction() as conn:
            conn.execute("INSERT INTO voucher_deliveries(id,request_id,voucher_id,invoice_version,contact_id,pdf_sha256,"
                         "status,sent_by) VALUES (%s,%s,%s,%s,%s,%s,'SENDING','pic_a')",
                         (pending, identifier, voucher['id'], voucher['approved_version'], contact_id, '0' * 64))
        response = self.send(identifier, contact_id)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'HANDOVER_BUSY'))
        self.assertEqual(self.calls, [])
        # A send that never came back (a restart, a lost connection) stops blocking after two minutes.
        with self.api.state.db.transaction() as conn:
            conn.execute("UPDATE voucher_deliveries SET created_at=now()-interval '3 minutes' WHERE id=%s", (pending,))
        self.assertEqual(self.send(identifier, contact_id).status_code, 200)
        [stale] = self.rows('SELECT status FROM voucher_deliveries WHERE id=%s', pending)
        self.assertEqual(stale['status'], 'UNCERTAIN')

    def test_contacts_are_checked_and_kept_per_client(self):
        identifier = self.final_voucher()
        for chat_id in ('abc', '12', '9' * 25):
            response = self.add_contact(chat_id=chat_id)
            self.assertEqual((response.status_code, response.json().get('field')), (422, 'telegram_chat_id'))
        self.assertEqual(self.add_contact(name=' ').json().get('field'), 'name')
        first, again = self.contact(), self.contact()
        self.assertEqual(first, again)
        group = self.contact(name='Grup keuangan klien', chat_id='-1001234567890')
        self.assertNotEqual(group, first)
        self.assertEqual(self.add_contact(client='client_b').status_code, 404)  # team B's client
        other = self.contact(client='client_a02', chat_id='555666777')
        self.assertEqual(self.send(identifier, other).status_code, 404)  # a contact of another client
        self.assertEqual(self.client.post(f'/api/v1/handover/contacts/{first}/disable').status_code, 200)
        self.assertEqual(self.send(identifier, first).status_code, 404)
        self.assertNotIn(first, [contact['id'] for contact in self.client.get('/api/v1/handover').json()['contacts']])
        events = [row['action'] for row in self.rows("SELECT action FROM client_events WHERE client_id='client_a' "
                                                     "AND action LIKE 'CONTACT_%%' ORDER BY id")]
        self.assertEqual(events, ['CONTACT_ADDED', 'CONTACT_ADDED', 'CONTACT_DISABLED'])
        self.api.state.db.initialize()  # the schema block runs again on every start
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
