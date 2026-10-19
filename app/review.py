"""Independent internal review and durable, version-bound demo vouchers."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .service import REQUIRED_LABELS, AppError, missing_required
from .signing import DIRECTOR_CONSENT, INTAKE_CONSENT, REVIEWER_CONSENT, SignatureGuard, content_sha256, new_verification_code
from .voucher_pdf import TEMPLATE_VERSION, render_voucher


CLIENT_CODES = {'client_a': 'ARS', 'client_b': 'BMP'}
# Only these templates print a box for the final approver, so only their vouchers can carry that approval.
SIGNED_TEMPLATES = ('amiga-demo-v4', 'amiga-demo-v5', 'amiga-demo-v6', 'amiga-demo-v7', 'amiga-demo-v8')
# From v7 the printed voucher has empty boxes for wet signatures; the approval steps stay as the app's record.
WET_SIGNATURE_TEMPLATES = ('amiga-demo-v7', 'amiga-demo-v8')


def voucher_number(client_id, sequence, at, code=None):
    """AMIGA numbers vouchers as running number, month, year (10792-10-2026). The client code keeps numbers unique
    across clients: clients.code since the portfolios, CLIENT_CODES and a hash for a client without one. Month and year
    follow Jakarta time, the same clock as the counter year."""
    local = at.astimezone(ZoneInfo('Asia/Jakarta'))
    code = code or CLIENT_CODES.get(client_id) or hashlib.sha256(client_id.encode()).hexdigest()[:3].upper()
    return f'{code}-{sequence:05d}-{local.month:02d}-{local.year}'


SOURCE_CHECKS = frozenset({
    'SOURCE_EVIDENCE_INVALID', 'SOURCE_VALUE_MISMATCH', 'AMBIGUOUS_VALUE',
    'OCR_INCOMPLETE', 'VISUAL_REVIEW_REQUIRED', 'HUMAN_CORRECTION_PENDING',
})


class ReviewService:
    def __init__(self, invoices):
        self.invoices, self.db, self.settings = invoices, invoices.db, invoices.settings
        self.directory = self.settings.data_dir / 'vouchers'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.renderer = render_voucher
        self.signatures = SignatureGuard()

    def assess(self, conn, row, draft, user):
        reason = reason_code = None
        if user['role'] != 'FINANCE_REVIEWER':
            reason = 'Persetujuan review hanya tersedia untuk Finance Reviewer.'
            reason_code = 'FINANCE_REQUIRED'
        elif row['uploaded_by'] == user['id']:
            reason = 'Pengunggah tidak dapat menyetujui invoice sendiri. Gunakan reviewer lain.'
            reason_code = 'UPLOADER_CANNOT_REVIEW'
        elif not draft or row['status'] not in ('READY_FOR_REVIEW', 'EXCEPTION', 'RETURNED'):
            reason = 'Invoice belum tersedia untuk persetujuan review.'
            reason_code = 'INVOICE_NOT_READY'
        elif row['submitted_at'] is None:
            reason = 'PIC Intake belum mengajukan invoice ini ke Finance.'
            reason_code = 'NOT_SUBMITTED'
        source_checks, blockers, current = [], [], None
        if draft:
            current, _ = self.invoices.snapshot(conn,row,
                {'invoice':draft['invoice'],'source_evidence':draft['source_evidence']},
                draft.get('human_changed_fields',()),draft.get('source'),tax_selection=draft.get('tax_selection'))
            for check in current['validation']['checks']:
                if check['blocking'] and check['status'] != 'PASSED':
                    (source_checks if check['code'] in SOURCE_CHECKS else blockers).append(check)
        # 15 Okt 2026, Aldian: open checks advise and Finance decides, so they never hold approval. Finance writes why
        # in the review note, and the audit keeps which checks were still open. What stays is data the voucher cannot
        # do without: the six required fields, Finance's own choice of tax, and an amount to pay.
        missing = missing_required(current['invoice']) if current else []
        if missing and reason is None:
            reason = ('Lengkapi isian wajib sebelum menyetujui: '
                      + ', '.join(REQUIRED_LABELS[path] for path in missing) + '.')
            reason_code = 'MISSING_EVIDENCE'
        if current and current['tax']['status'] != 'COMPUTED' and reason is None:
            reason = ('Pilih jenis potongan pajak sebelum menyetujui.' if current['tax']['status'] == 'NOT_SELECTED'
                      else 'Pajak belum dapat dihitung dari total invoice; periksa total sebelum menyetujui.')
            reason_code = 'TAX_SELECTION_REQUIRED' if current['tax']['status'] == 'NOT_SELECTED' else 'TAX_NOT_COMPUTED'
        # The PIC's submit dialog says up front when its vendor will be added to the client's master.
        return {'can_approve':reason is None,'reason':reason,'reason_code':reason_code,'source_checks':source_checks,
                'blocking_checks':blockers,'vendor_known':bool(current and current['resolved_vendor_id'])}, current

    def metadata(self, conn, row, draft, user):
        assessment, fresh = self.assess(conn,row,draft,user)
        # Snapshots saved before 15 Okt 2026 stopped the tax at a PPN conflict. It is computed again on read, so the
        # screen shows the amount Finance would sign for, the same one approve() puts on the voucher.
        stale = (draft and fresh and (draft.get('tax') or {}).get('status') != 'COMPUTED'
                 and fresh['tax']['status'] == 'COMPUTED')
        vouchers = conn.execute('SELECT v.id,v.invoice_version,v.number,v.template_version,v.render_status,'
            'v.error_code,v.superseded_at,v.attempt_count,v.pdf_sha256,d.approved_at,u.name AS reviewer '
            'FROM vouchers v JOIN review_decisions d ON d.id=v.decision_id JOIN users u ON u.id=d.actor_id '
            'WHERE v.request_id=%s ORDER BY v.invoice_version DESC',(row['id'],)).fetchall()
        current = None
        for voucher in vouchers:
            voucher['active'] = voucher['superseded_at'] is None and row['approved_version'] == voucher['invoice_version']
            if voucher['active']:
                current = voucher
                voucher['download_url'] = (f"/api/v1/requests/{row['id']}/voucher?version={voucher['invoice_version']}"
                                           if voucher['render_status']=='READY' else None)
                voucher['can_retry'] = user['role']=='FINANCE_REVIEWER' and voucher['render_status']=='FAILED'
        return {'approval':assessment,'voucher':current,'voucher_history':vouchers,
                'signature':self.signature_state(conn,row,current,user),
                'can_return_to_pic':user['role']=='FINANCE_REVIEWER' and self.returnable(row)} | (
                    {'draft':draft | {'tax':fresh['tax']}} if stale else {})

    @staticmethod
    def returnable(row):
        """Submitted and not signed by Finance yet, including a voucher the director sent back to Finance."""
        return (row['submitted_at'] is not None and row['approved_version'] is None and row['current_version'] >= 1
                and row['status'] in ('READY_FOR_REVIEW','EXCEPTION','RETURNED'))

    def signature_state(self, conn, row, voucher, user):
        """What the signing panels show: who signed, what still waits, and whether this user may act now."""
        steps = conn.execute('SELECT id,kind,voucher_id,signer_name,signer_title,verification_code,reason,signed_at '
                             'FROM approval_steps WHERE request_id=%s ORDER BY signed_at',(row['id'],)).fetchall()
        mine = [step for step in steps if voucher and step['voucher_id']==voucher['id']]
        reviewer = next((step for step in mine if step['kind']=='REVIEWER_SIGNED'),None)
        director = next((step for step in mine if step['kind']=='DIRECTOR_APPROVED'),None)
        returned = next((step for step in reversed(steps) if step['kind']=='DIRECTOR_RETURNED'),None)
        signoff = conn.execute('SELECT render_status,verify_url FROM voucher_signoffs WHERE voucher_id=%s',
                               (voucher['id'],)).fetchone() if voucher else None
        reason = None
        if user['role'] != 'AMIGA_DIRECTOR':
            reason = 'Persetujuan final hanya untuk Manajer Keuangan AMIGA.'
        elif row['status'] != 'AMIGA_REVIEWED':
            reason = 'Voucher ini tidak sedang menunggu persetujuan manajer keuangan.'
        elif voucher and voucher['render_status'] == 'FAILED':
            reason = 'Draf voucher gagal dibuat. Minta Finance mengulang render.'
        elif not voucher or voucher['render_status'] != 'READY':
            reason = 'Draf voucher masih dibuat. Tunggu beberapa detik.'
        elif voucher['template_version'] not in SIGNED_TEMPLATES:
            reason = 'Voucher lama ini belum punya kotak Manajer Keuangan. Kembalikan ke Finance.'

        def public(step):
            return {key:step[key] for key in ('signer_name','signer_title','verification_code','signed_at','reason')} if step else None

        return {'consent_text':DIRECTOR_CONSENT if user['role']=='AMIGA_DIRECTOR'
                    else INTAKE_CONSENT if user['role']=='PIC' else REVIEWER_CONSENT,
                'reviewer':public(reviewer),'director':public(director),
                'returned':public(returned) if row['status']=='RETURNED' else None,
                'can_director_act':reason is None,'director_block_reason':reason,
                'signed_voucher':{'render_status':signoff['render_status'],
                    'download_url':(f"/api/v1/requests/{row['id']}/voucher/signed?version={voucher['invoice_version']}"
                                    if signoff['render_status']=='READY' else None),
                    'can_retry':user['role']=='FINANCE_REVIEWER' and signoff['render_status']=='FAILED'} if signoff else None,
                'verify_url':signoff['verify_url'] if signoff else None}

    @staticmethod
    def specimen(conn, user_id):
        """The signer's current specimen (hash and PNG), or None: a signature without one prints as text only."""
        return conn.execute('SELECT sha256,image_png FROM signature_specimens WHERE user_id=%s '
                            'ORDER BY created_at DESC,sha256 LIMIT 1',(user_id,)).fetchone()

    @staticmethod
    def specimen_images(conn, *hashes):
        wanted = [digest for digest in hashes if digest]
        rows = conn.execute('SELECT sha256,image_png FROM signature_specimens WHERE sha256 = ANY(%s)',
                            (wanted,)).fetchall() if wanted else []
        return {row['sha256']:bytes(row['image_png']) for row in rows}

    def verify_signer(self, request_id, user, password, consent, stage):
        """Consent first, then the password at this moment, before any lock (PBKDF2 takes about 0.07 s on the demo laptop).
        A wrong password is audited without the password itself."""
        if consent is not True:
            raise AppError('CONSENT_REQUIRED','Centang pernyataan sebelum menyetujui.',422)
        if self.signatures.blocked(user['id']):
            raise AppError('SIGNATURE_RATE_LIMIT','Terlalu banyak percobaan persetujuan. Coba lagi 10 menit lagi.',429)
        if password and self.db.verify_password(user['id'],password):
            self.signatures.succeeded(user['id'])
            return
        self.signatures.failed(user['id'])
        with self.db.transaction() as conn:
            row = self.db.scoped_request(conn,request_id,user)
            if row:
                self.db.audit(conn,request_id,user['id'],'SIGN_FAILED','Password persetujuan tidak cocok.',
                              {'stage':stage},row['current_version'])
        raise AppError('SIGNATURE_PASSWORD_INVALID','Password tidak cocok. Persetujuan dibatalkan.',403)

    def approve(self, request_id, user, expected_version, reason, source_reviewed, *, password=None, consent=False,
                client_ip=None, user_agent=None, tax_adjustment_confirmed=False):
        if user['role'] != 'FINANCE_REVIEWER':
            raise AppError('FORBIDDEN','Hanya Finance Reviewer dapat menyetujui review.',403)
        self.verify_signer(request_id,user,password,consent,'REVIEWER')
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Request tidak ditemukan.',404)
            if row['uploaded_by'] == user['id']:
                raise AppError('SELF_APPROVAL_FORBIDDEN','Pengunggah tidak dapat menyetujui invoice sendiri.',403)
            if row['current_version'] != expected_version:
                raise AppError('VERSION_CONFLICT','Versi berubah. Muat ulang sebelum menyetujui.',409)
            if not source_reviewed:
                raise AppError('SOURCE_REVIEW_REQUIRED','Konfirmasi pemeriksaan seluruh dokumen asli diperlukan.')
            # Safe replay of a double click, including simultaneous requests under the client lock.
            if row['approved_version'] == expected_version and row['status'] in ('AMIGA_REVIEWED','AMIGA_APPROVED'):
                return self.invoices.detail(request_id,user)
            if row['status'] not in ('READY_FOR_REVIEW','EXCEPTION','RETURNED') or row['current_version'] < 1:
                raise AppError('INVALID_TRANSITION','Invoice belum dapat disetujui.',409)
            if row['submitted_at'] is None:
                raise AppError('NOT_SUBMITTED','PIC Intake belum mengajukan invoice ini ke Finance.',409)
            draft = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=%s',
                                 (request_id,expected_version)).fetchone()['snapshot']
            assessment, current = self.assess(conn,row,draft,user)
            if not assessment['can_approve']:
                raise AppError('UNRESOLVED_EXCEPTION',assessment['reason'])
            if current['tax'].get('ppn_origin') == 'INTERNAL_ADJUSTMENT' and not tax_adjustment_confirmed:
                raise AppError('TAX_ADJUSTMENT_CONFIRMATION_REQUIRED',
                               'Konfirmasi tambahan PPN dan tindak lanjut dokumen vendor sebelum menyetujui.',422)
            validation = current['validation']
            # The database copy is the original; any change in its bytes blocks approval.
            stored = conn.execute('SELECT content FROM request_files WHERE request_id=%s',(row['id'],)).fetchone()
            data = bytes(stored['content']) if stored else self.invoices.document_path(row['document_key']).read_bytes()
            if hashlib.sha256(data).hexdigest() != row['pdf_sha256']:
                raise AppError('DOCUMENT_CHANGED','Dokumen asli berubah; persetujuan diblokir.')
            now = datetime.now(timezone.utc)
            year = now.astimezone(ZoneInfo('Asia/Jakarta')).year
            sequence = conn.execute('INSERT INTO voucher_counters VALUES (%s,%s,1) ON CONFLICT(client_id,year) '
                'DO UPDATE SET last_number=voucher_counters.last_number+1 RETURNING last_number',
                (row['client_id'],year)).fetchone()['last_number']
            number = voucher_number(row['client_id'],sequence,now,conn.execute(
                'SELECT code FROM clients WHERE id=%s',(row['client_id'],)).fetchone()['code'])
            decision_id, voucher_id = str(uuid4()), str(uuid4())
            client = conn.execute('SELECT id,name FROM clients WHERE id=%s',(row['client_id'],)).fetchone()
            uploader = conn.execute('SELECT id,name FROM users WHERE id=%s',(row['uploaded_by'],)).fetchone()
            # v7 prints the PIC who submitted in the first signature box, so the submission is frozen with the voucher.
            submitter = conn.execute('SELECT id,name,title FROM users WHERE id=%s',(row['submitted_by'],)).fetchone()
            source_review = {'confirmed':True,'reviewed_checks':assessment['source_checks'],
                             'statement':'Reviewer mencocokkan seluruh field dan halaman dokumen asli.'}
            if current['tax'].get('ppn_origin') == 'INTERNAL_ADJUSTMENT':
                source_review['tax_adjustment_confirmed'] = True
            open_checks = [{'code':check['code'],'field':check['field']} for check in assessment['blocking_checks']]
            signer = conn.execute('SELECT name,title FROM users WHERE id=%s',(user['id'],)).fetchone()
            specimen = self.specimen(conn,user['id'])
            directors = conn.execute("SELECT u.name,u.title FROM users u JOIN assignments a ON a.user_id=u.id "
                                     "WHERE a.client_id=%s AND u.role='AMIGA_DIRECTOR' ORDER BY u.id",
                                     (row['client_id'],)).fetchall()
            step_id, code = str(uuid4()), new_verification_code()
            payload = {'number':number,'template_version':TEMPLATE_VERSION,'request_id':str(request_id),
                'invoice_version':expected_version,'invoice':deepcopy(draft['invoice']),
                'tax_selection':deepcopy(current['tax_selection']),'tax':deepcopy(current['tax']),
                'client':client,'uploader':uploader,'reviewer':{'id':user['id'],'name':user['name']},
                'submitter':submitter | {'submitted_at':row['submitted_at'].isoformat()},
                'approved_at':now.isoformat(),'review_note':reason,'source_review':source_review,
                'source_document_sha256':row['pdf_sha256'],'source_mode':row['mode'],
                # Printed in the final approver's box of the draft; the Manajer Keuangan approves the same content later.
                'assigned_director':directors[0] if len(directors)==1 else None,
                'signatures':{'reviewer':{'id':user['id'],'name':signer['name'],
                    'title':signer['title'] or 'Finance Reviewer AMIGA','signed_at':now.isoformat(),'code':code,
                    'specimen_sha256':specimen['sha256'] if specimen else None}}}
            content_hash = content_sha256(payload)
            conn.execute('INSERT INTO review_decisions VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (decision_id,request_id,expected_version,user['id'],reason,Jsonb(source_review),Jsonb(validation),now))
            conn.execute('INSERT INTO vouchers(id,request_id,invoice_version,decision_id,number,template_version,payload,render_status) '
                         "VALUES (%s,%s,%s,%s,%s,%s,%s,'PENDING')",
                         (voucher_id,request_id,expected_version,decision_id,number,TEMPLATE_VERSION,Jsonb(payload)))
            conn.execute('INSERT INTO approval_steps(id,request_id,invoice_version,voucher_id,kind,actor_id,signer_name,'
                         'signer_title,content_sha256,verification_code,auth_method,consent_text,client_ip,user_agent,'
                         "signed_at,specimen_sha256) VALUES (%s,%s,%s,%s,'REVIEWER_SIGNED',%s,%s,%s,%s,%s,'PASSWORD_REENTRY',"
                         '%s,%s,%s,%s,%s)',
                         (step_id,request_id,expected_version,voucher_id,user['id'],signer['name'],
                          payload['signatures']['reviewer']['title'],content_hash,code,REVIEWER_CONSENT,client_ip,
                          user_agent,now,payload['signatures']['reviewer']['specimen_sha256']))
            conn.execute("UPDATE requests SET status='AMIGA_REVIEWED',approved_version=%s,updated_at=now() WHERE id=%s",
                         (expected_version,request_id))
            self.db.audit(conn,request_id,user['id'],'REVIEW_APPROVED',reason,
                {'decision_id':decision_id,'voucher_number':number,'template_version':TEMPLATE_VERSION,
                 'source_review':source_review,'open_checks':open_checks,
                 'signature':{'step_id':step_id,'code':code,'content_sha256':content_hash},
                 'tax':{key:current['tax'][key] for key in ('pph_id','withheld_total','net_payable','rules_version')}},
                expected_version)
        return self.invoices.detail(request_id,user)

    def retry(self, request_id, user, expected_version, reason):
        if user['role'] != 'FINANCE_REVIEWER':
            raise AppError('FORBIDDEN','Pengulangan render hanya tersedia untuk Finance.',403)
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Request tidak ditemukan.',404)
            if row['approved_version'] != expected_version or row['current_version'] != expected_version:
                raise AppError('VERSION_CONFLICT','Voucher tidak lagi aktif untuk versi ini.',409)
            voucher = conn.execute('SELECT * FROM vouchers WHERE request_id=%s AND invoice_version=%s FOR UPDATE',
                                   (request_id,expected_version)).fetchone()
            if not voucher or voucher['superseded_at']:
                raise AppError('VOUCHER_SUPERSEDED','Voucher tidak lagi aktif.',409)
            signoff = conn.execute('SELECT render_status FROM voucher_signoffs WHERE voucher_id=%s FOR UPDATE',
                                   (voucher['id'],)).fetchone()
            if signoff and signoff['render_status'] == 'FAILED':
                # The signed copy renders from the same frozen payload and the same director step.
                conn.execute("UPDATE voucher_signoffs SET render_status='PENDING',error_code=NULL WHERE voucher_id=%s",
                             (voucher['id'],))
                self.db.audit(conn,request_id,user['id'],'SIGNED_VOUCHER_RETRY',reason,{'voucher_number':voucher['number']},
                              expected_version)
                return self.invoices.detail(request_id,user)
            if voucher['render_status'] != 'FAILED':
                raise AppError('INVALID_TRANSITION','Hanya render yang gagal dapat diulang.',409)
            conn.execute("UPDATE vouchers SET render_status='PENDING',error_code=NULL WHERE id=%s",(voucher['id'],))
            self.db.audit(conn,request_id,user['id'],'VOUCHER_RETRY',reason,{'voucher_number':voucher['number']},expected_version)
        return self.invoices.detail(request_id,user)

    def download(self, request_id, user, version):
        with self.db.transaction() as conn:
            row = self.db.scoped_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Voucher tidak tersedia.',404)
            if (row['approved_version'] is None or row['current_version'] != row['approved_version']
                or row['status'] not in ('AMIGA_REVIEWED','AMIGA_APPROVED')
                or (version is not None and version != row['approved_version'])):
                raise AppError('VOUCHER_SUPERSEDED','Versi ini belum disetujui atau voucher lama sudah tidak aktif.',409)
            voucher = conn.execute('SELECT * FROM vouchers WHERE request_id=%s AND invoice_version=%s',
                                   (request_id,row['approved_version'])).fetchone()
            if not voucher or voucher['superseded_at'] or voucher['render_status']!='READY':
                raise AppError('VOUCHER_NOT_READY','Voucher belum selesai dibuat.',409)
            return self.read_pdf(voucher['document_key'],voucher['pdf_sha256']),voucher['number']+'.pdf'

    def download_signed(self, request_id, user, version):
        with self.db.transaction() as conn:
            row = self.db.scoped_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Voucher tidak tersedia.',404)
            if row['status'] != 'AMIGA_APPROVED' or (version is not None and version != row['approved_version']):
                raise AppError('VOUCHER_NOT_SIGNED','Voucher ini belum disetujui manajer keuangan.',409)
            signed = conn.execute('SELECT s.*,v.number FROM voucher_signoffs s JOIN vouchers v ON v.id=s.voucher_id '
                                  'WHERE v.request_id=%s AND v.invoice_version=%s AND v.superseded_at IS NULL',
                                  (request_id,row['approved_version'])).fetchone()
            if not signed or signed['render_status'] != 'READY':
                raise AppError('VOUCHER_NOT_READY','Salinan final belum selesai dibuat.',409)
            return self.read_pdf(signed['document_key'],signed['pdf_sha256']),signed['number']+'-final.pdf'

    def read_pdf(self, key, digest):
        path = (self.directory / key).resolve()
        if not path.is_relative_to(self.directory.resolve()):
            raise AppError('VOUCHER_UNAVAILABLE','Voucher tidak tersedia.',409)
        try:
            data = path.read_bytes()
        except OSError:
            raise AppError('VOUCHER_UNAVAILABLE','File voucher tidak tersedia; hubungi pengelola.',409) from None
        if hashlib.sha256(data).hexdigest() != digest:
            raise AppError('VOUCHER_CHANGED','Integritas file voucher tidak sesuai.',409)
        return data

    def store_pdf(self, key, data):
        digest = hashlib.sha256(data).hexdigest()
        target = self.directory / key
        try:
            with target.open('xb') as output:
                output.write(data)
        except FileExistsError:
            # A crash after writing is recoverable only when the frozen payload renders identically.
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise AppError('VOUCHER_FILE_CONFLICT','File voucher sebelumnya berbeda.')
        return digest

    def process_next(self):
        return self.render_draft() or self.render_signoff()

    def render_draft(self):
        with self.db.transaction() as conn:
            voucher = conn.execute("SELECT * FROM vouchers WHERE render_status='PENDING' AND superseded_at IS NULL "
                                   'ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1').fetchone()
            if not voucher:
                return False
            conn.execute("UPDATE vouchers SET render_status='RENDERING',attempt_count=attempt_count+1 WHERE id=%s",(voucher['id'],))
            reviewer = (voucher['payload'].get('signatures') or {}).get('reviewer') or {}
            images = self.specimen_images(conn,reviewer.get('specimen_sha256'))
        try:
            data = self.renderer(voucher['payload'],specimens=images)
            key = str(voucher['id'])+'.pdf'
            digest = self.store_pdf(key,data)
            with self.db.transaction() as conn:
                conn.execute("UPDATE vouchers SET render_status='READY',document_key=%s,pdf_sha256=%s,rendered_at=now(),error_code=NULL WHERE id=%s",
                             (key,digest,voucher['id']))
                self.db.audit(conn,voucher['request_id'],voucher['payload']['reviewer']['id'],'VOUCHER_READY',
                    'Voucher demo dirender otomatis dari snapshot yang disetujui.',
                    {'voucher_number':voucher['number'],'pdf_sha256':digest},voucher['invoice_version'])
        except Exception as error:
            code = error.code if isinstance(error,AppError) else 'VOUCHER_RENDER_FAILED'
            with self.db.transaction() as conn:
                conn.execute("UPDATE vouchers SET render_status='FAILED',error_code=%s WHERE id=%s",(code,voucher['id']))
                self.db.audit(conn,voucher['request_id'],voucher['payload']['reviewer']['id'],'VOUCHER_FAILED',
                    'Render voucher gagal; keputusan review tetap tersimpan.',
                    {'voucher_number':voucher['number'],'error_code':code},voucher['invoice_version'])
        return True

    def render_signoff(self):
        with self.db.transaction() as conn:
            signoff = conn.execute("SELECT s.*,v.payload,v.request_id,v.invoice_version,v.number FROM voucher_signoffs s "
                                   "JOIN vouchers v ON v.id=s.voucher_id WHERE s.render_status='PENDING' "
                                   'ORDER BY s.created_at FOR UPDATE OF s SKIP LOCKED LIMIT 1').fetchone()
            if not signoff:
                return False
            step = conn.execute('SELECT actor_id,signer_name,signer_title,signed_at,verification_code,content_sha256,'
                                'specimen_sha256 FROM approval_steps WHERE id=%s',(signoff['director_step_id'],)).fetchone()
            conn.execute("UPDATE voucher_signoffs SET render_status='RENDERING',attempt_count=attempt_count+1 "
                         'WHERE voucher_id=%s',(signoff['voucher_id'],))
            images = self.specimen_images(conn,signoff['payload']['signatures']['reviewer'].get('specimen_sha256'),
                                          step['specimen_sha256'])
        details = {'verify_url':signoff['verify_url'],'content_sha256':step['content_sha256'],
                   'director':{'name':step['signer_name'],'title':step['signer_title'],
                               'signed_at':step['signed_at'].isoformat(),'code':step['verification_code'],
                               'specimen_sha256':step['specimen_sha256']}}
        try:
            data = self.renderer(signoff['payload'],details,specimens=images)
            digest = self.store_pdf(str(signoff['voucher_id'])+'-final.pdf',data)
            with self.db.transaction() as conn:
                conn.execute("UPDATE voucher_signoffs SET render_status='READY',document_key=%s,pdf_sha256=%s,"
                             'rendered_at=now(),error_code=NULL WHERE voucher_id=%s',
                             (str(signoff['voucher_id'])+'-final.pdf',digest,signoff['voucher_id']))
                self.db.audit(conn,signoff['request_id'],step['actor_id'],'SIGNED_VOUCHER_READY',
                    'Salinan final yang disetujui Finance dan manajer keuangan dirender otomatis.',
                    {'voucher_number':signoff['number'],'pdf_sha256':digest},signoff['invoice_version'])
        except Exception as error:
            code = error.code if isinstance(error,AppError) else 'VOUCHER_RENDER_FAILED'
            with self.db.transaction() as conn:
                conn.execute("UPDATE voucher_signoffs SET render_status='FAILED',error_code=%s WHERE voucher_id=%s",
                             (code,signoff['voucher_id']))
                self.db.audit(conn,signoff['request_id'],step['actor_id'],'SIGNED_VOUCHER_FAILED',
                    'Render salinan final gagal; persetujuan tetap tersimpan.',
                    {'voucher_number':signoff['number'],'error_code':code},signoff['invoice_version'])
        return True

    def director_approve(self, request_id, user, expected_version, *, password=None, consent=False,
                         client_ip=None, user_agent=None):
        """Stage 2: AMIGA's Manajer Keuangan approves the draft that Finance approved. The final copy reuses the frozen
        payload."""
        if user['role'] != 'AMIGA_DIRECTOR':
            raise AppError('FORBIDDEN','Persetujuan final hanya untuk Manajer Keuangan AMIGA.',403)
        self.verify_signer(request_id,user,password,consent,'DIRECTOR')
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Request tidak ditemukan.',404)
            if row['status'] == 'AMIGA_APPROVED' and row['approved_version'] == expected_version:
                return self.invoices.detail(request_id,user)  # a repeated click under the client lock
            if row['status'] != 'AMIGA_REVIEWED':
                raise AppError('INVALID_TRANSITION','Voucher ini tidak sedang menunggu persetujuan manajer keuangan.',409)
            if row['current_version'] != expected_version or row['approved_version'] != expected_version:
                raise AppError('VERSION_CONFLICT','Data berubah sejak disetujui Finance. Muat ulang.',409)
            if row['uploaded_by'] == user['id']:
                raise AppError('SELF_APPROVAL_FORBIDDEN','Pengunggah tidak dapat menyetujui invoice sendiri.',403)
            voucher = conn.execute('SELECT * FROM vouchers WHERE request_id=%s AND invoice_version=%s AND superseded_at IS NULL',
                                   (request_id,expected_version)).fetchone()
            if not voucher:
                raise AppError('VOUCHER_SUPERSEDED','Voucher sudah diganti. Muat ulang.',409)
            if voucher['template_version'] not in SIGNED_TEMPLATES:
                raise AppError('VOUCHER_TEMPLATE_UNSUPPORTED','Voucher lama ini belum punya kotak Manajer Keuangan.',409)
            if voucher['render_status'] != 'READY':
                raise AppError('VOUCHER_NOT_READY','Draf voucher masih dibuat. Tunggu beberapa detik.',409)
            reviewer = conn.execute("SELECT * FROM approval_steps WHERE voucher_id=%s AND kind='REVIEWER_SIGNED'",
                                    (voucher['id'],)).fetchone()
            if not reviewer:
                raise AppError('REVIEWER_SIGNATURE_MISSING','Persetujuan Finance belum ada.',409)
            if reviewer['actor_id'] == user['id']:
                raise AppError('SELF_APPROVAL_FORBIDDEN','Penyetuju Finance tidak dapat menjadi manajer keuangan.',403)
            content_hash = content_sha256(voucher['payload'])
            if content_hash != reviewer['content_sha256']:
                raise AppError('CONTENT_MISMATCH','Isi voucher tidak cocok dengan persetujuan Finance.',409)
            signer = conn.execute('SELECT name,title FROM users WHERE id=%s',(user['id'],)).fetchone()
            specimen = self.specimen(conn,user['id'])
            now, step_id, code = datetime.now(timezone.utc), str(uuid4()), new_verification_code()
            conn.execute('INSERT INTO approval_steps(id,request_id,invoice_version,voucher_id,kind,actor_id,signer_name,'
                         'signer_title,content_sha256,document_sha256,previous_step_id,verification_code,auth_method,'
                         'consent_text,client_ip,user_agent,signed_at,specimen_sha256) VALUES '
                         "(%s,%s,%s,%s,'DIRECTOR_APPROVED',%s,%s,%s,%s,%s,%s,%s,'PASSWORD_REENTRY',%s,%s,%s,%s,%s)",
                         (step_id,request_id,expected_version,voucher['id'],user['id'],signer['name'],
                          signer['title'] or 'Manajer Keuangan AMIGA',content_hash,voucher['pdf_sha256'],reviewer['id'],code,
                          DIRECTOR_CONSENT,client_ip,user_agent,now,specimen['sha256'] if specimen else None))
            conn.execute("INSERT INTO voucher_signoffs(voucher_id,director_step_id,verify_url,render_status) "
                         "VALUES (%s,%s,%s,'PENDING')",
                         (voucher['id'],step_id,f"{self.settings.public_base_url}/verifikasi/{voucher['id']}"))
            conn.execute("UPDATE requests SET status='AMIGA_APPROVED',updated_at=now() WHERE id=%s",(request_id,))
            self.db.audit(conn,request_id,user['id'],'DIRECTOR_APPROVED','Disetujui Manajer Keuangan AMIGA.',
                          {'step_id':step_id,'code':code,'voucher_number':voucher['number'],'content_sha256':content_hash},
                          expected_version)
        return self.invoices.detail(request_id,user)

    def director_return(self, request_id, user, expected_version, reason, *, client_ip=None, user_agent=None):
        """Back to Finance with a reason. The approved version is copied to a new one, so Finance can correct it or
        sign again without a change, while the returned voucher stays on record as superseded."""
        if user['role'] != 'AMIGA_DIRECTOR':
            raise AppError('FORBIDDEN','Pengembalian hanya untuk Manajer Keuangan AMIGA.',403)
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Request tidak ditemukan.',404)
            if row['status'] != 'AMIGA_REVIEWED':
                raise AppError('INVALID_TRANSITION','Voucher ini tidak sedang menunggu persetujuan manajer keuangan.',409)
            if row['current_version'] != expected_version or row['approved_version'] != expected_version:
                raise AppError('VERSION_CONFLICT','Data berubah. Muat ulang sebelum mengembalikan.',409)
            voucher = conn.execute('SELECT * FROM vouchers WHERE request_id=%s AND invoice_version=%s AND superseded_at IS NULL',
                                   (request_id,expected_version)).fetchone()
            if not voucher:
                raise AppError('VOUCHER_SUPERSEDED','Voucher sudah diganti. Muat ulang.',409)
            reviewer = conn.execute("SELECT id FROM approval_steps WHERE voucher_id=%s AND kind='REVIEWER_SIGNED'",
                                    (voucher['id'],)).fetchone()
            signer = conn.execute('SELECT name,title FROM users WHERE id=%s',(user['id'],)).fetchone()
            now, step_id, code = datetime.now(timezone.utc), str(uuid4()), new_verification_code()
            conn.execute('INSERT INTO approval_steps(id,request_id,invoice_version,voucher_id,kind,actor_id,signer_name,'
                         'signer_title,content_sha256,previous_step_id,verification_code,auth_method,reason,client_ip,'
                         "user_agent,signed_at) VALUES (%s,%s,%s,%s,'DIRECTOR_RETURNED',%s,%s,%s,%s,%s,%s,'SESSION',%s,%s,%s,%s)",
                         (step_id,request_id,expected_version,voucher['id'],user['id'],signer['name'],
                          signer['title'] or 'Manajer Keuangan AMIGA',content_sha256(voucher['payload']),
                          reviewer['id'] if reviewer else None,code,reason,client_ip,user_agent,now))
            conn.execute('UPDATE vouchers SET superseded_at=now() WHERE id=%s',(voucher['id'],))
            snapshot = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=%s',
                                    (request_id,expected_version)).fetchone()['snapshot']
            version = expected_version + 1
            conn.execute('INSERT INTO invoice_versions(request_id,version,snapshot,actor_id) VALUES (%s,%s,%s,%s)',
                         (request_id,version,Jsonb(snapshot),user['id']))
            conn.execute("UPDATE requests SET status='RETURNED',current_version=%s,approved_version=NULL,updated_at=now() "
                         'WHERE id=%s',(version,request_id))
            self.db.audit(conn,request_id,user['id'],'APPROVAL_INVALIDATED',reason,
                          {'previous_approved_version':expected_version},version)
            self.db.audit(conn,request_id,user['id'],'DIRECTOR_RETURNED',reason,
                          {'returned_version':expected_version,'copied_to_version':version,
                           'voucher_number':voucher['number'],'step_id':step_id},version)
        return self.invoices.detail(request_id,user)

    def finance_return(self, request_id, user, expected_version, reason):
        """Finance sends a submitted invoice back to the PIC with a reason. The data stays as it is: the PIC corrects
        it during intake and submits again, and the audit keeps both the submission and the return."""
        if user['role'] != 'FINANCE_REVIEWER':
            raise AppError('FORBIDDEN','Pengembalian ke PIC hanya untuk Finance Reviewer.',403)
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Request tidak ditemukan.',404)
            if not self.returnable(row):
                raise AppError('INVALID_TRANSITION','Invoice ini tidak sedang menunggu keputusan Finance.',409)
            if row['current_version'] != expected_version:
                raise AppError('VERSION_CONFLICT','Data berubah. Muat ulang sebelum mengembalikan.',409)
            snapshot = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=%s',
                                    (request_id,expected_version)).fetchone()['snapshot']
            # A voucher the director returned leaves status RETURNED; back in intake it reads from the checks again.
            status = ('EXCEPTION' if any(c['blocking'] and c['status'] != 'PASSED' for c in snapshot['validation']['checks'])
                      else 'READY_FOR_REVIEW')
            conn.execute('UPDATE requests SET status=%s,submitted_at=NULL,submitted_by=NULL,submitted_version=NULL,'
                         'updated_at=now() WHERE id=%s',(status,request_id))
            self.db.audit(conn,request_id,user['id'],'FINANCE_RETURNED',reason,
                          {'returned_version':expected_version,'submitted_by':row['submitted_by'],
                           'submitted_version':row['submitted_version']},expected_version)
        return self.invoices.detail(request_id,user)

    def verification(self, voucher_id):
        """Public check of one voucher: number, status, signers and hashes. No amount, account or vendor leaves here."""
        with self.db.transaction() as conn:
            voucher = conn.execute('SELECT number,template_version,payload,pdf_sha256,superseded_at FROM vouchers WHERE id=%s',
                                   (voucher_id,)).fetchone()
            if not voucher:
                return None
            steps = conn.execute("SELECT kind,signer_name,signer_title,verification_code,signed_at,content_sha256 "
                                 "FROM approval_steps WHERE voucher_id=%s AND kind IN ('REVIEWER_SIGNED','DIRECTOR_APPROVED') "
                                 'ORDER BY signed_at',(voucher_id,)).fetchall()
            signoff = conn.execute('SELECT pdf_sha256 FROM voucher_signoffs WHERE voucher_id=%s',(voucher_id,)).fetchone()
        content = content_sha256(voucher['payload'])
        status = ('DIGANTIKAN' if voucher['superseded_at'] else
                  'SAH' if any(step['kind']=='DIRECTOR_APPROVED' for step in steps) else 'MENUNGGU_DIREKSI')

        def jakarta(moment):
            return moment.astimezone(ZoneInfo('Asia/Jakarta')).strftime('%d-%m-%Y %H:%M WIB')

        # Up to v6 the voucher prints both electronic signatures with their codes. From v7 it carries empty boxes for wet
        # signatures, so this page lists the three approvals in the app, in the order of the boxes, without codes.
        wet = voucher['template_version'] in WET_SIGNATURE_TEMPLATES
        signers = [{'role':('Diperiksa Oleh' if wet else 'Diajukan Oleh') if step['kind']=='REVIEWER_SIGNED'
                            else 'Disetujui Oleh',
                    'name':step['signer_name'],'title':step['signer_title'],
                    'code':None if wet else step['verification_code'],'signed_at':jakarta(step['signed_at'])}
                   for step in steps]
        submitter = voucher['payload'].get('submitter') if wet else None
        if submitter:
            signers.insert(0,{'role':'Diajukan Oleh','name':submitter['name'],
                              'title':submitter.get('title') or 'Admin Intake AMIGA','code':None,
                              'signed_at':jakarta(datetime.fromisoformat(submitter['submitted_at']))})
        return {'number':voucher['number'],'status':status,'wet_signatures':wet,'signers':signers,
                'content_sha256':content,'content_matches':bool(steps) and all(step['content_sha256']==content for step in steps),
                'draft_pdf_sha256':voucher['pdf_sha256'],'final_pdf_sha256':signoff['pdf_sha256'] if signoff else None}

    def recover(self, conn):
        interrupted = conn.execute("UPDATE vouchers SET render_status='FAILED',error_code='VOUCHER_RENDER_INTERRUPTED' "
                                   "WHERE render_status='RENDERING' RETURNING *").fetchall()
        for voucher in interrupted:
            self.db.audit(conn,voucher['request_id'],voucher['payload']['reviewer']['id'],'VOUCHER_FAILED',
                          'Render sebelumnya terputus; dapat diulang dari snapshot yang sama.',
                          {'voucher_number':voucher['number']},voucher['invoice_version'])
        interrupted = conn.execute("UPDATE voucher_signoffs s SET render_status='FAILED',error_code='VOUCHER_RENDER_INTERRUPTED' "
                                   "FROM vouchers v WHERE v.id=s.voucher_id AND s.render_status='RENDERING' "
                                   'RETURNING s.director_step_id,v.request_id,v.invoice_version,v.number').fetchall()
        for signoff in interrupted:
            actor = conn.execute('SELECT actor_id FROM approval_steps WHERE id=%s',(signoff['director_step_id'],)).fetchone()
            self.db.audit(conn,signoff['request_id'],actor['actor_id'],'SIGNED_VOUCHER_FAILED',
                          'Render salinan final terputus; dapat diulang dari persetujuan yang sama.',
                          {'voucher_number':signoff['number']},signoff['invoice_version'])
