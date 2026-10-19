"""Intake, durable processing and versioned review of invoice drafts."""

from copy import deepcopy
from contextlib import nullcontext
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import threading
from uuid import uuid4

from pypdf import PdfReader, PdfWriter
from psycopg.types.json import Jsonb

from . import taxes
from .settings import ROOT, MAX_PAGES, MAX_PDF_BYTES
from .database import Database
from .signing import INTAKE_CONSENT, canonical_json
from amiga_ocr.contracts import Context, ContractError, OCRDocument, OCRPage, Rules, validate_extraction
from amiga_ocr.live_budget import BudgetLedger, BudgetError
from amiga_ocr.openai_live import MEDIA_TYPES, Config, OpenAIClient, LiveError, normalize_response
from amiga_ocr.validation import check, field_values, identity, validate_invoice

# The extension must agree with the bytes: a PNG renamed to .pdf is refused, not guessed.
EXTENSIONS = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
STORED_EXTENSION = {'application/pdf': '.pdf', 'image/jpeg': '.jpg', 'image/png': '.png'}
BEDROCK_RESERVATION_MICRO_USD = 50_000


class AppError(ValueError):
    def __init__(self, code, message, status=422, field=None):
        super().__init__(message)
        self.code, self.status, self.field = code, status, field


def media_type_of(data):
    return next((media for media, magic in MEDIA_TYPES.items() if data.startswith(magic)), None)


def inspect_document(data):
    """Media type and text per page. A photo is one page without a text layer, like a scanned PDF."""
    if len(data) > MAX_PDF_BYTES:
        raise AppError('FILE_TOO_LARGE', 'Ukuran file maksimal 5 MB.', 413)
    media_type = media_type_of(data)
    if media_type == 'application/pdf':
        return media_type, inspect_pdf(data)
    if media_type is None:
        raise AppError('INVALID_DOCUMENT', 'Pilih invoice berupa PDF, JPG, atau PNG.')
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
    except Exception:
        raise AppError('INVALID_DOCUMENT', 'Gambar tidak dapat dibaca. Foto ulang atau simpan ulang filenya.') from None
    if not 200 <= min(width, height) <= max(width, height) <= 10_000:
        raise AppError('INVALID_DOCUMENT', 'Sisi gambar harus 200 sampai 10.000 piksel.')
    return media_type, ['']


def value_at(invoice, path):
    """Value of an edit path such as line_items[0].quantity or payment.account_number."""
    node = invoice
    for part in path.replace(']', '').replace('[', '.').split('.'):
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


# The PIC submits once the six fields the rules require are filled. NPWP and faktur stay optional: small vendors often
# print neither, and the PIC answers for that choice in the submission note.
REQUIRED_LABELS = {'vendor_name': 'Nama vendor', 'invoice_number': 'Nomor invoice', 'invoice_date': 'Tanggal invoice',
                   'currency': 'Mata uang', 'stated_total': 'Total tagihan sebelum PPh',
                   'payment.account_number': 'Nomor rekening'}


# Fields a ContractError names before its colon; numbers and line items fail without a name.
NAMED_CONTRACT_FIELDS = frozenset({'vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'currency', 'vendor_npwp',
                                   'buyer_name', 'buyer_npwp', 'po_number', 'faktur_number', 'faktur_date',
                                   'payment.bank_name', 'payment.account_holder', 'payment.account_number'})


def missing_required(invoice):
    """Required fields still empty, in the order of Rules().required_fields."""
    values = dict(field_values(invoice))
    return [path for path in Rules().required_fields
            if values.get(path) is None or (isinstance(values.get(path), str) and not values.get(path).strip())]


def stage(status, submitted_at):
    """Where a request waits. The status stays the result of the checks; the PIC's submission is a column of its own."""
    if status == 'AMIGA_APPROVED':
        return 'FINAL'
    if status == 'AMIGA_REVIEWED':
        return 'DIRECTOR'
    return 'FINANCE' if submitted_at else 'INTAKE'


def inspect_pdf(data):
    if len(data) > MAX_PDF_BYTES:
        raise AppError('FILE_TOO_LARGE', 'Ukuran PDF maksimal 5 MB.', 413)
    if not data.startswith(b'%PDF-'):
        raise AppError('INVALID_DOCUMENT', 'Pilih dokumen PDF yang valid.')
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise AppError('ENCRYPTED_PDF', 'Gunakan PDF tanpa kata sandi.')
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise AppError('PAGE_LIMIT', 'Satu invoice maksimal 5 halaman.')
        return [(page.extract_text() or '')[:100_000] for page in reader.pages]
    except AppError:
        raise
    except Exception:
        raise AppError('INVALID_DOCUMENT', 'PDF tidak dapat dibaca. Periksa atau ekspor ulang dokumennya.') from None


