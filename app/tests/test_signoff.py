"""Two-stage approval: Finance approves, AMIGA's Manajer Keuangan approves or returns (no live API)."""

from copy import deepcopy
import hashlib
from io import BytesIO
from html.parser import HTMLParser
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from pypdf import PdfReader
import psycopg

from app.database import CLIENTS
from app.tests import test_app as fixtures


# "Disetujui Oleh" is AMIGA's Manajer Keuangan since 15 Oct (the BOD before), one account for every client. The client
# approves payment outside. The role code stays AMIGA_DIRECTOR.
MANAGER = 'manajer.keuangan@amiga.local'
# Since the portfolios of 15 Oct the final approver holds all twenty seeded clients, in byte order like directors() below.
EVERY_CLIENT = ','.join(sorted(client[0] for client in CLIENTS))


class SignoffAcceptanceTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    sample = fixtures.DatabaseAcceptanceTests.sample
    detail = fixtures.DatabaseAcceptanceTests.detail
    edit = fixtures.DatabaseAcceptanceTests.edit
    pic_submit = fixtures.DatabaseAcceptanceTests.pic_submit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def submitted(self, name='normal'):
        self.login('pic@amiga.local')
        identifier = self.sample(name)
        self.pic_submit(identifier)
        self.login('finance@amiga.local')
        return identifier

    def approve(self, identifier, version=1, **overrides):
        payload = dict(expected_version=version, source_reviewed=True, reason='Dokumen sintetis diperiksa seluruh halaman',
                       password='test-password-only', consent=True)
        payload.update(overrides)
        return self.client.post('/api/v1/requests/' + identifier + '/review', json=payload)

    def steps(self, identifier):
        with self.api.state.db.transaction() as conn:
            return conn.execute('SELECT * FROM approval_steps WHERE request_id=%s ORDER BY signed_at',
                                (identifier,)).fetchall()

    def voucher_row(self, identifier):
        with self.api.state.db.transaction() as conn:
            return conn.execute('SELECT * FROM vouchers WHERE request_id=%s AND superseded_at IS NULL',
                                (identifier,)).fetchone()

    def test_reviewer_signature_requires_consent_and_the_password_at_that_moment(self):
        identifier = self.submitted()
        response = self.approve(identifier, consent=False)
        self.assertEqual((response.status_code, response.json()['code']), (422, 'CONSENT_REQUIRED'))
        response = self.approve(identifier, password='kata-sandi-salah')
        # 403, not 401: the page logs the user out on any 401.
        self.assertEqual((response.status_code, response.json()['code']), (403, 'SIGNATURE_PASSWORD_INVALID'))
        self.assertEqual(self.detail(identifier)['status'], 'READY_FOR_REVIEW')
        self.assertEqual(self.steps(identifier), [])
        with self.api.state.db.transaction() as conn:
            failed = conn.execute("SELECT changes FROM audit_events WHERE request_id=%s AND action='SIGN_FAILED'",
                                  (identifier,)).fetchall()
        self.assertEqual(len(failed), 1)
        self.assertNotIn('kata-sandi-salah', json.dumps(failed[0]['changes']))

    def test_reviewer_signature_is_frozen_in_the_voucher_and_the_step(self):
        identifier = self.submitted()
        response = self.approve(identifier)
        self.assertEqual(response.status_code, 200, response.text)
        # Brief p6/p9: the draft voucher still follows the Finance approval directly.
        self.assertEqual(response.json()['voucher']['render_status'], 'PENDING')
        [step] = self.steps(identifier)
        voucher = self.voucher_row(identifier)
        signature = voucher['payload']['signatures']['reviewer']
        self.assertEqual((step['kind'], step['actor_id'], step['voucher_id']),
                         ('REVIEWER_SIGNED', 'finance_a', voucher['id']))
        self.assertEqual((signature['name'], signature['title'], signature['code']),
                         ('Nadia Putri', 'Finance Reviewer AMIGA', step['verification_code']))
        self.assertEqual(voucher['payload']['assigned_director'],
                         {'name': 'Bagas Wiratama', 'title': 'Manajer Keuangan AMIGA'})
        # v7 prints the PIC who submitted in the first box, frozen with the voucher.
        submitter = voucher['payload']['submitter']
        self.assertEqual((submitter['id'], submitter['name'], submitter['title']),
                         ('pic_a', 'Dian Pratama', 'Admin Intake AMIGA'))
        # The hash covers the voucher content without the signature block, in canonical JSON.
        content = {key: value for key, value in voucher['payload'].items() if key != 'signatures'}
        canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(step['content_sha256'], hashlib.sha256(canonical).hexdigest())
        self.assertEqual(step['auth_method'], 'PASSWORD_REENTRY')
        self.assertIn('dokumen asli', step['consent_text'])

    def test_double_click_signs_once(self):
        identifier = self.submitted()
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertEqual(len(self.steps(identifier)), 1)

    def test_signature_history_is_append_only(self):
        identifier = self.submitted()
        self.assertEqual(self.approve(identifier).status_code, 200)
        for statement in ("UPDATE approval_steps SET signer_name='X'", 'DELETE FROM approval_steps'):
            with self.subTest(statement=statement), self.assertRaises(psycopg.errors.RaiseException), \
                    self.api.state.db.transaction() as conn:
                conn.execute(statement)

    def test_repeated_wrong_signing_passwords_are_rate_limited(self):
        identifier = self.submitted()
        codes = [self.approve(identifier, password=f'salah-{attempt}').json()['code'] for attempt in range(6)]
        self.assertEqual(codes, ['SIGNATURE_PASSWORD_INVALID'] * 5 + ['SIGNATURE_RATE_LIMIT'])
        self.assertEqual(self.approve(identifier).status_code, 429)

    def test_a_good_signature_clears_earlier_wrong_passwords(self):
        # Like the login limit: typos before a good signature do not count against the next signature.
        identifier = self.submitted()
        for attempt in range(4):
            self.assertEqual(self.approve(identifier, password=f'salah-{attempt}').status_code, 403)
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertEqual(self.approve(identifier, password='salah-lagi').status_code, 403)
        self.assertEqual(self.approve(identifier).status_code, 200)  # a replay; 429 if the typos still counted

    def signed_by_finance(self):
        identifier = self.submitted()
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())  # renders the draft voucher
        return identifier

    def director_approve(self, identifier, version=1, **overrides):
        payload = dict(expected_version=version, password='test-password-only', consent=True)
        payload.update(overrides)
        return self.client.post(f'/api/v1/requests/{identifier}/director-approval', json=payload)

    def director_return(self, identifier, version=1, reason='Nominal PPN perlu dicek ulang dengan vendor'):
        return self.client.post(f'/api/v1/requests/{identifier}/director-return',
                                json={'expected_version': version, 'reason': reason})

    def signed_pdf(self, identifier, version=1):
        return self.client.get(f'/api/v1/requests/{identifier}/voucher/signed?version={version}')

    @staticmethod
    def text(data):
        return ' '.join(' '.join(page.extract_text() for page in PdfReader(BytesIO(data)).pages).split())

    def test_director_approval_chains_steps_and_renders_signed_pdf(self):
        identifier = self.signed_by_finance()
        draft = self.voucher_row(identifier)
        self.login(MANAGER)
        response = self.director_approve(identifier)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'AMIGA_APPROVED')
        reviewer, director = self.steps(identifier)
        self.assertEqual((director['kind'], director['actor_id'], director['previous_step_id']),
                         ('DIRECTOR_APPROVED', 'direksi_a', reviewer['id']))
        self.assertEqual(director['content_sha256'], reviewer['content_sha256'])
        self.assertEqual(director['document_sha256'], draft['pdf_sha256'])
        self.assertIn('Manajer Keuangan AMIGA', director['consent_text'])
        self.assertEqual(director['signer_title'], 'Manajer Keuangan AMIGA')
        self.assertTrue(self.api.state.review.process_next())  # renders the signed copy
        signed = self.signed_pdf(identifier)
        self.assertEqual(signed.status_code, 200, signed.text[:200])
        text = self.text(signed.content)
        # v8: wet signatures of the PIC and the vendor only; Finance and the Manajer Keuangan approve in the app.
        for expected in ('FINAL', 'Diajukan Oleh', 'Diterima Oleh', 'Vendor penerima pembayaran', 'Admin Intake AMIGA'):
            self.assertIn(expected, text)
        for absent in (reviewer['verification_code'], director['verification_code'], 'Ditandatangani secara elektronik',
                       'Diperiksa Oleh', 'Disetujui Oleh', 'Manajer Keuangan AMIGA'):
            self.assertNotIn(absent, text)
        links = [annotation.get_object().get('/A', {}).get('/URI')
                 for page in PdfReader(BytesIO(signed.content)).pages for annotation in page.get('/Annots', [])]
        self.assertTrue(any(link and link.endswith('/verifikasi/'+str(draft['id'])) for link in links))
        self.login('pic@amiga.local')
        self.assertEqual(self.signed_pdf(identifier).content, signed.content)
        self.assertEqual(self.client.get(f'/api/v1/requests/{identifier}/voucher?version=1').status_code, 200)

    def other_director(self):
        # A second AMIGA director who only holds client B, to prove that the assignment still scopes a director.
        with self.api.state.db.transaction() as conn:
            conn.execute("INSERT INTO users(id,name,email,password_hash,role,title) SELECT 'direksi_lain','Direktur Lain',"
                         "'direksi.lain@amiga.local',password_hash,'AMIGA_DIRECTOR','Direktur AMIGA' FROM users "
                         "WHERE id='finance_a'")
            conn.execute("INSERT INTO assignments VALUES ('direksi_lain','client_b')")
        return 'direksi.lain@amiga.local'

    def test_director_scope_and_role_limits(self):
        identifier = self.signed_by_finance()
        self.assertEqual(self.director_approve(identifier).status_code, 403)
        self.login('pic@amiga.local')
        self.assertEqual(self.director_approve(identifier).status_code, 403)
        self.assertEqual(self.director_return(identifier).status_code, 403)
        self.login(self.other_director())
        self.assertEqual(self.director_approve(identifier).status_code, 404)
        self.assertEqual(self.director_return(identifier).status_code, 404)
        self.login(MANAGER)
        self.assertEqual(self.approve(identifier).status_code, 403)
        self.assertEqual(self.edit(identifier, self.detail(identifier)['draft']['invoice']).status_code, 403)
        upload = self.client.post('/api/v1/demo/normal?client_id=client_a', headers={'Idempotency-Key': str(uuid4())})
        self.assertEqual(upload.status_code, 403)

    def test_director_without_the_client_cannot_read_anything(self):
        identifier = self.signed_by_finance()
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())
        reads = [f'/api/v1/requests/{identifier}', f'/api/v1/requests/{identifier}/document',
                 f'/api/v1/requests/{identifier}/voucher?version=1', f'/api/v1/requests/{identifier}/voucher/signed?version=1']
        self.assertEqual([self.client.get(url).status_code for url in reads], [200] * 4)  # the assigned BOD can
        self.login(self.other_director())
        self.assertEqual([self.client.get(url).status_code for url in reads], [404] * 4)
        self.assertEqual(self.client.get('/api/v1/requests?client_id=client_a').status_code, 404)

    def test_one_bod_signs_for_every_client(self):
        self.login('pic.b@amiga.local')
        identifier = self.sample('normal', client='client_b')
        self.pic_submit(identifier)
        self.login('finance.b@amiga.local')
        response = self.approve(identifier)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.api.state.review.process_next())
        self.assertEqual(self.voucher_row(identifier)['payload']['assigned_director'],
                         {'name': 'Bagas Wiratama', 'title': 'Manajer Keuangan AMIGA'})
        self.login(MANAGER)
        response = self.director_approve(identifier)
        self.assertEqual((response.status_code, response.json()['status']), (200, 'AMIGA_APPROVED'))

    def test_director_needs_a_ready_draft_and_the_current_version(self):
        identifier = self.submitted()
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.login(MANAGER)
        response = self.director_approve(identifier)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VOUCHER_NOT_READY'))
        self.assertTrue(self.api.state.review.process_next())
        response = self.director_approve(identifier, version=2)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VERSION_CONFLICT'))

    def test_director_bad_password_or_missing_consent_changes_nothing(self):
        identifier = self.signed_by_finance()
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier, consent=False).json()['code'], 'CONSENT_REQUIRED')
        self.assertEqual(self.director_approve(identifier, password='kata-sandi-salah').status_code, 403)
        self.assertEqual(self.detail(identifier)['status'], 'AMIGA_REVIEWED')
        self.assertEqual([step['kind'] for step in self.steps(identifier)], ['REVIEWER_SIGNED'])

    def test_director_double_click_signs_once(self):
        identifier = self.signed_by_finance()
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.assertEqual([step['kind'] for step in self.steps(identifier)], ['REVIEWER_SIGNED', 'DIRECTOR_APPROVED'])
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM voucher_signoffs').fetchone()['n'], 1)

    def test_finance_edit_after_signing_blocks_the_director(self):
        identifier = self.signed_by_finance()
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['line_items'][0]['description'] = 'Barang contoh A revisi'
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 409)
        self.assertEqual([step['kind'] for step in self.steps(identifier)], ['REVIEWER_SIGNED'])

    def test_amiga_approved_request_is_locked(self):
        identifier = self.signed_by_finance()
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.login('finance@amiga.local')
        detail = self.detail(identifier)
        self.assertFalse(detail['can_edit'])
        invoice = deepcopy(detail['draft']['invoice'])
        invoice['line_items'][0]['description'] = 'Barang contoh A revisi'
        response = self.edit(identifier, invoice)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'AMIGA_APPROVED_LOCKED'))

    def test_return_requires_a_reason_and_copies_the_version(self):
        identifier = self.signed_by_finance()
        first = self.voucher_row(identifier)
        self.login(MANAGER)
        self.assertEqual(self.director_return(identifier, reason='ok').status_code, 422)
        response = self.director_return(identifier)
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['status'], detail['current_version'], detail['approved_version']), ('RETURNED', 2, None))
        steps = self.steps(identifier)
        self.assertEqual([step['kind'] for step in steps], ['REVIEWER_SIGNED', 'DIRECTOR_RETURNED'])
        self.assertEqual(steps[1]['reason'], 'Nominal PPN perlu dicek ulang dengan vendor')
        with self.api.state.db.transaction() as conn:
            versions = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s ORDER BY version',
                                    (identifier,)).fetchall()
            superseded = conn.execute('SELECT superseded_at FROM vouchers WHERE id=%s', (first['id'],)).fetchone()
        self.assertEqual(versions[1]['snapshot'], versions[0]['snapshot'])
        self.assertIsNotNone(superseded['superseded_at'])

    def test_finance_resigns_a_returned_version_without_changes(self):
        identifier = self.signed_by_finance()
        first = self.voucher_row(identifier)['number']
        self.login(MANAGER)
        self.assertEqual(self.director_return(identifier).status_code, 200)
        self.login('finance@amiga.local')
        response = self.approve(identifier, version=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['status'], 'AMIGA_REVIEWED')
        self.assertNotEqual(self.voucher_row(identifier)['number'], first)

    def test_director_cannot_sign_a_legacy_template(self):
        with patch('app.review.TEMPLATE_VERSION', 'amiga-demo-v3'):
            identifier = self.signed_by_finance()
        self.login(MANAGER)
        response = self.director_approve(identifier)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VOUCHER_TEMPLATE_UNSUPPORTED'))
        self.assertEqual(self.director_return(identifier).status_code, 200)

    def test_bod_is_told_when_the_draft_failed_instead_of_waiting(self):
        # After an outage the draft is FAILED for good until Finance retries; "wait a few seconds" would never end.
        identifier = self.submitted()
        self.assertEqual(self.approve(identifier).status_code, 200)
        review = self.api.state.review
        working = review.renderer

        def broken(*_, **__):
            raise RuntimeError('render gagal')

        review.renderer = broken
        self.assertTrue(review.process_next())
        review.renderer = working
        self.login(MANAGER)
        signature = self.detail(identifier)['signature']
        self.assertFalse(signature['can_director_act'])
        self.assertEqual(signature['director_block_reason'], 'Draf voucher gagal dibuat. Minta Finance mengulang render.')

    def test_failed_signed_render_can_be_retried(self):
        identifier = self.signed_by_finance()
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        review = self.api.state.review
        working = review.renderer

        def broken(*_, **__):
            raise RuntimeError('render gagal')

        review.renderer = broken
        self.assertTrue(review.process_next())
        self.assertEqual(self.detail(identifier)['signature']['signed_voucher']['render_status'], 'FAILED')
        review.renderer = working
        self.login('finance@amiga.local')
        response = self.client.post(f'/api/v1/requests/{identifier}/voucher/retry',
                                    json={'expected_version': 1, 'reason': 'Gangguan render lokal sudah diperiksa'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(review.process_next())
        self.assertEqual(self.signed_pdf(identifier).status_code, 200)

    def test_director_queue_lists_only_signing_work(self):
        signed = self.signed_by_finance()
        self.login('pic@amiga.local')
        self.sample('missing_bank')
        self.login(MANAGER)
        items = self.client.get('/api/v1/requests?client_id=client_a').json()['items']
        self.assertEqual([str(item['id']) for item in items], [signed])

    def test_public_verification_shows_signers_and_hashes_only(self):
        identifier = self.signed_by_finance()
        voucher = self.voucher_row(identifier)
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())
        reviewer, director = self.steps(identifier)
        with self.api.state.db.transaction() as conn:
            final = conn.execute('SELECT pdf_sha256 FROM voucher_signoffs WHERE voucher_id=%s', (voucher['id'],)).fetchone()
        self.client.cookies.clear()
        response = self.client.get(f"/api/v1/verifikasi/{voucher['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body['status'], body['number'], body['content_matches']), ('SAH', voucher['number'], True))
        # v7: the three approvals in the order of the printed boxes, without codes, since none is printed.
        self.assertEqual([(signer['role'], signer['name'], signer['code']) for signer in body['signers']],
                         [('Diajukan Oleh', 'Dian Pratama', None), ('Diperiksa Oleh', 'Nadia Putri', None),
                          ('Disetujui Oleh', 'Bagas Wiratama', None)])
        self.assertEqual(body['final_pdf_sha256'], final['pdf_sha256'])
        page = self.client.get(f"/verifikasi/{voucher['id']}")
        self.assertEqual(page.status_code, 200)
        self.assertIn('text/html', page.headers['content-type'])
        for expected in ('Sah', 'Bagas Wiratama', 'Manajer Keuangan AMIGA', 'Diperiksa Oleh', 'Tanda tangan basah',
                         final['pdf_sha256']):
            self.assertIn(expected, page.text)
        for absent in (reviewer['verification_code'], director['verification_code'], 'Direksi'):
            self.assertNotIn(absent, page.text)
        for private in ('00123456', 'Bank Contoh', 'PT Contoh Demo', 'IDR'):
            self.assertNotIn(private, response.text)
            self.assertNotIn(private, page.text)
        class PublicImages(HTMLParser):
            def __init__(self):
                super().__init__()
                self.sources = []

            def handle_starttag(self, tag, attrs):
                if tag == 'img':
                    self.sources.append(dict(attrs).get('src'))

        assets = PublicImages()
        assets.feed(page.text)
        self.assertEqual(assets.sources, ['/static/brand/amiga-logo.png'])
        for leak in ('<img', 'image/png'):
            self.assertNotIn(leak, response.text)
        for leak in ('base64', 'specimen'):  # the brand is public; signatures and banking details are private
            self.assertNotIn(leak, page.text)
            self.assertNotIn(leak, response.text)
        self.assertEqual(self.client.get(f'/api/v1/verifikasi/{uuid4()}').status_code, 404)
        self.assertEqual(self.client.get(f'/verifikasi/{uuid4()}').status_code, 404)

    def test_verification_waits_for_the_director_then_shows_superseded(self):
        identifier = self.signed_by_finance()
        voucher = self.voucher_row(identifier)
        body = self.client.get(f"/api/v1/verifikasi/{voucher['id']}").json()
        self.assertEqual((body['status'], [signer['name'] for signer in body['signers']]),
                         ('MENUNGGU_DIREKSI', ['Dian Pratama', 'Nadia Putri']))
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['line_items'][0]['description'] = 'Barang contoh A revisi'
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/verifikasi/{voucher['id']}").json()['status'], 'DIGANTIKAN')

    def directors(self):
        with self.api.state.db.transaction() as conn:
            return conn.execute("SELECT u.id,u.email,u.title,u.role,string_agg(a.client_id,',' ORDER BY a.client_id COLLATE \"C\") AS clients "
                                "FROM users u LEFT JOIN assignments a ON a.user_id=u.id WHERE u.id LIKE 'direksi%' "
                                'GROUP BY u.id ORDER BY u.id').fetchall()

    def test_reinitialize_keeps_role_constraint_and_the_finance_manager(self):
        # schema.sql runs on every start; a second start must keep the approver and reject unknown or retired roles.
        self.api.state.db.initialize()
        self.assertEqual([(row['id'], row['email'], row['role'], row['title'], row['clients']) for row in self.directors()],
                         [('direksi_a', MANAGER, 'AMIGA_DIRECTOR', 'Manajer Keuangan AMIGA', EVERY_CLIENT)])
        for role in ('ADMIN', 'CLIENT_APPROVER'):
            with self.subTest(role=role), self.assertRaises(psycopg.errors.CheckViolation), \
                    self.api.state.db.transaction() as conn:
                conn.execute("INSERT INTO users VALUES ('admin_x','Admin','admin@amiga.local','x',%s)", (role,))

    def test_restart_moves_old_client_directors_to_the_amiga_bod(self):
        # The demo database of 14 Oct still has two client directors from the first stage 8 design.
        db = self.api.state.db
        identifier = self.signed_by_finance()
        with db.transaction() as conn:
            conn.execute('ALTER TABLE users DROP CONSTRAINT users_role_check')
            conn.execute("UPDATE users SET role='CLIENT_APPROVER',email='direksi.a@klien.local',"
                         "title='Direktur Utama Arunika Sejahtera' WHERE id='direksi_a'")
            conn.execute("DELETE FROM assignments WHERE user_id='direksi_a' AND client_id='client_b'")
            conn.execute("INSERT INTO users(id,name,email,password_hash,role,title) SELECT 'direksi_b','Laras Kusuma',"
                         "'direksi.b@klien.local',password_hash,'CLIENT_APPROVER','Direktur Bumi Persada' FROM users "
                         "WHERE id='finance_a' ON CONFLICT (id) DO UPDATE SET role='CLIENT_APPROVER'")
            conn.execute("INSERT INTO assignments VALUES ('direksi_b','client_b') ON CONFLICT DO NOTHING")
            conn.execute("ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN "
                         "('PIC','FINANCE_REVIEWER','CLIENT_APPROVER'))")
            conn.execute("UPDATE requests SET status='CLIENT_APPROVED' WHERE id=%s", (identifier,))
        db.initialize()
        self.assertEqual([(row['id'], row['email'], row['role'], row['title'], row['clients']) for row in self.directors()],
                         [('direksi_a', MANAGER, 'AMIGA_DIRECTOR', 'Manajer Keuangan AMIGA', EVERY_CLIENT),
                          ('direksi_b', 'direksi.b@klien.local', 'AMIGA_DIRECTOR', 'Direktur Bumi Persada', None)])
        self.assertEqual(self.detail(identifier)['status'], 'AMIGA_APPROVED')

    def test_restart_turns_the_bod_login_into_the_finance_manager(self):
        # The demo database of 15 Oct afternoon: the final approver is still the BOD and the PICs are "PIC Klien".
        db = self.api.state.db
        with db.transaction() as conn:
            conn.execute("UPDATE users SET email='direksi@amiga.local',title='Direktur Utama AMIGA' WHERE id='direksi_a'")
            conn.execute("UPDATE users SET title='PIC Klien' WHERE role='PIC'")
        db.initialize()
        self.assertEqual([(row['id'], row['email'], row['title'], row['clients']) for row in self.directors()],
                         [('direksi_a', MANAGER, 'Manajer Keuangan AMIGA', EVERY_CLIENT)])
        with db.transaction() as conn:
            titles = {row['title'] for row in conn.execute("SELECT title FROM users WHERE role='PIC'").fetchall()}
        self.assertEqual(titles, {'Admin Intake AMIGA'})
        response = self.client.post('/api/v1/login', json={'email': 'direksi@amiga.local', 'password': 'test-password-only'})
        self.assertEqual((response.status_code, response.json()['code']), (401, 'LOGIN_FAILED'))
        self.login(MANAGER)
        self.assertEqual(self.client.get('/api/v1/session').json()['role'], 'AMIGA_DIRECTOR')

    def test_moving_to_the_bod_runs_once(self):
        # A later, deliberate assignment of the retired client director must survive the next restart.
        db = self.api.state.db
        with db.transaction() as conn:
            conn.execute("INSERT INTO users(id,name,email,password_hash,role,title) SELECT 'direksi_b','Laras Kusuma',"
                         "'direksi.b@klien.local',password_hash,'AMIGA_DIRECTOR','Direktur AMIGA' FROM users "
                         "WHERE id='finance_a' ON CONFLICT (id) DO NOTHING")
            conn.execute("INSERT INTO assignments VALUES ('direksi_b','client_b') ON CONFLICT DO NOTHING")
        db.initialize()
        self.assertEqual([(row['id'], row['clients']) for row in self.directors()],
                         [('direksi_a', EVERY_CLIENT), ('direksi_b', 'client_b')])

    def retired_director_in_an_old_database(self):
        # The demo database of 14 Oct, before accounts could be closed: the second client director of the first
        # design is still there, without a client, with a session opened before the restart.
        with self.api.state.db.transaction() as conn:
            conn.execute("INSERT INTO users(id,name,email,password_hash,role,title) SELECT 'direksi_b','Laras Kusuma',"
                         "'direksi.b@klien.local',password_hash,'AMIGA_DIRECTOR','Direktur Bumi Persada' FROM users "
                         "WHERE id='finance_a' ON CONFLICT (id) DO NOTHING")
        self.login('direksi.b@klien.local')
        with self.api.state.db.transaction() as conn:
            conn.execute('ALTER TABLE users DROP COLUMN IF EXISTS disabled_at')

    def test_restart_closes_the_retired_client_director_login(self):
        self.retired_director_in_an_old_database()
        self.api.state.db.initialize()
        self.assertEqual(self.client.get('/api/v1/session').status_code, 401)
        response = self.client.post('/api/v1/login', json={'email':'direksi.b@klien.local', 'password':'test-password-only'})
        self.assertEqual((response.status_code, response.json()['code']), (401, 'LOGIN_FAILED'))
        self.login(MANAGER)

    def test_closing_the_retired_login_runs_once(self):
        # Like the move to the BOD: an account deliberately reopened later stays open after the next restart.
        self.retired_director_in_an_old_database()
        db = self.api.state.db
        db.initialize()
        with db.transaction() as conn:
            conn.execute("UPDATE users SET disabled_at=NULL WHERE id='direksi_b'")
        db.initialize()
        self.login('direksi.b@klien.local')

    def test_bod_session_covers_every_client(self):
        self.login(MANAGER)
        session = self.client.get('/api/v1/session').json()
        self.assertEqual((session['role'], ','.join(sorted(client['id'] for client in session['clients']))),
                         ('AMIGA_DIRECTOR', EVERY_CLIENT))

    def specimen_of(self, user_id):
        with self.api.state.db.transaction() as conn:
            return conn.execute('SELECT sha256,image_png FROM signature_specimens WHERE user_id=%s', (user_id,)).fetchone()

    @staticmethod
    def images(data):
        return sum(len(page.images) for page in PdfReader(BytesIO(data)).pages)

    def test_signers_get_a_synthetic_specimen_and_others_do_not(self):
        db = self.api.state.db
        db.initialize()  # a restart adds nothing
        with db.transaction() as conn:
            rows = conn.execute('SELECT user_id,source,sha256,image_png FROM signature_specimens ORDER BY user_id').fetchall()
        self.assertEqual([(row['user_id'], row['source']) for row in rows],
                         [('direksi_a', 'SYNTHETIC_DEMO'), ('finance_a', 'SYNTHETIC_DEMO'), ('finance_b', 'SYNTHETIC_DEMO')])
        for row in rows:
            self.assertTrue(bytes(row['image_png']).startswith(b'\x89PNG'))
            self.assertEqual(hashlib.sha256(bytes(row['image_png'])).hexdigest(), row['sha256'])
        with self.assertRaises(psycopg.errors.RaiseException), db.transaction() as conn:
            conn.execute("UPDATE signature_specimens SET source='UPLOADED'")

    def test_v7_prints_no_specimen_while_the_steps_keep_their_hash(self):
        # 15 Oct: wet signatures on paper. The only image on either copy is the AMIGA logo.
        identifier = self.signed_by_finance()
        finance, manager = self.specimen_of('finance_a'), self.specimen_of('direksi_a')
        [reviewer] = self.steps(identifier)
        self.assertEqual(reviewer['specimen_sha256'], finance['sha256'])
        self.assertEqual(self.voucher_row(identifier)['payload']['signatures']['reviewer']['specimen_sha256'],
                         finance['sha256'])
        draft = self.client.get(f'/api/v1/requests/{identifier}/voucher?version=1')
        self.assertEqual((draft.status_code, self.images(draft.content)), (200, 1))
        self.login(MANAGER)
        self.assertEqual(self.director_approve(identifier).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())
        self.assertEqual(self.steps(identifier)[1]['specimen_sha256'], manager['sha256'])
        self.assertEqual(self.images(self.signed_pdf(identifier).content), 1)

    def test_an_approver_without_a_specimen_still_approves(self):
        with self.api.state.db.transaction() as conn:
            conn.execute("INSERT INTO users(id,name,email,password_hash,role,title) SELECT 'finance_c','Finance Cadangan',"
                         "'finance.c@amiga.local',password_hash,'FINANCE_REVIEWER','Finance Reviewer AMIGA' FROM users "
                         "WHERE id='finance_a'")
            conn.execute("INSERT INTO assignments VALUES ('finance_c','client_a')")
        self.login('pic@amiga.local')
        identifier = self.sample('normal')
        self.pic_submit(identifier)
        self.login('finance.c@amiga.local')
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertTrue(self.api.state.review.process_next())
        self.assertIsNone(self.steps(identifier)[0]['specimen_sha256'])
        draft = self.client.get(f'/api/v1/requests/{identifier}/voucher?version=1')
        self.assertEqual((draft.status_code, self.images(draft.content)), (200, 1))  # the logo only

    def test_the_specimen_preview_is_gone(self):
        # The approval dialog no longer shows a specimen: nothing is stamped on a v7 voucher.
        self.login('finance@amiga.local')
        self.assertEqual(self.client.get('/api/v1/session/specimen').status_code, 404)

    def test_signing_password_check_reads_the_stored_hash(self):
        db = self.api.state.db
        self.assertTrue(db.verify_password('finance_a', 'test-password-only'))
        self.assertFalse(db.verify_password('finance_a', 'kata-sandi-salah'))
        self.assertFalse(db.verify_password('tidak_ada', 'test-password-only'))


if __name__ == '__main__':
    unittest.main()
