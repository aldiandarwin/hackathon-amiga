"""Multiple upload acceptance against PostgreSQL, with no real provider calls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from unittest.mock import patch
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import create_app
from app.service import sample_input
from app.tests import test_app as fixtures


class BatchAcceptanceTests(unittest.TestCase):
    login=fixtures.DatabaseAcceptanceTests.login

    def setUp(self):
        fixtures.DatabaseAcceptanceTests.setUp(self)
        self.login('pic@amiga.local')  # since 15 Oct only the PIC uploads
    forbid_live=staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    @staticmethod
    def descriptor(data, name='invoice.pdf'):
        return {'filename':name,'byte_size':len(data),'sha256':hashlib.sha256(data).hexdigest()}

    def create(self, items, key=None, client='client_a', **extras):
        return self.client.post('/api/v1/intake-batches',headers={'Idempotency-Key':key or str(uuid4())},
                                json={'client_id':client,'items':items,**extras})

    def receive(self, identifier, position, data, **headers):
        return self.client.post(f'/api/v1/intake-batches/{identifier}/items/{position}',content=data,
                                headers={'Content-Type':'application/pdf',**headers})

    def detail(self, identifier):
        response=self.client.get('/api/v1/intake-batches/'+str(identifier))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def demo(self, key=None):
        response=self.client.post('/api/v1/demo-batches/mixed?client_id=client_a',
                                  headers={'Idempotency-Key':key or str(uuid4())})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def install_fake(self):
        calls=[]
        class FakeClient:
            def preflight(self):
                pass

            def extract_pdf(self, data, case_id):
                calls.append(case_id)
                saved=sample_input('normal')[1]
                raw={'invoice':saved['invoice'],'evidence':[{'field':path,'page':entry['page'],'raw_value':entry['raw_value']}
                     for path,entry in saved['source_evidence'].items() if entry]}
                return {'run_id':str(uuid4()),'duration_ms':0,'cost_upper_estimate_usd':'0','usage':{},'prompt_version':'BATCH_TEST_NO_NETWORK',
                        'response':{'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(raw)}]}]}}
        self.api.state.service.live_client_factory=FakeClient
        return calls

    def test_mixed_raw_upload_rejects_one_file_and_processes_the_others(self):
        calls=self.install_fake()
        data=[sample_input('normal')[0],b'Broken synthetic PDF',sample_input('missing_bank')[0]]
        response=self.create([self.descriptor(value,f'file-{i}.pdf') for i,value in enumerate(data)])
        self.assertEqual(response.status_code,201,response.text)
        identifier=response.json()['id']
        for position,value in enumerate(data,1):
            self.assertEqual(self.receive(identifier,position,value).status_code,202)
        result=self.detail(identifier)
        self.assertEqual(result['counts'],{'pending':0,'accepted':2,'rejected':1})
        self.assertEqual(result['items'][1]['error_code'],'INVALID_DOCUMENT')
        self.assertIsNone(result['items'][1]['request_id'])
        self.assertTrue(result['upload_complete'])
        self.assertEqual(calls,[])
        self.assertTrue(self.api.state.service.process_next())
        self.assertTrue(self.api.state.service.process_next())
        self.assertFalse(self.api.state.service.process_next())
        self.assertEqual(len(calls),2)
        self.assertTrue(all(item['request_status'] in ('READY_FOR_REVIEW','EXCEPTION') for item in self.detail(identifier)['items'] if item['request_id']))

    def test_replay_demo_is_bounded_and_never_uses_provider(self):
        key=str(uuid4())
        batch=self.demo(key)
        self.assertEqual(batch['mode'],'REPLAY')
        self.assertEqual(batch['counts'],{'pending':0,'accepted':2,'rejected':1})
        self.assertEqual(self.demo(key)['id'],batch['id'])
        while self.api.state.service.process_next():
            pass
        other=self.demo()
        self.assertEqual([i['request_id'] for i in batch['items']],[i['request_id'] for i in other['items']])
        self.assertFalse(any(i['request_created'] for i in other['items']))
        self.assertFalse(self.api.state.service.process_next())

    def test_duplicate_bytes_and_repeated_item_do_not_enqueue_twice(self):
        data=sample_input('normal')[0]
        batch=self.create([self.descriptor(data,'one.pdf'),self.descriptor(data,'two.pdf')]).json()
        for position in (1,1,2):
            self.assertEqual(self.receive(batch['id'],position,data).status_code,202)
        items=self.detail(batch['id'])['items']
        self.assertEqual(items[0]['request_id'],items[1]['request_id'])
        self.assertTrue(items[0]['request_created'])
        self.assertFalse(items[1]['request_created'])
        self.assertEqual(self.receive(batch['id'],1,b'changed').status_code,409)
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM jobs').fetchone()['n'],1)
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM audit_events WHERE action='BATCH_RECEIVED'").fetchone()['n'],2)

    def test_manifest_idempotency_and_payload_mismatch(self):
        data=sample_input('normal')[0]
        items=[self.descriptor(data)]
        key=str(uuid4())
        first=self.create(items,key=key).json()
        self.assertEqual(self.create(items,key=key).json()['id'],first['id'])
        items[0]['filename']='changed.pdf'
        self.assertEqual(self.create(items,key=key).status_code,409)
        self.assertEqual(self.receive(first['id'],1,b'different bytes').status_code,202)
        result=self.detail(first['id'])['items'][0]
        self.assertEqual(result['status'],'REJECTED')
        self.assertEqual(result['error_code'],'MANIFEST_MISMATCH')
        self.receive(first['id'],1,data)
        self.assertEqual(self.detail(first['id'])['items'][0]['status'],'REJECTED')
        self.assertFalse(self.api.state.service.process_next())

    def test_oversized_empty_and_non_pdf_manifest_items_are_independent(self):
        items=[{'filename':'large.pdf','byte_size':5_000_001,'sha256':'0'*64},
               self.descriptor(b'','empty.pdf'),self.descriptor(b'x','notes.txt'),self.descriptor(sample_input('normal')[0])]
        batch=self.create(items).json()
        self.assertEqual(batch['counts'],{'pending':1,'accepted':0,'rejected':3})
        self.assertEqual([i['error_code'] for i in batch['items'][:3]],['FILE_TOO_LARGE','INVALID_DOCUMENT','INVALID_FILENAME'])
        self.assertEqual(self.receive(batch['id'],4,sample_input('normal')[0]).status_code,202)
        self.assertEqual(self.detail(batch['id'])['counts']['accepted'],1)

    def test_actual_oversize_body_is_rejected_and_persisted(self):
        batch=self.create([self.descriptor(b'expected')]).json()
        response=self.receive(batch['id'],1,b'%PDF-'+b'x'*5_000_000)
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(response.json()['items'][0]['error_code'],'FILE_TOO_LARGE')
        self.assertFalse(self.api.state.service.process_next())

    def test_encrypted_excess_pages_and_wrong_content_type_are_rejected(self):
        data=[]
        for encrypted,count in ((True,1),(False,6)):
            writer,stream=PdfWriter(),BytesIO()
            for _ in range(count):writer.add_blank_page(width=200,height=200)
            if encrypted:writer.encrypt('test-only')
            writer.write(stream);data.append(stream.getvalue())
        data.append(sample_input('normal')[0])
        batch=self.create([self.descriptor(value,f'{i}.pdf') for i,value in enumerate(data)]).json()
        for position,value in enumerate(data,1):
            self.receive(batch['id'],position,value,**({'Content-Type':'text/plain'} if position==3 else {}))
        self.assertEqual([i['error_code'] for i in self.detail(batch['id'])['items']],['ENCRYPTED_PDF','PAGE_LIMIT','INVALID_DOCUMENT'])
        self.assertFalse(self.api.state.service.process_next())

    def test_batch_contract_limits_and_mode_cannot_be_supplied_by_browser(self):
        descriptor=self.descriptor(b'x')
        for items,extras in (([],{}),([descriptor]*6,{}),([descriptor],{'mode':'REPLAY'}),
                             ([descriptor|{'sample_name':'normal'}],{}),([descriptor|{'filename':'../secret.pdf'}],{}),
                             ([descriptor|{'byte_size':True}],{})):
            with self.subTest(items=items,extras=extras):
                self.assertEqual(self.create(items,**extras).status_code,422)

    def test_assignment_owner_csrf_and_anonymous_access(self):
        batch=self.create([self.descriptor(b'x')]).json()
        identifier=batch['id']
        self.login('finance@amiga.local')
        self.assertFalse(self.detail(identifier)['can_upload'])
        self.assertEqual(self.receive(identifier,1,b'x').status_code,403)
        self.assertEqual(self.create([self.descriptor(b'x')]).status_code,403)  # Finance does not upload
        self.login('finance.b@amiga.local')
        self.assertEqual(self.client.get('/api/v1/intake-batches/'+identifier).status_code,404)
        self.assertEqual(self.client.get('/api/v1/intake-batches?client_id=client_a').status_code,404)
        self.assertEqual(self.receive(identifier,1,b'x').status_code,404)
        self.assertEqual(self.create([self.descriptor(b'x')]).status_code,404)
        self.client.headers.pop('X-CSRF-Token')
        self.assertEqual(self.create([self.descriptor(b'x')],client='client_b').status_code,403)
        self.client.cookies.clear()
        self.assertEqual(self.client.get('/api/v1/intake-batches/'+identifier).status_code,401)

    def test_interrupted_upload_manifest_survives_restart_and_can_resume(self):
        data=sample_input('normal')[0]
        batch=self.create([self.descriptor(data),self.descriptor(b'broken','later.pdf')]).json()
        self.receive(batch['id'],1,data)
        restarted=create_app(self.settings,start_worker=False,live_client_factory=self.forbid_live)
        with TestClient(restarted) as client:
            login=client.post('/api/v1/login',json={'email':'pic@amiga.local','password':'test-password-only'})
            client.headers['X-CSRF-Token']=login.json()['csrf']
            restored=client.get('/api/v1/intake-batches/'+batch['id']).json()
            self.assertEqual(restored['counts'],{'pending':1,'accepted':1,'rejected':0})
            result=client.post(f"/api/v1/intake-batches/{batch['id']}/items/2",content=b'broken',headers={'Content-Type':'application/pdf'})
            self.assertEqual(result.json()['counts'],{'pending':0,'accepted':1,'rejected':1})
            self.assertEqual(client.get('/api/v1/intake-batches?client_id=client_a').json()['items'][0]['id'],batch['id'])

    def test_concurrent_resubmission_links_one_request(self):
        data=sample_input('normal')[0]
        batch=self.create([self.descriptor(data)]).json()
        user=self.client.get('/api/v1/session').json()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes=list(executor.map(lambda _:self.api.state.batches.receive(batch['id'],1,user,data),range(2)))
        self.assertEqual(outcomes[0]['items'][0]['request_id'],outcomes[1]['items'][0]['request_id'])
        with self.api.state.db.transaction() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM requests').fetchone()['n'],1)

    def test_item_request_job_and_audit_rollback_together(self):
        data=sample_input('normal')[0]
        batch=self.create([self.descriptor(data)]).json()
        user=self.client.get('/api/v1/session').json()
        original=self.api.state.db.audit
        def fail_batch_audit(conn,request_id,actor,action,*args):
            if action=='BATCH_RECEIVED':raise RuntimeError('Test failed database-side operation')
            return original(conn,request_id,actor,action,*args)
        with patch.object(self.api.state.db,'audit',side_effect=fail_batch_audit):
            with self.assertRaises(RuntimeError):
                self.api.state.batches.receive(batch['id'],1,user,data)
        self.assertEqual(self.detail(batch['id'])['items'][0]['status'],'PENDING')
        with self.api.state.db.transaction() as conn:
            for table in ('requests','jobs','audit_events'):
                self.assertEqual(conn.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n'],0)
        self.assertEqual(self.receive(batch['id'],1,data).status_code,202)


if __name__=='__main__':
    unittest.main(verbosity=2)
