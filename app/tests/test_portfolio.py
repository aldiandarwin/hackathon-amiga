"""Portfolios: two teams of a PIC and a Finance reviewer hold ten clients each, AMIGA's director holds all (no live API)."""

from datetime import datetime, timezone
import unittest
from uuid import uuid4

import psycopg

from app.database import CLIENTS
from app.review import voucher_number
from app.tests import test_app as fixtures


TEAM_A = {client[0] for client in CLIENTS if client[5] == 'A'}
TEAM_B = {client[0] for client in CLIENTS if client[5] == 'B'}


class PortfolioTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    sample = fixtures.DatabaseAcceptanceTests.sample
    pic_submit = fixtures.DatabaseAcceptanceTests.pic_submit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def clients_of(self, email):
        self.login(email)
        return [client['id'] for client in self.client.get('/api/v1/session').json()['clients']]

    def test_two_teams_hold_ten_clients_each_and_the_bod_all_twenty(self):
        self.assertEqual((len(TEAM_A), len(TEAM_B)), (10, 10))
        for email, team in (('pic@amiga.local', TEAM_A), ('finance@amiga.local', TEAM_A),
                            ('pic.b@amiga.local', TEAM_B), ('finance.b@amiga.local', TEAM_B)):
            with self.subTest(email=email):
                self.assertEqual(set(self.clients_of(email)), team)
        self.assertEqual(set(self.clients_of('manajer.keuangan@amiga.local')), TEAM_A | TEAM_B)

    def test_every_seeded_client_has_code_city_sector_team_and_the_demo_vendor(self):
        with self.api.state.db.transaction() as conn:
            rows = conn.execute('SELECT c.id,c.name,c.code,c.city,c.sector,c.team,v.id AS vendor FROM clients c '
                                "LEFT JOIN vendors v ON v.client_id=c.id AND v.id='vendor_demo'").fetchall()
        self.assertEqual((len(rows), len({row['code'] for row in rows})), (20, 20))
        for row in rows:
            with self.subTest(client=row['id']):
                self.assertRegex(row['code'], r'^[A-Z]{3}$')
                self.assertRegex(row['name'], r'^(PT|CV) ')
                self.assertTrue(row['city'] and row['sector'])
                self.assertIn(row['team'], ('A', 'B'))
                self.assertEqual(row['vendor'], 'vendor_demo')

    def test_restart_renames_the_first_two_clients_once_and_keeps_later_renames(self):
        # The demo database of 15 Oct still carries the first two clients under their old names.
        db = self.api.state.db
        with db.transaction() as conn:
            conn.execute("UPDATE clients SET name='Arunika Sejahtera' WHERE id='client_a'")
            conn.execute("UPDATE clients SET name='Bumi Persada Konstruksi' WHERE id='client_b'")
        db.initialize()
        with db.transaction() as conn:
            names = {row['id']: row['name'] for row in
                     conn.execute("SELECT id,name FROM clients WHERE id IN ('client_a','client_b')").fetchall()}
        self.assertEqual(names, {'client_a': 'PT Arunika Sejahtera', 'client_b': 'Bumi Persada Konstruksi'})

    def test_queue_without_client_id_lists_every_assigned_client(self):
        self.login('pic@amiga.local')
        first, second = self.sample('normal'), self.sample('normal', client='client_a02')
        response = self.client.get('/api/v1/requests')
        self.assertEqual(response.status_code, 200, response.text)
        rows = {str(item['id']): item for item in response.json()['items']}
        self.assertEqual(set(rows), {first, second})
        self.assertEqual((rows[second]['client_id'], rows[second]['client_name']), ('client_a02', 'PT Sinar Kalingga Logistik'))
        self.login('pic.b@amiga.local')
        self.assertEqual(self.client.get('/api/v1/requests').json()['items'], [])

    def test_another_team_cannot_read_or_upload_to_a_client(self):
        self.login('pic@amiga.local')
        identifier = self.sample('normal', client='client_a02')
        self.login('pic.b@amiga.local')
        self.assertEqual(self.client.get('/api/v1/requests?client_id=client_a02').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/requests/' + identifier).status_code, 404)
        response = self.client.post('/api/v1/demo/normal?client_id=client_a02', headers={'Idempotency-Key': str(uuid4())})
        self.assertEqual(response.status_code, 404)

    def test_voucher_number_uses_the_client_code(self):
        self.assertEqual(voucher_number('client_a02', 1, datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc), 'SKL'),
                         'SKL-00001-10-2026')
        self.login('pic@amiga.local')
        identifier = self.sample('normal', client='client_a02')
        self.pic_submit(identifier)
        self.login('finance@amiga.local')
        response = self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': 1, 'source_reviewed': True, 'reason': 'Dokumen sintetis diperiksa seluruh halaman',
            'password': 'test-password-only', 'consent': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertRegex(response.json()['voucher']['number'], r'^SKL-00001-\d{2}-\d{4}$')