def sample_input(name):
    cases_path = ROOT / 'prototype/dataset/cases.jsonl'
    cases = [json.loads(line) for line in cases_path.read_text(encoding='utf-8').splitlines()]
    case = next((c for c in cases if c['metadata']['scenario'] == name), None)
    if not case:
        raise AppError('NOT_FOUND', 'Contoh tidak ditemukan.', 404)
    pack = ROOT / case['input']['pdf']
    if hashlib.sha256(pack.read_bytes()).hexdigest() != case['input']['pdf_sha256']:
        raise AppError('SAMPLE_CHANGED', 'Dokumen contoh berubah; ekstraksi tersimpan tidak dapat dipakai.')
    writer, buffer = PdfWriter(), BytesIO()
    writer.add_page(PdfReader(pack).pages[case['input']['pack_page'] - 1])
    writer.write(buffer)
    result = json.loads((ROOT / 'app/sample-results.json').read_text(encoding='utf-8'))[name]
    if result['dataset_sha256'] != hashlib.sha256(cases_path.read_bytes()).hexdigest():
        raise AppError('SAMPLE_CHANGED', 'Dataset contoh tidak cocok dengan hasil tersimpan.')
    return buffer.getvalue(), result


class InvoiceService:
    def __init__(self, database, settings, live_client_factory=None, fallback_client_factory=None):
        self.db, self.settings = database, settings
        self.documents = settings.data_dir / 'documents'
        self.documents.mkdir(parents=True, exist_ok=True)
        if live_client_factory:
            # Tests inject their own readers; the real fallback is never added behind their back.
            factories = [live_client_factory] + ([fallback_client_factory] if fallback_client_factory else [])
        else:
            readers = {'bedrock': self._bedrock_client, 'openai': self._live_client}
            names = dict.fromkeys([settings.extraction_provider, settings.extraction_fallback])
            factories = [readers[name] for name in names if name in readers]
        # live_client_factory stays the primary reader; tests replace it after construction.
        self.live_client_factory, self.fallback_factories = factories[0], factories[1:]
        self.preview_lock = threading.Lock()

    def _live_client(self):
        config = Config.load()
        # This is deliberately the original shared experiment ledger, never a new one.
        ledger = BudgetLedger(ROOT / 'prototype/.local/spend.sqlite3', config.stop_usd)
        return OpenAIClient(config, ledger)

    def _bedrock_client(self):
        from amiga_ocr.bedrock_live import BedrockClient, BedrockConfig
        config = BedrockConfig.load()
        # Separate ledger: AWS spend of the class account, not Aldian's OpenAI budget.
        ledger = BudgetLedger(ROOT / 'prototype/.local/spend-bedrock.sqlite3', config.stop_usd,
                              BEDROCK_RESERVATION_MICRO_USD)
        return BedrockClient(config, ledger)

    def original_bytes(self, conn, row):
        """Uploaded bytes from the database, checked against the hash recorded at upload."""
        stored = conn.execute('SELECT content FROM request_files WHERE request_id=%s', (row['id'],)).fetchone()
        data = bytes(stored['content']) if stored else self.document_path(row['document_key']).read_bytes()
        if hashlib.sha256(data).hexdigest() != row['pdf_sha256']:
            raise AppError('DOCUMENT_CHANGED', 'Dokumen sumber berubah.')
        return data

    def backfill_files(self):
        """Copy originals uploaded before stage 6 from disk into request_files, only when the hash still matches."""
        copied, skipped = 0, 0
        with self.db.transaction() as conn:
            rows = conn.execute('SELECT r.* FROM requests r LEFT JOIN request_files f ON f.request_id=r.id '
                                'WHERE f.request_id IS NULL').fetchall()
            for row in rows:
                path = self.document_path(row['document_key'])
                data = path.read_bytes() if path.is_file() else b''
                if not data or hashlib.sha256(data).hexdigest() != row['pdf_sha256']:
                    skipped += 1
                    continue
                conn.execute('INSERT INTO request_files(request_id,sha256,media_type,filename,byte_size,content) '
                             'VALUES (%s,%s,%s,%s,%s,%s)', (row['id'], row['pdf_sha256'], row['media_type'],
                                                            row['filename'], len(data), data))
                copied += 1
        return copied, skipped

    def document_path(self, key):
        path = (self.documents / key).resolve()
        if not path.is_relative_to(self.documents.resolve()):
            raise AppError('INVALID_DOCUMENT_PATH', 'Dokumen tidak tersedia.', 404)
        return path

    def preview(self, row, page_number):
        if not 1 <= page_number <= row['page_count']:
            raise AppError('NOT_FOUND', 'Halaman tidak tersedia.', 404)
        # Local rasterization avoids dependence on a browser's built-in PDF plug-in.
        # Rendered pages remain private and use the same assignment check as the PDF.
        import pymupdf
        previews = self.settings.data_dir / 'previews' / str(row['id'])
        target = previews / f'{page_number}.png'
        with self.preview_lock:
            if not target.exists():
                try:
                    previews.mkdir(parents=True, exist_ok=True)
                    source = self.document_path(row['document_key'])
                    if not source.is_file():
                        # The database holds the original; the disk copy is only a cache.
                        with self.db.transaction() as conn:
                            source.write_bytes(self.original_bytes(conn, row))
                    if row['media_type'] != 'application/pdf':
                        from PIL import Image, ImageOps
                        with Image.open(source) as image:
                            # Phone photos often store rotation in EXIF; show them upright like the reader sees them.
                            image = ImageOps.exif_transpose(image).convert('RGB')
                            image.thumbnail((1800, 2600))
                            image.save(target, 'PNG')
                        return target
                    with pymupdf.open(source) as document:
                        page = document[page_number - 1]
                        scale = min(1.5, 1800 / page.rect.width, 2600 / page.rect.height)
                        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(target)
                except Exception:
                    raise AppError('PREVIEW_FAILED', 'Pratinjau tidak tersedia; buka PDF asli.') from None
        return target

    def intake(self, data, user, client_id, filename, idempotency_key, sample=None, *, connection=None, tax_selection=None):
        tax_selection = taxes.normalize_selection(tax_selection)
        if client_id not in {c['id'] for c in user['clients']}:
            raise AppError('NOT_FOUND', 'Klien tidak tersedia.', 404)
        # 15 Okt 2026, Aldian: the PIC uploads; Finance checks, corrects, approves or returns, but does not upload.
        if user['role'] != 'PIC':
            raise AppError('FORBIDDEN', 'Unggah invoice hanya untuk PIC Intake.', 403)
        media_type, pages = inspect_document(data)
        filename = filename.replace('\\', '/').split('/')[-1].strip()
        if EXTENSIONS.get(Path(filename).suffix.lower()) != media_type or len(filename) > 180:
            raise AppError('INVALID_FILENAME', 'Nama file harus berakhiran .pdf, .jpg, .jpeg, atau .png sesuai isinya, '
                                               'maksimal 180 karakter.')
        digest = hashlib.sha256(data).hexdigest()
        mode = 'REPLAY' if sample else 'OPENAI'
        # Batch receipt uses the caller's transaction so the request/job/item commit together.
        with (self.db.transaction() if connection is None else nullcontext(connection)) as conn:
            # Serialize intake within this client; duplicate clicks cannot enqueue twice.
            conn.execute('SELECT id FROM clients WHERE id=%s FOR UPDATE', (client_id,))
            prior = conn.execute('SELECT * FROM requests WHERE client_id=%s AND uploaded_by=%s '
                                 'AND idempotency_key=%s', (client_id, user['id'], idempotency_key)).fetchone()
            if prior:
                if (prior['pdf_sha256'], prior['mode'], prior['sample_name'], prior['tax_selection']) != (digest, mode, sample, tax_selection):
                    raise AppError('IDEMPOTENCY_CONFLICT', 'Kunci unggahan sudah dipakai untuk dokumen lain.', 409)
                return str(prior['id']), False
            prior = conn.execute('SELECT id FROM requests WHERE client_id=%s AND pdf_sha256=%s AND mode=%s '
                                 'ORDER BY created_at LIMIT 1', (client_id, digest, mode)).fetchone()
            if prior:
                return str(prior['id']), False
            request_id = str(uuid4())
            key = request_id + STORED_EXTENSION[media_type]
            conn.execute('INSERT INTO requests(id,client_id,uploaded_by,filename,document_key,pdf_sha256,page_count,'
                         'pages,mode,sample_name,status,idempotency_key,tax_selection,media_type) '
                         'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (request_id, client_id, user['id'], filename, key, digest, len(pages), Jsonb(pages),
                          mode, sample, 'QUEUED', idempotency_key, Jsonb(tax_selection) if tax_selection else None,
                          media_type))
            # The original bytes live in the database, append-only, in the same transaction as the request.
            conn.execute('INSERT INTO request_files(request_id,sha256,media_type,filename,byte_size,content) '
                         'VALUES (%s,%s,%s,%s,%s,%s)', (request_id, digest, media_type, filename, len(data), data))
            conn.execute('INSERT INTO jobs(request_id,status) VALUES (%s,%s)', (request_id, 'QUEUED'))
            self.db.audit(conn, request_id, user['id'], 'UPLOADED', 'Invoice diterima untuk ekstraksi.',
                          {'filename': filename, 'mode': mode, 'tax_selection': tax_selection}, 0)
            # Disk copy is only a preview cache. Writing it last means a failed write rolls the request back.
            with self.document_path(key).open('xb') as output:
                output.write(data)
            return request_id, True

    def detail(self, request_id, user):
        with self.db.transaction() as conn:
            row = self.db.scoped_request(conn, request_id, user)
            if not row:
                raise AppError('NOT_FOUND', 'Request tidak ditemukan.', 404)
            snapshot = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=%s',
                                    (request_id, row['current_version'])).fetchone()
            audit = conn.execute('SELECT a.id,a.action,a.reason,a.changes,a.version,a.created_at,u.name AS actor '
                                 'FROM audit_events a JOIN users u ON u.id=a.actor_id WHERE request_id=%s '
                                 'ORDER BY a.id DESC LIMIT 100', (request_id,)).fetchall()
            # Hash checked inside PostgreSQL, so the review screen can show it without moving the file around.
            original = conn.execute('SELECT media_type,byte_size,encode(sha256(content),%s)=sha256 AS verified '
                                    'FROM request_files WHERE request_id=%s', ('hex', request_id)).fetchone()
            changed = (snapshot['snapshot'].get('human_changed_fields') or []) if snapshot else []
            first = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=1',
                                 (request_id,)).fetchone() if changed else None
            # The PIC corrects and submits during intake; after the submission Finance keeps the edits.
            intake = (row['submitted_at'] is None and row['status'] in ('READY_FOR_REVIEW', 'EXCEPTION')
                      and row['current_version'] > 0)
            submitted = next((a for a in audit if a['action'] == 'INTAKE_SUBMITTED'), None) if row['submitted_at'] else None
            # Back in intake after Finance returned it: the newest of the two events tells which one still holds.
            handover = next((a for a in audit if a['action'] in ('INTAKE_SUBMITTED', 'FINANCE_RETURNED')), None)
            returned = handover if handover and handover['action'] == 'FINANCE_RETURNED' and not row['submitted_at'] else None
            return {k: row[k] for k in ('id','client_id','filename','status','current_version','approved_version','uploaded_by','page_count','mode',
                                        'created_at','updated_at','error_code','media_type','submitted_at','submitted_version')} | {
                'draft': snapshot['snapshot'] if snapshot else None, 'audit': audit,
                'can_edit': (user['role'] == 'FINANCE_REVIEWER' and row['current_version'] > 0
                             and row['status'] != 'AMIGA_APPROVED') or (user['role'] == 'PIC' and intake),
                'stage': stage(row['status'], row['submitted_at']),
                'can_submit': user['role'] == 'PIC' and intake,
                'missing_required': missing_required(snapshot['snapshot']['invoice']) if snapshot else [],
                'required_fields': list(Rules().required_fields),
                'submission': {'by': submitted['actor'], 'at': submitted['created_at'], 'version': submitted['version'],
                               'note': submitted['changes'].get('note')} if submitted else None,
                'returned_to_pic': {'by': returned['actor'], 'at': returned['created_at'], 'version': returned['version'],
                                    'reason': returned['reason']} if returned else None,
                'original_file': dict(original, stored_in_database=True) if original else
                                 {'stored_in_database': False, 'media_type': row['media_type']},
                'original_values': {path: value_at(first['snapshot']['invoice'], path) for path in changed} if first else {},
                'document_url': f'/api/v1/requests/{request_id}/document'} | self.review.metadata(
                    conn,row,snapshot['snapshot'] if snapshot else None,user)

    def context(self, conn, row):
        vendors = conn.execute('SELECT * FROM vendors WHERE client_id=%s', (row['client_id'],)).fetchall()
        directory = {identity(v['name']): v['id'] for v in vendors}
        history = conn.execute('SELECT r.id AS request_id,r.client_id,v.snapshot FROM requests r JOIN invoice_versions v '
                               'ON v.request_id=r.id AND v.version=r.current_version WHERE r.client_id=%s AND r.id<>%s',
                               (row['client_id'], row['id'])).fetchall()
        # An invoice read before its vendor was registered stored no vendor id, so it is matched by the vendor's name.
        previous = tuple({'client_id': h['client_id'], 'request_id': str(h['request_id']),
                          'vendor_id': h['snapshot'].get('resolved_vendor_id')
                                       or directory.get(identity(h['snapshot']['invoice']['vendor_name'] or '')),
                          'invoice_number': h['snapshot']['invoice']['invoice_number'], 'active': True}
                         for h in history if h['snapshot']['invoice']['invoice_number'])
        return Context(row['client_id'], str(row['id']), row['uploaded_by'], row['current_version'] + 1,
                       directory,
                       {v['id']: tuple(v['verified_accounts']) for v in vendors}, True, previous, True,
                       {v['id']: v['npwp'] for v in vendors if v.get('npwp')})

    def snapshot(self, conn, row, extraction, changes=(), source=None, tax_selection=None):
        source = source or {}
        document = OCRDocument(str(row['id']), source.get('provider') or ('openai' if row['mode'] == 'OPENAI' else 'saved_openai'),
                               source.get('model') or 'gpt-6-luna',
                               tuple(OCRPage(i+1, text, bool(text)) for i, text in enumerate(row['pages'])),
                               row['page_count'], all(row['pages']), {})
        candidate = deepcopy(extraction)
        validation = validate_invoice(candidate, document, self.context(conn, row), Rules(),
                                      declared_zero=taxes.declared_zero(candidate['invoice'], tax_selection))
        if not all(row['pages']):
            validation['checks'].append(check('VISUAL_REVIEW_REQUIRED', 'NOT_CHECKED',
                'Foto atau scan ini tidak punya lapisan teks. Cocokkan nilai dengan gambar dokumen.'))
        vendor_id = candidate['invoice']['vendor_id']
        if vendor_id and conn.execute('SELECT 1 FROM vendors WHERE client_id=%s AND id=%s AND registered_by IS NOT NULL',
                                      (row['client_id'], vendor_id)).fetchone():
            # Shown to Finance and the director, never holding approval: the PIC answered for it when submitting.
            validation['checks'].append(check('VENDOR_NEW', 'NOT_CHECKED', 'Vendor didaftarkan PIC saat pengajuan, bukan dari master yang sudah diverifikasi. Rekening dan NPWP berasal dari invoice.',
                field='payment.account_number', blocking=False))
        for path in changes:
            validation['checks'].append(check('HUMAN_CORRECTION_PENDING', 'NOT_CHECKED',
                'Nilai telah dikoreksi manusia; bukti asli tetap disimpan untuk review.', field=path))
        tax, tax_checks = taxes.compute(candidate['invoice'], tax_selection)
        validation['checks'].extend(tax_checks)
        status = 'EXCEPTION' if any(c['blocking'] and c['status'] != 'PASSED' for c in validation['checks']) else 'READY_FOR_REVIEW'
        return deepcopy(extraction) | {'validation': validation, 'resolved_vendor_id': candidate['invoice']['vendor_id'],
                                       'human_changed_fields': list(changes), 'source': source or {},
                                       'tax_selection': tax_selection, 'tax': tax}, status

    def edit(self, request_id, user, expected_version, invoice, reason, tax_selection=None):
        if user['role'] not in ('PIC', 'FINANCE_REVIEWER'):
            raise AppError('FORBIDDEN', 'Koreksi hanya tersedia untuk PIC Intake dan Finance Reviewer.', 403)
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn, request_id, user)
            if not row:
                raise AppError('NOT_FOUND', 'Request tidak ditemukan.', 404)
            if row['status'] == 'AMIGA_APPROVED':
                # Both signatures cover this content; a change needs a new invoice, not an edit.
                raise AppError('AMIGA_APPROVED_LOCKED', 'Voucher sudah disetujui manajer keuangan, jadi datanya tidak bisa dikoreksi lagi.', 409)
            if user['role'] == 'PIC' and row['submitted_at'] is not None:
                # The PIC answers for what was submitted; later corrections are Finance's, each with its own audit row.
                raise AppError('INTAKE_LOCKED', 'Invoice sudah diajukan ke Finance. Koreksi berikutnya oleh Finance.', 409)
            if row['current_version'] != expected_version or row['current_version'] < 1 or row['status'] == 'PROCESSING':
                raise AppError('VERSION_CONFLICT', 'Versi sudah berubah. Muat ulang sebelum menyimpan.', 409)
            old = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=%s',
                               (request_id, expected_version)).fetchone()['snapshot']
            # The form always shows Biaya lain; left empty on a draft read before schema v3, it is no change.
            if (isinstance(invoice, dict) and invoice.get('stated_other_charges_total') is None
                    and 'stated_other_charges_total' not in old['invoice']):
                invoice.pop('stated_other_charges_total', None)
            try:
                extraction = validate_extraction({'invoice': invoice, 'source_evidence': old['source_evidence']})
            except ContractError as error:
                # The contract names the field first ("invoice_date: ..."), so the form can mark that one field.
                field = str(error).split(':')[0]
                raise AppError('INVALID_PAYLOAD', 'Periksa format tanggal, angka, rekening dan baris invoice.',
                               field=field if field in NAMED_CONTRACT_FIELDS else None) from None
            try:
                selection = old.get('tax_selection') if tax_selection is None else taxes.normalize_selection(tax_selection)
            except ValueError:
                raise AppError('INVALID_PAYLOAD', 'Pilihan pajak tidak valid.') from None
            if invoice == old['invoice'] and selection == old.get('tax_selection'):
                raise AppError('NO_CHANGES', 'Tidak ada perubahan untuk disimpan.')
            before, after = dict(field_values(old['invoice'])), dict(field_values(invoice))
            changed = {key: {'before': before.get(key), 'after': after.get(key)}
                       for key in set(before) | set(after) if before.get(key) != after.get(key)}
            changed |= taxes.selection_changes(old.get('tax_selection'), selection)
            original = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=1',
                                    (request_id,)).fetchone()['snapshot']['invoice']
            baseline = dict(field_values(original))
            human_fields = sorted(key for key in set(baseline) | set(after) if baseline.get(key) != after.get(key))
            snapshot, status = self.snapshot(conn, row, extraction, human_fields, old.get('source'), tax_selection=selection)
            version = expected_version + 1
            conn.execute('INSERT INTO invoice_versions(request_id,version,snapshot,actor_id) VALUES (%s,%s,%s,%s)',
                         (request_id, version, Jsonb(snapshot), user['id']))
            conn.execute('UPDATE requests SET current_version=%s,status=%s,approved_version=NULL,updated_at=now() WHERE id=%s',
                         (version, status, request_id))
            if row['approved_version'] is not None:
                conn.execute('UPDATE vouchers SET superseded_at=now() WHERE request_id=%s AND superseded_at IS NULL', (request_id,))
                self.db.audit(conn,request_id,user['id'],'APPROVAL_INVALIDATED',reason,
                              {'previous_approved_version':row['approved_version']},version)
            self.db.audit(conn, request_id, user['id'], 'DRAFT_EDITED', reason, changed, version)
        return self.detail(request_id, user)

    def submit(self, request_id, user, expected_version, consent, note=None):
        """The PIC hands a checked draft to Finance. Only the six required fields must be filled; any other open check may
        stay, once the PIC ticks the statement and writes why. Finance and the director still review afterwards."""
        if user['role'] != 'PIC':
            raise AppError('FORBIDDEN', 'Pengajuan ke Finance hanya untuk PIC Intake.', 403)
        if consent is not True:
            raise AppError('CONSENT_REQUIRED', 'Centang pernyataan sebelum mengajukan ke Finance.', 422)
        note = (note or '').strip()
        with self.db.transaction() as conn:
            row = self.db.locked_request(conn, request_id, user)
            if not row:
                raise AppError('NOT_FOUND', 'Request tidak ditemukan.', 404)
            if row['submitted_at'] is not None:
                if row['submitted_by'] == user['id']:  # a double click gets the result of the first
                    return self.detail(request_id, user)
                raise AppError('INTAKE_LOCKED', 'Invoice sudah diajukan ke Finance. Koreksi berikutnya oleh Finance.', 409)
            if (row['current_version'] != expected_version or row['current_version'] < 1
                    or row['status'] not in ('READY_FOR_REVIEW', 'EXCEPTION')):
                raise AppError('VERSION_CONFLICT', 'Versi sudah berubah. Muat ulang sebelum mengajukan.', 409)
            stored = conn.execute('SELECT snapshot FROM invoice_versions WHERE request_id=%s AND version=%s',
                                  (request_id, expected_version)).fetchone()['snapshot']
            missing = missing_required(stored['invoice'])
            if missing:
                raise AppError('MISSING_EVIDENCE', 'Lengkapi isian wajib sebelum mengajukan: '
                               + ', '.join(REQUIRED_LABELS[path] for path in missing) + '.', 422)
            # Before the checks run again: a vendor registered here verifies its own account, and any later failure
            # below rolls the registration back with the rest of the submission.
            registered = self.register_vendor(conn, row, user, stored['invoice'])
            # Submitting runs the checks again, so a duplicate uploaded since extraction still reaches Finance.
            fresh, status = self.snapshot(conn, row, {'invoice': stored['invoice'], 'source_evidence': stored['source_evidence']},
                                          stored.get('human_changed_fields') or (), stored.get('source'),
                                          tax_selection=stored.get('tax_selection'))
            open_checks = {c['code'] for c in fresh['validation']['checks'] if c['blocking'] and c['status'] != 'PASSED'}
            if fresh['tax']['status'] != 'COMPUTED':
                open_checks.add('TAX_SELECTION_REQUIRED' if fresh['tax']['status'] == 'NOT_SELECTED' else 'TAX_NOT_COMPUTED')
            if (open_checks or registered) and len(note) < 5:
                raise AppError('REASON_REQUIRED', ('Vendor baru ikut didaftarkan. ' if registered else 'Masih ada kendala. ')
                               + 'Tulis catatan minimal 5 karakter: kenapa invoice ini tetap diajukan.', 422)
            version = expected_version
            # A new version only when the checks came out differently, so an unchanged draft keeps its number.
            if canonical_json([fresh['validation'], fresh['resolved_vendor_id']]) != canonical_json(
                    [stored['validation'], stored.get('resolved_vendor_id')]):
                version = expected_version + 1
                conn.execute('INSERT INTO invoice_versions(request_id,version,snapshot,actor_id) VALUES (%s,%s,%s,%s)',
                             (request_id, version, Jsonb(fresh), user['id']))
                conn.execute('UPDATE requests SET current_version=%s,status=%s WHERE id=%s', (version, status, request_id))
            conn.execute('UPDATE requests SET submitted_at=now(),submitted_by=%s,submitted_version=%s,updated_at=now() '
                         'WHERE id=%s', (user['id'], version, request_id))
            content = hashlib.sha256(canonical_json({'invoice': stored['invoice'],
                                                     'tax_selection': stored.get('tax_selection')})).hexdigest()
            self.db.audit(conn, request_id, user['id'], 'INTAKE_SUBMITTED', note or 'Diajukan ke Finance tanpa kendala terbuka.',
                          {'consent_text': INTAKE_CONSENT, 'open_checks': sorted(open_checks), 'note': note or None,
                           'content_sha256': content} | ({'revalidated_from': expected_version} if version != expected_version
                                                        else {}) | ({'registered_vendor': registered['id']} if registered
                                                                    else {}), version)
        return self.detail(request_id, user)

    def register_vendor(self, conn, row, user, invoice):
        """A vendor the client's master does not know yet is added by the submitting PIC, with the account and NPWP
        printed on the invoice. A known vendor is never changed here: a different account stays BANK_MISMATCH for
        Finance, the classic route of a swapped payee. The one exception is the vendor this same invoice registered on
        an earlier submission that Finance returned: the PIC may correct the account and NPWP it read."""
        vendors = conn.execute('SELECT id,name,verified_accounts,npwp,registered_request_id FROM vendors WHERE client_id=%s',
                               (row['client_id'],)).fetchall()
        name, account = invoice['vendor_name'], invoice['payment']['account_number']
        same = next((v for v in vendors if identity(v['name']) == identity(name)), None)
        if same and same['registered_request_id'] != row['id']:
            return None
        owner = next((v for v in vendors if account in v['verified_accounts'] and v is not same), None)
        if owner:
            raise AppError('VENDOR_EXISTS', f"Rekening {account} sudah terdaftar untuk vendor {owner['name']}. "
                           'Samakan nama vendor dengan master sebelum mengajukan.', 409)
        if same:
            vendor = {'id': same['id'], 'name': same['name'], 'account_number': account, 'npwp': invoice.get('vendor_npwp')}
            if same['verified_accounts'] == [account] and same['npwp'] == vendor['npwp']:
                return None  # unchanged: the PIC answered for it on the first submission
            conn.execute('UPDATE vendors SET verified_accounts=%s,npwp=%s WHERE client_id=%s AND id=%s',
                         (Jsonb([account]), vendor['npwp'], row['client_id'], same['id']))
            self.db.audit(conn, row['id'], user['id'], 'VENDOR_UPDATED',
                          f"Rekening atau NPWP vendor {same['name']} dibetulkan PIC saat pengajuan ulang.",
                          vendor | {'before': {'account_number': (same['verified_accounts'] or [None])[0],
                                               'npwp': same['npwp']}}, row['current_version'])
            return vendor
        vendor = {'id': 'v_' + hashlib.sha256(identity(name).encode()).hexdigest()[:12], 'name': name,
                  'account_number': account, 'npwp': invoice.get('vendor_npwp')}
        conn.execute('INSERT INTO vendors(client_id,id,name,verified_accounts,npwp,registered_by,registered_at,'
                     'registered_request_id) VALUES (%s,%s,%s,%s,%s,%s,now(),%s)',
                     (row['client_id'], vendor['id'], name, Jsonb([account]), vendor['npwp'], user['id'], row['id']))
        self.db.audit(conn, row['id'], user['id'], 'VENDOR_REGISTERED', f'Vendor baru {name} didaftarkan PIC saat pengajuan.',
                      vendor, row['current_version'])
        return vendor

    def read_live(self, row, data):
        """Primary reader first; the next one runs only when it fails. Every attempt lands in extraction_runs."""
        failed = []
        for factory in [self.live_client_factory] + self.fallback_factories:
            client, trace = None, None
            try:
                client = factory()
                client.preflight()
                if hasattr(client, 'extract_document'):
                    trace = client.extract_document(data, row['media_type'], 'web:' + str(row['id']))
                else:  # readers written before stage 6 only know PDFs
                    trace = client.extract_pdf(data, 'web:' + str(row['id']))
                traces = self.settings.data_dir / 'traces'
                traces.mkdir(exist_ok=True)
                (traces / (trace['run_id'] + '.json')).write_text(json.dumps(trace, default=str), encoding='utf-8')
                extraction = (client.normalize(trace, str(row['id'])) if hasattr(client, 'normalize')
                              else normalize_response(trace['response'], str(row['id'])))
            except Exception as error:
                provider = getattr(client, 'provider', 'openai')
                self.record_run(row, provider, getattr(client, 'model', None), trace, error,
                                failed[0][0] if failed else None)
                failed.append((provider, error))
                continue
            provider = getattr(client, 'provider', 'openai')
            fallback_from = failed[0][0] if failed else None
            self.record_run(row, provider, getattr(client, 'model', None), trace, None, fallback_from)
            source = {key: trace.get(key) for key in ('run_id','duration_ms','cost_upper_estimate_usd','usage','prompt_version')}
            source.update({'mode': 'LIVE_' + provider.upper(), 'live_calls': len(failed) + 1, 'provider': provider,
                           'model': trace.get('returned_model') or getattr(client, 'model', None),
                           'fallback_from': fallback_from})
            return extraction, source
        raise failed[-1][1]

    def record_run(self, row, provider, model, trace, error, fallback_from):
        usage = (trace or {}).get('usage') or {}
        raw = json.loads(json.dumps((trace or {}).get('response'), default=str)) if trace else None
        with self.db.transaction() as conn:
            conn.execute('INSERT INTO extraction_runs(request_id,provider,model,prompt_version,status,reason,duration_ms,'
                         'input_tokens,output_tokens,cost_upper_usd,fallback_from,raw_response) '
                         'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (row['id'], provider, model, (trace or {}).get('prompt_version'),
                          'FAILED' if error else 'COMPLETED', f'{type(error).__name__}: {str(error)[:200]}' if error else None,
                          (trace or {}).get('duration_ms'), usage.get('input_tokens'), usage.get('output_tokens'),
                          (trace or {}).get('cost_upper_estimate_usd'), fallback_from, Jsonb(raw) if raw is not None else None))

    def process_next(self):
        with self.db.transaction() as conn:
            job = conn.execute("SELECT j.request_id FROM jobs j WHERE j.status='QUEUED' "
                               'ORDER BY j.request_id FOR UPDATE SKIP LOCKED LIMIT 1').fetchone()
            if not job:
                return False
            row = conn.execute('SELECT * FROM requests WHERE id=%s', (job['request_id'],)).fetchone()
            conn.execute("UPDATE jobs SET status='PROCESSING',started_at=now() WHERE request_id=%s", (row['id'],))
            conn.execute("UPDATE requests SET status='PROCESSING',updated_at=now() WHERE id=%s", (row['id'],))
        try:
            with self.db.transaction() as conn:
                data = self.original_bytes(conn, row)
            if row['mode'] == 'REPLAY':
                _, saved = sample_input(row['sample_name'])
                extraction = {'invoice': saved['invoice'], 'source_evidence': saved['source_evidence']}
                for entry in extraction['source_evidence'].values():
                    if entry:
                        entry['document_id'] = str(row['id'])
                source = {'mode': 'SAVED_OPENAI_RESPONSE', 'live_calls': 0, 'original_run_id': saved['run_id']}
            else:
                extraction, source = self.read_live(row, data)
            extraction = validate_extraction(extraction)
            with self.db.transaction() as conn:
                conn.execute('SELECT id FROM clients WHERE id=%s FOR UPDATE',(row['client_id'],))
                snapshot, status = self.snapshot(conn, row, extraction, source=source, tax_selection=row['tax_selection'])
                conn.execute('INSERT INTO invoice_versions(request_id,version,snapshot,actor_id) VALUES (%s,1,%s,%s)',
                             (row['id'], Jsonb(snapshot), row['uploaded_by']))
                conn.execute('UPDATE requests SET status=%s,current_version=1,updated_at=now() WHERE id=%s', (status,row['id']))
                conn.execute("UPDATE jobs SET status='COMPLETED',finished_at=now() WHERE request_id=%s", (row['id'],))
                self.db.audit(conn, row['id'], row['uploaded_by'], 'EXTRACTED',
                              'Ekstraksi selesai; belum disetujui Finance.', {'source': source}, 1)
        except Exception as error:
            code = 'BUDGET_BLOCKED' if isinstance(error, BudgetError) else 'EXTRACTION_FAILED'
            if isinstance(error, AppError):
                code = error.code
            with self.db.transaction() as conn:
                conn.execute("UPDATE requests SET status='EXCEPTION',error_code=%s,updated_at=now() WHERE id=%s", (code,row['id']))
                conn.execute("UPDATE jobs SET status='FAILED',finished_at=now() WHERE request_id=%s", (row['id'],))
                self.db.audit(conn, row['id'], row['uploaded_by'], 'EXTRACTION_FAILED',
                              'Pemrosesan dihentikan. Tidak ada retry otomatis.', {'error_code': code}, 0)
        return True


