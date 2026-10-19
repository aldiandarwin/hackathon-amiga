"""HTTP + PostgreSQL acceptance checks. Never sends paid API requests."""

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import shutil
import time
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from pypdf import PdfWriter
import psycopg
from psycopg import sql

from app.main import create_app
from app.service import AppError, inspect_pdf, sample_input, Worker
from app.settings import ROOT, Settings
from amiga_ocr.live_budget import BudgetError


class DocumentTests(unittest.TestCase):
    def test_reject_invalid_large_encrypted_and_excess_pages(self):
        cases = [(b'not a PDF', 'INVALID_DOCUMENT'), (b'%PDF-' + b'0'*5_000_000, 'FILE_TOO_LARGE')]
        for encrypted, count, code in [(True, 1, 'ENCRYPTED_PDF'), (False, 6, 'PAGE_LIMIT')]:
            writer, output = PdfWriter(), BytesIO()
            for _ in range(count):
                writer.add_blank_page(width=200, height=200)
            if encrypted:
                writer.encrypt('test-only')
            writer.write(output)
            cases.append((output.getvalue(), code))
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(AppError) as caught:
                inspect_pdf(payload)
            self.assertEqual(caught.exception.code, code)

    def test_frozen_samples_are_readable_and_have_saved_evidence(self):
        for name in ('normal', 'missing_bank', 'wrong_total'):
            pdf, saved = sample_input(name)
            self.assertEqual(len(inspect_pdf(pdf)), 1)
            self.assertTrue(saved['source_evidence'])


def drop_private_data(settings):
    """Each test removes its own schema and folder, so nothing piles up between runs. The guard keeps this away from
    the demo schema and from anything outside app/test-output."""
    folder = Path(settings.data_dir).resolve()
    if not settings.schema.startswith('amiga_test_') or not folder.is_relative_to((ROOT / 'app/test-output').resolve()):
        raise AssertionError('Refusing to remove data outside the test area')
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(settings.schema)))
    shutil.rmtree(folder, ignore_errors=True)


class CleanupTests(unittest.TestCase):
    def test_database_test_leaves_no_schema_or_folder_behind(self):
        # 1,124 schemas and folders piled up before this; each test now removes its own when it ends.
        seen = {}

        class Probe(unittest.TestCase):
            setUp = DatabaseAcceptanceTests.setUp
            login = DatabaseAcceptanceTests.login
            forbid_live = staticmethod(DatabaseAcceptanceTests.forbid_live)

            def test_probe(inner):
                seen['schema'], seen['folder'] = inner.settings.schema, inner.settings.data_dir
                self.assertTrue(seen['folder'].exists())

        result = unittest.TestResult()
        Probe('test_probe').run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        with psycopg.connect(Settings.load().database_url) as conn:
            left = conn.execute('SELECT 1 FROM information_schema.schemata WHERE schema_name=%s',
                                (seen['schema'],)).fetchone()
        self.assertIsNone(left)
        self.assertFalse(seen['folder'].exists())