class ClientCreationTests(unittest.TestCase):
    """A PIC opens a new client, for example the eleventh, for the team and AMIGA's director."""
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    sample = fixtures.DatabaseAcceptanceTests.sample
    pic_submit = fixtures.DatabaseAcceptanceTests.pic_submit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)
    clients_of = PortfolioTests.clients_of

    def create(self, **fields):
        payload = {'name': 'CV Sinar Baru Teknik', 'city': 'Bandung', 'sector': 'Servis mesin industri'} | fields
        return self.client.post('/api/v1/clients', json=payload)

    def test_pic_creates_a_client_for_the_team_and_the_bod(self):
        self.login('pic@amiga.local')
        response = self.create(code='SBT')
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual((body['client']['id'], body['client']['code'], body['client']['team']), ('client_sbt', 'SBT', 'A'))
        self.assertEqual(set(body['members']), {'Dian Pratama', 'Nadia Putri', 'Bagas Wiratama'})
        for email, holds in (('pic@amiga.local', True), ('finance@amiga.local', True), ('manajer.keuangan@amiga.local', True),
                             ('pic.b@amiga.local', False), ('finance.b@amiga.local', False)):
            with self.subTest(email=email):
                self.assertEqual('client_sbt' in self.clients_of(email), holds)
        self.assertEqual(self.client.get('/api/v1/requests?client_id=client_sbt').status_code, 404)
        with self.api.state.db.transaction() as conn:
            row = conn.execute("SELECT created_by,created_at FROM clients WHERE id='client_sbt'").fetchone()
            event = conn.execute("SELECT actor_id,action,changes FROM client_events WHERE client_id='client_sbt'").fetchone()
        self.assertEqual(row['created_by'], 'pic_a')
        self.assertIsNotNone(row['created_at'])
        self.assertEqual((event['actor_id'], event['action'], event['changes']['code']), ('pic_a', 'CLIENT_CREATED', 'SBT'))

    def test_new_client_validation_and_unique_name_and_code(self):
        self.login('pic@amiga.local')
        for fields, code in (({'name': 'Sinar Baru Teknik'}, 'INVALID_PAYLOAD'), ({'npwp': '12.345.678'}, 'INVALID_PAYLOAD'),
                             ({'code': 'S1'}, 'INVALID_PAYLOAD'), ({'name': 'pt arunika sejahtera'}, 'INVALID_PAYLOAD'),
                             ({'name': 'PT Arunika  Sejahtera'}, 'CLIENT_EXISTS'), ({'code': 'ARS'}, 'CLIENT_EXISTS')):
            with self.subTest(fields=fields):
                response = self.create(**fields)
                self.assertEqual(response.json()['code'], code)
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM clients').fetchone()['n'], 20)

    def test_only_a_pic_creates_clients(self):
        for email in ('finance@amiga.local', 'manajer.keuangan@amiga.local'):
            with self.subTest(email=email):
                self.login(email)
                self.assertEqual(self.create().status_code, 403)

    def test_a_suggested_code_carries_through_to_the_voucher(self):
        self.login('pic.b@amiga.local')
        response = self.create(name='PT Nusantara Jaya Abadi', city='Surabaya')
        self.assertEqual(response.status_code, 201, response.text)
        client = response.json()['client']
        self.assertEqual((client['code'], client['team']), ('NJA', 'B'))
        identifier = self.sample('normal', client=client['id'])
        self.pic_submit(identifier)
        self.login('finance.b@amiga.local')
        response = self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': 1, 'source_reviewed': True, 'reason': 'Dokumen sintetis diperiksa seluruh halaman',
            'password': 'test-password-only', 'consent': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertRegex(response.json()['voucher']['number'], r'^NJA-00001-\d{2}-\d{4}$')

    def test_client_events_are_append_only(self):
        self.login('pic@amiga.local')
        self.assertEqual(self.create().status_code, 201)
        for statement in ("UPDATE client_events SET action='CHANGED'", 'DELETE FROM client_events'):
            with self.subTest(statement=statement), self.assertRaises(psycopg.errors.RaiseException), \
                    self.api.state.db.transaction() as conn:
                conn.execute(statement)


if __name__ == '__main__':
    unittest.main()