class Worker:
    def __init__(self, service):
        self.service = service
        self.stop = threading.Event()
        self.thread = None
        self.healthy = False

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='amiga-worker')
        self.thread.start()

    def run(self):
        # One session lock per schema: tests and app cannot steal each other's jobs.
        lock_key = int.from_bytes(hashlib.sha256(self.service.settings.schema.encode()).digest()[:7], 'big')
        try:
            with self.service.db.open() as lock:
                if not lock.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (lock_key,)).fetchone()['acquired']:
                    return
                lock.commit()
                self.recover_interrupted()
                self.healthy = True
                outage = False
                while not self.stop.is_set():
                    try:
                        if outage:
                            # Work cut off mid-way by the outage is released before anything new starts.
                            self.recover_interrupted()
                            outage = False
                        extracted = self.service.process_next()
                        rendered = self.service.review.process_next()
                    except Exception as error:
                        # One dropped connection stopped the worker for good on 14 Oct; retry instead. Only the
                        # error class is logged, never its message, so no document content reaches the log.
                        self.healthy, outage = False, True
                        print(f'amiga-worker: {type(error).__name__}, mencoba lagi dalam 2 detik', file=sys.stderr)
                        self.stop.wait(2)
                        continue
                    self.healthy = True
                    if not extracted and not rendered:
                        self.stop.wait(0.5)
        except Exception:
            # No secret or document content goes into ordinary server logs.
            self.healthy = False
        finally:
            self.healthy = False

    def recover_interrupted(self):
        """Extractions and renders cut off mid-way: at start, and again after the database comes back. Only this
        worker processes jobs (advisory lock), so anything still in progress here was interrupted."""
        with self.service.db.transaction() as conn:
            interrupted = conn.execute("UPDATE requests SET status='EXCEPTION',error_code='PROCESS_INTERRUPTED' "
                                       "WHERE status='PROCESSING' RETURNING id,uploaded_by").fetchall()
            for row in interrupted:
                conn.execute("UPDATE jobs SET status='FAILED',finished_at=now() WHERE request_id=%s", (row['id'],))
                self.service.db.audit(conn,row['id'],row['uploaded_by'],'PROCESS_INTERRUPTED',
                                      'Proses sebelumnya terputus; tidak diulang otomatis.',{},0)
            self.service.review.recover(conn)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
