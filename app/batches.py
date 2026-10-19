"""Durable, bounded multiple-file intake. Uses the same invoice and budget path."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from . import taxes
from .service import EXTENSIONS, AppError, sample_input
from .settings import MAX_BATCH_FILES, MAX_PDF_BYTES


class BatchService:
    def __init__(self, invoices):
        self.invoices, self.db = invoices, invoices.db

    @staticmethod
    def assigned(user, client_id):
        if client_id not in {client['id'] for client in user['clients']}:
            raise AppError('NOT_FOUND','Klien tidak tersedia.',404)

    def scoped(self, conn, identifier, user):
        row=conn.execute('SELECT b.*,u.name AS uploader FROM upload_batches b '
            'JOIN assignments a ON a.client_id=b.client_id AND a.user_id=%s '
            'JOIN users u ON u.id=b.uploaded_by WHERE b.id=%s',(user['id'],identifier)).fetchone()
        if not row:
            raise AppError('NOT_FOUND','Batch tidak ditemukan.',404)
        return row

    def create(self, user, client_id, items, key, *, samples=None):
        self.assigned(user,client_id)
        if user['role'] != 'PIC':
            raise AppError('FORBIDDEN','Unggah invoice hanya untuk PIC Intake.',403)
        if not 1 <= len(items) <= MAX_BATCH_FILES:
            raise AppError('BATCH_LIMIT','Pilih satu hingga lima file.')
        try:
            # The key stays absent without a selection, so older manifests keep their digest.
            items=[item|{'tax_selection':taxes.normalize_selection(item['tax_selection'])} if item.get('tax_selection') else item
                   for item in items]
        except ValueError:
            raise AppError('INVALID_PAYLOAD','Pilihan pajak tidak valid.') from None
        mode='REPLAY' if samples else 'OPENAI'
        manifest=json.dumps({'client_id':client_id,'mode':mode,'items':items,'samples':samples},sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(manifest.encode()).hexdigest()
        identifier=str(uuid4())
        with self.db.transaction() as conn:
            row=conn.execute('INSERT INTO upload_batches(id,client_id,uploaded_by,idempotency_key,manifest_sha256,mode) '
                'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(uploaded_by,idempotency_key) DO NOTHING RETURNING id',
                (identifier,client_id,user['id'],key,digest,mode)).fetchone()
            if not row:
                prior=conn.execute('SELECT * FROM upload_batches WHERE uploaded_by=%s AND idempotency_key=%s',
                                   (user['id'],key)).fetchone()
                if prior['manifest_sha256']!=digest:
                    raise AppError('IDEMPOTENCY_CONFLICT','Kunci batch sudah dipakai untuk pilihan file yang berbeda.',409)
                identifier=str(prior['id'])
            else:
                for position,item in enumerate(items,1):
                    code,message=None,None
                    if item['byte_size']>MAX_PDF_BYTES:
                        code,message='FILE_TOO_LARGE','Ukuran file maksimal 5 MB.'
                    elif item['byte_size']==0:
                        code,message='INVALID_DOCUMENT','File kosong tidak dapat diproses.'
                    elif Path(item['filename']).suffix.lower() not in EXTENSIONS or len(item['filename'])>180:
                        code,message='INVALID_FILENAME','Nama file harus berakhiran .pdf, .jpg, .jpeg, atau .png dan maksimal 180 karakter.'
                    conn.execute('INSERT INTO upload_batch_items(batch_id,position,filename,byte_size,pdf_sha256,sample_name,'
                        'tax_selection,status,error_code,error_message,received_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'
                        'CASE WHEN %s THEN now() ELSE NULL END)',
                        (identifier,position,item['filename'],item['byte_size'],item['sha256'],
                         samples[position-1] if samples else None,
                         Jsonb(item['tax_selection']) if item.get('tax_selection') else None,
                         'REJECTED' if code else 'PENDING',code,message,bool(code)))
        return self.detail(identifier,user)

    def detail(self, identifier, user):
        with self.db.transaction() as conn:
            row=self.scoped(conn,identifier,user)
            items=conn.execute('SELECT i.position,i.filename,i.byte_size,i.pdf_sha256 AS sha256,i.tax_selection,i.status,i.request_id,'
                'i.request_created,i.error_code,i.error_message,i.received_at,r.status AS request_status,'
                'r.error_code AS processing_error,r.current_version FROM upload_batch_items i '
                'LEFT JOIN requests r ON r.id=i.request_id WHERE i.batch_id=%s ORDER BY i.position',(identifier,)).fetchall()
        counts={status.lower():sum(item['status']==status for item in items) for status in ('PENDING','ACCEPTED','REJECTED')}
        return {k:row[k] for k in ('id','client_id','mode','created_at','uploader')} | {
            'items':items,'counts':counts,'upload_complete':counts['pending']==0,
            'can_upload':row['uploaded_by']==user['id'] and user['role']=='PIC'}

    def listing(self, client_id, user):
        self.assigned(user,client_id)
        with self.db.transaction() as conn:
            rows=conn.execute('SELECT b.id,b.mode,b.created_at,u.name AS uploader,count(*) AS total,'
                "count(*) FILTER(WHERE i.status='PENDING') AS pending,"
                "count(*) FILTER(WHERE i.status='ACCEPTED') AS accepted,"
                "count(*) FILTER(WHERE i.status='REJECTED') AS rejected "
                'FROM upload_batches b JOIN users u ON u.id=b.uploaded_by JOIN upload_batch_items i ON i.batch_id=b.id '
                'WHERE b.client_id=%s GROUP BY b.id,u.name ORDER BY b.created_at DESC LIMIT 20',(client_id,)).fetchall()
        return {'items':rows,'limit':20}

    def authorize_upload(self, identifier, position, user):
        with self.db.transaction() as conn:
            row=self.scoped(conn,identifier,user)
            if row['uploaded_by']!=user['id'] or user['role']!='PIC':
                raise AppError('FORBIDDEN','Hanya pengunggah batch dapat mengirim file ini.',403)
            if not conn.execute('SELECT 1 FROM upload_batch_items WHERE batch_id=%s AND position=%s',(identifier,position)).fetchone():
                raise AppError('NOT_FOUND','File dalam batch tidak ditemukan.',404)

    def receive(self, identifier, position, user, data, *, content_type='application/pdf', too_large=False):
        with self.db.transaction() as conn:
            row=self.scoped(conn,identifier,user)
            if row['uploaded_by']!=user['id'] or user['role']!='PIC':
                raise AppError('FORBIDDEN','Hanya pengunggah batch dapat mengirim file ini.',403)
            conn.execute('SELECT id FROM clients WHERE id=%s FOR UPDATE',(row['client_id'],))
            item=conn.execute('SELECT * FROM upload_batch_items WHERE batch_id=%s AND position=%s FOR UPDATE',
                              (identifier,position)).fetchone()
            if not item:
                raise AppError('NOT_FOUND','File dalam batch tidak ditemukan.',404)
            if item['status']=='REJECTED':
                pass  # Terminal file rejection remains visible; use a new manifest for a corrected file.
            elif item['status']=='ACCEPTED':
                if too_large or len(data)!=item['byte_size'] or hashlib.sha256(data).hexdigest()!=item['pdf_sha256']:
                    raise AppError('IDEMPOTENCY_CONFLICT','File berbeda dari unggahan yang sudah diterima.',409)
            else:
                try:
                    if too_large or len(data)>MAX_PDF_BYTES:
                        raise AppError('FILE_TOO_LARGE','Ukuran file maksimal 5 MB.',413)
                    if len(data)!=item['byte_size'] or hashlib.sha256(data).hexdigest()!=item['pdf_sha256']:
                        raise AppError('MANIFEST_MISMATCH','File berbeda dari pilihan awal; pilih ulang sebagai batch baru.')
                    if content_type.split(';')[0]!=EXTENSIONS.get(Path(item['filename']).suffix.lower()):
                        raise AppError('INVALID_DOCUMENT','Jenis file tidak cocok dengan namanya. Unggah PDF, JPG, atau PNG.',415)
                    if row['mode']=='REPLAY':
                        if not item['sample_name']:
                            raise AppError('INVALID_DOCUMENT','Contoh ini sengaja berupa file rusak untuk uji batch.')
                        expected,_=sample_input(item['sample_name'])
                        if expected!=data:
                            raise AppError('SAMPLE_CHANGED','Dokumen berbeda dari contoh yang disiapkan.')
                    request_id,created=self.invoices.intake(data,user,row['client_id'],item['filename'],
                        f'batch-{identifier}-{position}',item['sample_name'],connection=conn,tax_selection=item['tax_selection'])
                    conn.execute("UPDATE upload_batch_items SET status='ACCEPTED',request_id=%s,request_created=%s,received_at=now() "
                                 'WHERE batch_id=%s AND position=%s',(request_id,created,identifier,position))
                    version=conn.execute('SELECT current_version FROM requests WHERE id=%s',(request_id,)).fetchone()['current_version']
                    self.db.audit(conn,request_id,user['id'],'BATCH_RECEIVED','Invoice diterima melalui batch.',
                                  {'batch_id':str(identifier),'position':position,'reused':not created},version)
                except AppError as error:
                    conn.execute("UPDATE upload_batch_items SET status='REJECTED',error_code=%s,error_message=%s,received_at=now() "
                                 'WHERE batch_id=%s AND position=%s',(error.code,str(error),identifier,position))
        return self.detail(identifier,user)

    def demo(self, user, client_id, key):
        # Fixed server-owned inputs only: no arbitrary document can masquerade as a free replay.
        samples=['normal',None,'missing_bank']
        data=[sample_input('normal')[0],b'AMIGA synthetic invalid PDF',sample_input('missing_bank')[0]]
        names=['contoh-lengkap.pdf','contoh-rusak.pdf','contoh-rekening-kosong.pdf']
        items=[{'filename':name,'byte_size':len(value),'sha256':hashlib.sha256(value).hexdigest(),
                'tax_selection':taxes.SAMPLE_SELECTION} for name,value in zip(names,data)]
        batch=self.create(user,client_id,items,key,samples=samples)
        for position,value in enumerate(data,1):
            batch=self.receive(batch['id'],position,user,value)
        return batch
