"""Independent approval, frozen PDF, revision and retry acceptance tests (no live API)."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from io import BytesIO
import unittest

from pypdf import PdfReader
import psycopg

from app.tests import test_app as fixtures
from app.voucher_pdf import render_voucher


class ReviewAcceptanceTests(unittest.TestCase):
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
        payload = dict(expected_version=version,source_reviewed=True,reason='Dokumen sintetis diperiksa seluruh halaman',
                       password='test-password-only',consent=True)
        payload.update(overrides)
        return self.client.post('/api/v1/requests/'+identifier+'/review',json=payload)

    def voucher(self, identifier, version=1):
        return self.client.get(f'/api/v1/requests/{identifier}/voucher?version={version}')

    def retry(self, identifier, version=1):
        return self.client.post(f'/api/v1/requests/{identifier}/voucher/retry',json={
            'expected_version':version,'reason':'Gangguan render lokal sudah diperiksa'})

    def record(self, identifier, version=1):
        with self.api.state.db.transaction() as conn:
            return conn.execute('SELECT * FROM vouchers WHERE request_id=%s AND invoice_version=%s',(identifier,version)).fetchone()

    def test_pic_self_approval_and_cross_client_are_blocked(self):
        # Brief p9 scenario 5: whoever uploads cannot approve. Since 15 Oct only the PIC uploads and only Finance
        # approves, so Finance cannot upload at all and the PIC who uploaded is refused.
        upload = self.client.post('/api/v1/demo/normal?client_id=client_a', headers={'Idempotency-Key':'finance-upload'})
        self.assertEqual((upload.status_code, upload.json()['code']), (403, 'FORBIDDEN'))
        self.login('pic@amiga.local')
        own = self.sample()
        self.assertEqual(self.approve(own).status_code,403)
        self.assertFalse(self.detail(own)['approval']['can_approve'])
        self.assertEqual(self.detail(own)['approval']['reason_code'],'FINANCE_REQUIRED')
        self.assertEqual(self.retry(own).status_code,403)
        self.login('finance.b@amiga.local')
        self.assertEqual(self.approve(own).status_code,404)
        self.assertEqual(self.retry(own).status_code,404)
        self.assertEqual(self.voucher(own).status_code,404)
        self.client.cookies.clear()
        self.assertEqual(self.voucher(own).status_code,401)

    def test_acknowledgment_reason_contract_and_stale_version(self):
        identifier = self.submitted()
        self.assertIsNone(self.detail(identifier)['approval']['reason_code'])
        for values in ({'source_reviewed':False},{'source_reviewed':'yes'}, {'reason':'     '},
                       {'actor_id':'pic_a'},{'skip_validation':True}):
            with self.subTest(values=values):
                self.assertEqual(self.approve(identifier,**values).status_code,422)
        self.assertEqual(self.approve(identifier,version=2).status_code,409)
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM vouchers').fetchone()['n'],0)

    def test_approval_generates_frozen_private_pdf_and_repeat_is_idempotent(self):
        identifier = self.submitted()
        original = self.detail(identifier)['draft']
        response = self.approve(identifier)
        self.assertEqual(response.status_code,200,response.text)
        detail = response.json()
        self.assertEqual(detail['status'],'AMIGA_REVIEWED')
        self.assertEqual(detail['approved_version'],1)
        self.assertEqual(detail['voucher']['render_status'],'PENDING')
        self.assertEqual(self.voucher(identifier).status_code,409)
        self.assertTrue(self.api.state.review.process_next())
        pdf = self.voucher(identifier)
        self.assertEqual(pdf.status_code,200,pdf.text[:150] if pdf.status_code!=200 else '')
        self.assertEqual(pdf.headers['content-type'],'application/pdf')
        self.assertIn('attachment;',pdf.headers['content-disposition'])
        reader = PdfReader(BytesIO(pdf.content))
        self.assertEqual(len(reader.pages),1)
        text = ' '.join(' '.join(p.extract_text() for p in reader.pages).split())
        # v8 prints the PIC and the vendor; the Finance reviewer approves in the app but is not printed.
        for expected in ('00123456','500.000','Dian Pratama','Diterima Oleh','ARS-', 'di luar aplikasi'):
            self.assertIn(expected,text)
        self.assertNotIn('Nadia Putri',text)
        self.assertEqual(self.detail(identifier)['draft'],original)
        record = self.record(identifier)
        self.assertEqual(record['payload']['uploader']['name'], 'Dian Pratama')
        self.assertEqual(record['pdf_sha256'],hashlib.sha256(pdf.content).hexdigest())
        self.assertEqual(record['payload']['invoice'],original['invoice'])
        self.assertEqual(self.approve(identifier).status_code,200)
        self.assertEqual(self.record(identifier)['number'],record['number'])
        self.assertFalse(self.api.state.review.process_next())
        self.login('pic@amiga.local')
        self.assertEqual(self.voucher(identifier).content,pdf.content)

    def test_simultaneous_approval_uses_one_decision_and_number(self):
        identifier = self.submitted()
        user = self.client.get('/api/v1/session').json()
        def submit(_):
            return self.api.state.review.approve(identifier,user,1,'Pemeriksaan serentak untuk uji',True,
                                                 password='test-password-only',consent=True)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit,range(2)))
        self.assertEqual(outcomes[0]['voucher']['number'],outcomes[1]['voucher']['number'])
        with self.api.state.db.transaction() as conn:
            for table in ('review_decisions','vouchers'):
                self.assertEqual(conn.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT last_number FROM voucher_counters').fetchone()['last_number'],1)

    def test_approval_rechecks_duplicates_after_extraction(self):
        identifier = self.submitted()
        self.assertTrue(self.detail(identifier)['approval']['can_approve'])
        self.sample('wrong_total')
        detail = self.detail(identifier)
        self.assertEqual(detail['status'],'READY_FOR_REVIEW')
        self.assertIn('POSSIBLE_DUPLICATE',[c['code'] for c in detail['approval']['blocking_checks']])
        # 15 Okt 2026: the recheck no longer holds the signature; it puts the duplicate on record for the director.
        approved = self.approve(identifier)
        self.assertEqual(approved.status_code,200,approved.text)
        [event] = [a for a in approved.json()['audit'] if a['action']=='REVIEW_APPROVED']
        self.assertIn('POSSIBLE_DUPLICATE',[c['code'] for c in event['changes']['open_checks']])

    def test_missing_data_holds_approval_while_other_checks_are_finance_calls(self):
        # 15 Okt 2026: an empty required field, or a currency the tax cannot be computed in, still holds the signature.
        # A total or an account that differs is flagged, and Finance decides with a review note.
        identifier = self.submitted()
        base = self.detail(identifier)['draft']['invoice']
        for version,change in [(1,{'payment':{**base['payment'],'account_number':None}}),(2,{'currency':'USD'})]:
            result = self.edit(identifier,{**deepcopy(base),**change},version=version)
            self.assertEqual(result.status_code,200,result.text)
            rejected = self.approve(identifier,version=version+1)
            self.assertEqual(rejected.status_code,422,rejected.text)
        invoice = deepcopy(base)
        invoice['stated_total'] = '510000'
        invoice['payment']['account_number'] = '00001234'
        self.assertEqual(self.edit(identifier,invoice,version=3).status_code,200)
        approved = self.approve(identifier,version=4)
        self.assertEqual(approved.status_code,200,approved.text)
        [event] = [a for a in approved.json()['audit'] if a['action']=='REVIEW_APPROVED']
        self.assertLessEqual({'TOTAL_MISMATCH','BANK_MISMATCH'},{c['code'] for c in event['changes']['open_checks']})

    def test_human_source_review_preserves_original_evidence_and_signed_checks(self):
        # The account is a required field, so the PIC fills it before submitting.
        self.login('pic@amiga.local')
        identifier = self.sample('missing_bank')
        original = self.detail(identifier)['draft']
        invoice = deepcopy(original['invoice'])
        invoice['payment']['account_number']='00123456'
        self.assertEqual(self.edit(identifier,invoice).status_code,200)
        self.pic_submit(identifier,version=2)
        self.login('finance@amiga.local')
        self.assertEqual(self.approve(identifier,version=2,source_reviewed=False).status_code,422)
        response = self.approve(identifier,version=2)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['draft']['source_evidence'],original['source_evidence'])
        record = self.record(identifier,2)
        checks=record['payload']['source_review']['reviewed_checks']
        self.assertIn('HUMAN_CORRECTION_PENDING',[c['code'] for c in checks])
        self.assertTrue(self.api.state.review.process_next())

    def test_revision_invalidates_old_link_without_changing_pdf_or_decision(self):
        identifier=self.submitted()
        self.assertEqual(self.approve(identifier).status_code,200)
        self.api.state.review.process_next()
        old_pdf=self.voucher(identifier).content
        old_record=self.record(identifier)
        invoice=deepcopy(old_record['payload']['invoice'])
        invoice['due_date']='2026-11-30'
        changed=self.edit(identifier,invoice).json()
        self.assertIsNone(changed['approved_version'])
        self.assertIsNone(changed['voucher'])
        self.assertEqual(self.voucher(identifier).status_code,409)
        self.assertEqual(self.retry(identifier).status_code,409)
        self.assertEqual(self.approve(identifier).status_code,409)
        self.assertEqual((self.api.state.review.directory/old_record['document_key']).read_bytes(),old_pdf)
        self.assertIsNotNone(self.record(identifier)['superseded_at'])
        self.assertEqual(self.approve(identifier,version=2).status_code,200)
        self.api.state.review.process_next()
        self.assertNotEqual(self.record(identifier,2)['number'],old_record['number'])
        self.assertEqual(self.record(identifier)['payload'],old_record['payload'])
        self.assertEqual(self.record(identifier,2)['payload']['invoice'],invoice)
        self.assertEqual(self.voucher(identifier,2).status_code,200)
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM review_decisions').fetchone()['n'],2)

    def test_edit_before_render_does_not_publish_obsolete_voucher(self):
        identifier=self.submitted()
        self.approve(identifier)
        invoice=deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['due_date']='2026-11-30'
        self.edit(identifier,invoice)
        self.assertFalse(self.api.state.review.process_next())
        self.assertEqual(self.voucher(identifier).status_code,409)
        self.assertIsNone(self.record(identifier)['payload']['invoice']['due_date'])

    def test_render_failure_retries_same_snapshot_without_new_number(self):
        identifier=self.submitted()
        self.approve(identifier)
        record=self.record(identifier)
        attempts=[]
        def fail(payload, **options):
            attempts.append(deepcopy(payload))
            raise RuntimeError('Test local render interruption')
        self.api.state.review.renderer=fail
        self.api.state.review.process_next()
        detail=self.detail(identifier)
        self.assertEqual(detail['status'],'AMIGA_REVIEWED')
        self.assertEqual(detail['voucher']['render_status'],'FAILED')
        self.assertFalse(self.api.state.review.process_next())
        self.assertEqual(self.retry(identifier).status_code,200)
        def success(payload, **options):
            attempts.append(deepcopy(payload))
            return render_voucher(payload, **options)
        self.api.state.review.renderer=success
        self.api.state.review.process_next()
        self.assertEqual(attempts,[record['payload'],record['payload']])
        result=self.record(identifier)
        self.assertEqual(result['number'],record['number'])
        self.assertEqual(result['decision_id'],record['decision_id'])
        self.assertEqual(result['attempt_count'],2)
        self.assertEqual(self.voucher(identifier).status_code,200)

    def test_interrupted_render_recovers_and_valid_existing_file_is_reused(self):
        identifier=self.submitted()
        self.approve(identifier)
        record=self.record(identifier)
        # The worker stamps the reviewer's specimen, so the file it wrote before the crash carries it too.
        with self.api.state.db.transaction() as conn:
            images=self.api.state.review.specimen_images(conn,record['payload']['signatures']['reviewer']['specimen_sha256'])
        pdf=render_voucher(record['payload'],specimens=images)
        (self.api.state.review.directory/(str(record['id'])+'.pdf')).write_bytes(pdf)
        with self.api.state.db.transaction() as conn:
            conn.execute("UPDATE vouchers SET render_status='RENDERING',attempt_count=1 WHERE request_id=%s",(identifier,))
            self.api.state.review.recover(conn)
        self.assertEqual(self.record(identifier)['error_code'],'VOUCHER_RENDER_INTERRUPTED')
        self.retry(identifier)
        self.api.state.review.process_next()
        self.assertEqual(self.voucher(identifier).content,pdf)

    def test_immutable_decision_payload_and_tampered_file_are_rejected(self):
        identifier=self.submitted()
        self.approve(identifier)
        for query in ("UPDATE review_decisions SET reason='changed' WHERE request_id=%s",
                      "UPDATE vouchers SET payload='{}' WHERE request_id=%s"):
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.api.state.db.transaction() as conn:
                    conn.execute(query,(identifier,))
        self.api.state.review.process_next()
        record=self.record(identifier)
        with self.assertRaises(psycopg.errors.RaiseException):
            with self.api.state.db.transaction() as conn:
                conn.execute("UPDATE vouchers SET pdf_sha256='changed' WHERE request_id=%s",(identifier,))
        (self.api.state.review.directory/record['document_key']).write_bytes(b'Test corrupted file')
        response=self.voucher(identifier)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['code'],'VOUCHER_CHANGED')

    def test_source_document_changed_blocks_approval(self):
        # Since stage 6 the original lives in request_files. The disk copy is a preview cache, so damaging it
        # changes nothing, and the database copy refuses every change.
        identifier=self.submitted()
        with self.api.state.db.transaction() as conn:
            row=conn.execute('SELECT * FROM requests WHERE id=%s',(identifier,)).fetchone()
        self.api.state.service.document_path(row['document_key']).write_bytes(b'Test changed source')
        for statement,values in (('UPDATE request_files SET content=%s WHERE request_id=%s',(b'Test changed source',identifier)),
                                 ('UPDATE requests SET pdf_sha256=%s WHERE id=%s',('0'*64,identifier))):
            with self.assertRaises(psycopg.errors.RaiseException), self.api.state.db.transaction() as conn:
                conn.execute(statement,values)
        # A hash that no longer matches the stored bytes still blocks with DOCUMENT_CHANGED.
        with self.assertRaises(Exception) as caught, self.api.state.db.transaction() as conn:
            self.api.state.service.original_bytes(conn,dict(row,pdf_sha256='0'*64))
        self.assertEqual(caught.exception.code,'DOCUMENT_CHANGED')
        response=self.approve(identifier)
        self.assertEqual(response.status_code,200,response.text)
        document=self.client.get(f'/api/v1/requests/{identifier}/document')
        self.assertEqual(hashlib.sha256(document.content).hexdigest(),row['pdf_sha256'])

    def test_long_pdf_is_deterministic_and_preserves_all_rows(self):
        identifier=self.submitted()
        self.approve(identifier)
        payload=deepcopy(self.record(identifier)['payload'])
        template=payload['invoice']['line_items'][0]
        payload['invoice']['line_items']=[dict(template,line_number=i,description=f'Baris {i:03d} <uji> & data panjang '+('rincian ' * 8)) for i in range(1,61)]
        first=render_voucher(payload)
        self.assertEqual(first,render_voucher(payload))
        reader=PdfReader(BytesIO(first))
        self.assertGreater(len(reader.pages),2)
        self.assertIn('Baris 001',reader.pages[0].extract_text())
        text='\n'.join(page.extract_text() for page in reader.pages)
        for i in range(1,61):
            self.assertIn(f'Baris {i:03d} <uji> &',text)
        for page in reader.pages:
            self.assertIn('Halaman ',page.extract_text())
        # Retained for visual QA. Synthetic formatting stress case, not a valid invoice.
        (self.settings.data_dir/'voucher-layout-stress.pdf').write_bytes(first)

    def test_other_charges_print_only_when_the_invoice_has_them(self):
        identifier=self.submitted()
        self.approve(identifier)
        payload=deepcopy(self.record(identifier)['payload'])
        text=lambda pdf:' '.join(' '.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages).split())
        self.assertNotIn('Biaya lain',text(render_voucher(payload)))
        payload['invoice']['stated_other_charges_total']='600000.00'
        self.assertIn('Biaya lain 600.000',text(render_voucher(payload)))


if __name__=='__main__':
    unittest.main(verbosity=2)