class DatabaseAcceptanceTests(unittest.TestCase):
    """Every test uses its own schema and private directory, and removes both when it ends."""

    def setUp(self):
        local = Settings.load()
        name = 'amiga_test_' + uuid4().hex
        self.settings = Settings(local.database_url, 'test-password-only', ROOT/'app/test-output'/name, name, True)
        # Registered first, so it runs last: after the test app below has shut down.
        self.addCleanup(drop_private_data, self.settings)
        self.api = create_app(self.settings, start_worker=False, live_client_factory=self.forbid_live)
        self.client = TestClient(self.api)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.login('finance@amiga.local')

    @staticmethod
    def forbid_live():
        raise AssertionError('A test attempted a real OpenAI client')

    def login(self, email):
        response = self.client.post('/api/v1/login', json={'email':email, 'password':'test-password-only'})
        self.assertEqual(response.status_code, 200)
        self.client.headers['X-CSRF-Token'] = response.json()['csrf']
        self.email = email

    def sample(self, name='normal', key=None, client='client_a', process=True):
        # Since 15 Oct only the PIC uploads: the client's PIC uploads, then the account logged in before comes back.
        with self.api.state.db.transaction() as conn:
            uploader = conn.execute("SELECT u.email FROM users u JOIN assignments a ON a.user_id=u.id WHERE a.client_id=%s "
                                    "AND u.role='PIC' ORDER BY u.id LIMIT 1", (client,)).fetchone()['email']
        viewer = getattr(self, 'email', None)
        if viewer != uploader:
            self.login(uploader)
        response = self.client.post(f'/api/v1/demo/{name}?client_id={client}', headers={'Idempotency-Key':key or str(uuid4())})
        self.assertEqual(response.status_code, 202, response.text)
        identifier = response.json()['request_id']
        if process:
            self.assertTrue(self.api.state.service.process_next())
        if viewer and viewer != uploader:
            self.login(viewer)
        return identifier

    def detail(self, identifier):
        response = self.client.get('/api/v1/requests/'+identifier)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def edit(self, identifier, invoice, version=1, reason='Koreksi sesuai pemeriksaan dokumen'):
        return self.client.patch('/api/v1/requests/'+identifier+'/draft', json={
            'expected_version':version, 'invoice':invoice, 'reason':reason})

    def pic_submit(self, identifier, version=1, note='Data sudah dicocokkan dengan dokumen asli'):
        """Since 15 Oct Finance signs only what a PIC submitted. Call it while the PIC is logged in."""
        response = self.client.post('/api/v1/requests/'+identifier+'/submit', json={
            'expected_version':version, 'consent':True, 'note':note})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_auth_csrf_origin_and_private_paths(self):
        self.client.headers.pop('X-CSRF-Token')
        response = self.client.post('/api/v1/demo/normal?client_id=client_a', headers={'Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/api/v1/login', headers={'Origin':'http://untrusted.example'}, json={'email':'finance@amiga.local','password':'test-password-only'})
        self.assertEqual(response.status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/requests?client_id=client_a').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/login', json={'email':'finance@amiga.local','password':'incorrect'}).status_code, 401)
        for path in ('/.env', '/.appdata/demo-access.txt', '/static/../.env'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_queue_exposes_issues_and_the_computed_payment_plan(self):
        identifier = self.sample('wrong_total')
        item = self.client.get('/api/v1/requests?client_id=client_a').json()['items'][0]
        self.assertEqual(str(item['id']), identifier)
        self.assertIn('TOTAL_MISMATCH', item['issue_codes'])
        self.assertGreater(item['issue_count'], 0)
        self.assertEqual(item['net_payable'], '510000.00')
        self.assertFalse(item['needs_other_reviewer'])  # the PIC uploaded it
        self.assertNotIn('tax', item)
        self.assertNotIn('validation', item)
        self.assertNotIn('uploaded_by', item)
        # Invoices Finance uploaded before 15 Oct still need another Finance reviewer.
        with self.api.state.db.transaction() as conn:
            conn.execute("UPDATE requests SET uploaded_by='finance_a' WHERE id=%s", (identifier,))
        item = self.client.get('/api/v1/requests?client_id=client_a').json()['items'][0]
        self.assertTrue(item['needs_other_reviewer'])
        self.login('pic@amiga.local')
        item = self.client.get('/api/v1/requests?client_id=client_a').json()['items'][0]
        self.assertFalse(item['needs_other_reviewer'])

    def test_client_isolation_for_list_detail_document_and_edit(self):
        identifier = self.sample()
        invoice = self.detail(identifier)['draft']['invoice']
        self.login('finance.b@amiga.local')
        self.assertEqual(self.client.get('/api/v1/requests?client_id=client_a').status_code, 404)
        self.assertEqual(self.client.get('/api/v1/requests?client_id=client_b').json()['items'], [])
        for suffix in ('', '/document', '/preview/1'):
            self.assertEqual(self.client.get('/api/v1/requests/'+identifier+suffix).status_code, 404)
        self.assertEqual(self.edit(identifier, invoice).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/demo/normal?client_id=client_a', headers={'Idempotency-Key':str(uuid4())}).status_code, 404)

    def test_idempotency_and_pdf_duplicate_do_not_enqueue_again(self):
        self.login('pic@amiga.local')  # since 15 Oct only the PIC uploads
        key = str(uuid4())
        identifier = self.sample(key=key, process=False)
        for next_key in (key, str(uuid4())):
            response = self.client.post('/api/v1/demo/normal?client_id=client_a', headers={'Idempotency-Key':next_key})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json(), {'request_id':identifier, 'created':False})
        response = self.client.post('/api/v1/demo/wrong_total?client_id=client_a', headers={'Idempotency-Key':key})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.api.state.service.process_next())
        self.assertFalse(self.api.state.service.process_next())
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM jobs').fetchone()['n'], 1)

    def test_replay_document_and_persistence_across_app_restart(self):
        identifier = self.sample()
        detail = self.detail(identifier)
        self.assertEqual(detail['status'], 'READY_FOR_REVIEW')
        self.assertEqual(detail['draft']['source']['live_calls'], 0)
        self.assertEqual(detail['draft']['invoice']['payment']['account_number'], '00123456')
        response = self.client.get(detail['document_url'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, sample_input('normal')[0])
        preview = self.client.get('/api/v1/requests/'+identifier+'/preview/1')
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers['content-type'], 'image/png')
        self.assertTrue(preview.content.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get('/api/v1/requests/'+identifier+'/preview/2').status_code,404)
        other = create_app(self.settings, start_worker=False, live_client_factory=self.forbid_live)
        with TestClient(other) as restarted:
            login = restarted.post('/api/v1/login', json={'email':'finance@amiga.local','password':'test-password-only'})
            self.assertEqual(login.status_code, 200)
            restored = restarted.get('/api/v1/requests/'+identifier).json()
            self.assertEqual(restored['draft'], detail['draft'])
            self.assertEqual(len(restored['audit']), 2)

    def test_edit_version_audit_evidence_and_stale_conflict(self):
        identifier = self.sample()
        original = self.detail(identifier)
        invoice = deepcopy(original['draft']['invoice'])
        invoice['payment']['account_number'] = '00001234'
        result = self.edit(identifier, invoice)
        self.assertEqual(result.status_code, 200, result.text)
        changed = result.json()
        self.assertEqual(changed['current_version'], 2)
        self.assertEqual(changed['draft']['source_evidence'], original['draft']['source_evidence'])
        self.assertIn('payment.account_number', changed['draft']['human_changed_fields'])
        self.assertEqual(changed['audit'][0]['changes']['payment.account_number'], {'before':'00123456','after':'00001234'})
        self.assertEqual(changed['status'], 'EXCEPTION')
        self.assertEqual(self.edit(identifier, invoice).status_code, 409)
        self.assertEqual(self.detail(identifier)['current_version'], 2)
        with self.api.state.db.transaction() as conn:
            old = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=1',(identifier,)).fetchone()
            self.assertEqual(old['snapshot'], original['draft'])

    def test_contract_invalid_numbers_reason_and_pic_edits_after_submit_rejected(self):
        identifier = self.sample()
        invoice = self.detail(identifier)['draft']['invoice']
        invoice['stated_total'] = 500000.0
        self.assertEqual(self.edit(identifier, invoice).status_code, 422)
        invoice['stated_total'] = '500000.00'
        self.assertEqual(self.edit(identifier, invoice, reason='   ').status_code, 422)
        # The PIC corrects during intake under the same contract, and is locked out once the invoice is submitted.
        self.login('pic@amiga.local')
        self.assertTrue(self.detail(identifier)['can_edit'])
        invoice['stated_total'] = 500000.0
        self.assertEqual(self.edit(identifier, invoice).status_code, 422)
        self.pic_submit(identifier)
        self.assertFalse(self.detail(identifier)['can_edit'])
        invoice['stated_total'] = '510000.00'
        self.assertEqual(self.edit(identifier, invoice).status_code, 409)
        self.assertEqual(self.detail(identifier)['current_version'], 1)

    def test_history_is_append_only_in_database(self):
        identifier = self.sample()
        for query in ('UPDATE invoice_versions SET version=2 WHERE request_id=%s',
                      "UPDATE audit_events SET reason='modified' WHERE request_id=%s"):
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.api.state.db.transaction() as conn:
                    conn.execute(query, (identifier,))
        self.assertEqual(self.detail(identifier)['current_version'], 1)

    def test_upload_endpoint_and_worker_with_fake_transport(self):
        pdf, saved = sample_input('normal')
        calls = []

        class FakeClient:
            def preflight(self):
                calls.append('preflight')

            def extract_pdf(self, data, case_id):
                calls.append('extract')
                raw = {'invoice':saved['invoice'], 'evidence':[{'field':path,'page':entry['page'],'raw_value':entry['raw_value']}
                        for path, entry in saved['source_evidence'].items() if entry]}
                return {'run_id':str(uuid4()),'duration_ms':0,'cost_upper_estimate_usd':'0','usage':{},'prompt_version':'TEST_NO_NETWORK',
                        'response':{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(raw)}]}]}}

        self.api.state.service.live_client_factory = FakeClient
        self.login('pic@amiga.local')  # since 15 Oct only the PIC uploads
        response = self.client.post('/api/v1/requests?client_id=client_a&filename=uploaded.pdf', content=pdf,
                                    headers={'Content-Type':'application/pdf','Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(calls, [])
        identifier = response.json()['request_id']
        self.assertEqual(self.detail(identifier)['status'], 'QUEUED')
        self.assertTrue(self.api.state.service.process_next())
        self.assertEqual(calls, ['preflight','extract'])
        self.assertEqual(self.detail(identifier)['status'], 'READY_FOR_REVIEW')
        self.assertFalse(self.api.state.service.process_next())

    def test_budget_failure_stops_job_without_retry(self):
        class BudgetBlocked:
            def preflight(self):
                pass

            def extract_pdf(self, data, case_id):
                raise BudgetError('Test only; not the actual ledger')

        self.api.state.service.live_client_factory = BudgetBlocked
        self.login('pic@amiga.local')  # since 15 Oct only the PIC uploads
        response = self.client.post('/api/v1/requests?client_id=client_a&filename=budget.pdf', content=sample_input('normal')[0],
                                    headers={'Content-Type':'application/pdf','Idempotency-Key':str(uuid4())})
        identifier = response.json()['request_id']
        self.api.state.service.process_next()
        detail = self.detail(identifier)
        self.assertEqual(detail['error_code'], 'BUDGET_BLOCKED')
        self.assertEqual(detail['status'], 'EXCEPTION')
        self.assertIsNone(detail['draft'])
        self.assertFalse(self.api.state.service.process_next())

    def test_invalid_upload_is_rejected_before_enqueue(self):
        self.login('pic@amiga.local')  # since 15 Oct only the PIC uploads
        response = self.client.post('/api/v1/requests?client_id=client_a&filename=bad.pdf', content=b'not a PDF',
                                    headers={'Content-Type':'application/pdf','Idempotency-Key':str(uuid4())})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.api.state.service.process_next())

    def test_worker_survives_a_transient_database_error(self):
        # On 14 Oct one dropped connection stopped both demo workers for good, so no voucher rendered afterwards.
        service, calls = self.api.state.service, []

        def flaky():
            calls.append(time.monotonic())
            if len(calls) == 1:
                raise psycopg.OperationalError('connection lost')
            return False

        service.process_next = flaky
        worker = self.api.state.worker
        worker.start()
        self.addCleanup(worker.close)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and not (len(calls) >= 2 and worker.healthy):
            time.sleep(0.05)
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(worker.healthy)
        self.assertTrue(worker.thread.is_alive())

    def test_worker_releases_work_cut_off_by_a_database_outage(self):
        # A full outage can strike mid-job. Once the database is back the job must not stay PROCESSING for good.
        identifier, service, calls = self.sample(process=False), self.api.state.service, []

        def outage():
            calls.append(1)
            if len(calls) == 1:
                with self.api.state.db.transaction() as conn:
                    conn.execute("UPDATE requests SET status='PROCESSING' WHERE id=%s",(identifier,))
                    conn.execute("UPDATE jobs SET status='PROCESSING' WHERE request_id=%s",(identifier,))
                raise psycopg.OperationalError('server closed the connection unexpectedly')
            return False

        service.process_next = outage
        worker = self.api.state.worker
        worker.start()
        self.addCleanup(worker.close)
        deadline = time.monotonic() + 8
        # Two calls means the worker has run again after the outage.
        while time.monotonic() < deadline and (len(calls) < 2 or self.detail(identifier)['status'] == 'PROCESSING'):
            time.sleep(0.2)
        detail = self.detail(identifier)
        self.assertEqual((detail['status'], detail['error_code']), ('EXCEPTION', 'PROCESS_INTERRUPTED'))
        self.assertTrue(worker.healthy)

    def test_interrupted_job_is_not_retried_after_worker_restart(self):
        identifier = self.sample(process=False)
        with self.api.state.db.transaction() as conn:
            conn.execute("UPDATE requests SET status='PROCESSING' WHERE id=%s",(identifier,))
            conn.execute("UPDATE jobs SET status='PROCESSING' WHERE request_id=%s",(identifier,))
        worker = Worker(self.api.state.service)
        self.addCleanup(worker.close)
        worker.start()
        deadline = time.monotonic() + 5
        while not worker.healthy and time.monotonic() < deadline:
            worker.stop.wait(0.05)
        self.assertTrue(worker.healthy)
        detail = self.detail(identifier)
        self.assertEqual(detail['status'],'EXCEPTION')
        self.assertEqual(detail['error_code'],'PROCESS_INTERRUPTED')
        self.assertIsNone(detail['draft'])
        self.assertEqual(detail['audit'][0]['action'],'PROCESS_INTERRUPTED')
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT status FROM jobs WHERE request_id=%s',(identifier,)).fetchone()['status'],'FAILED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
