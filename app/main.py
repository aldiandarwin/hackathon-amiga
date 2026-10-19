"""Loopback-only FastAPI application for invoice intake and draft review."""

from contextlib import asynccontextmanager
import hmac
import mimetypes
import re
import time
from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictBool
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import taxes
from .database import Database
from .service import BEDROCK_RESERVATION_MICRO_USD, AppError, InvoiceService, Worker, sample_input, stage
from .review import ReviewService
from .presentation import queue_summary
from .verify_page import render_page
from .batches import BatchService
from .clients import ClientService
from .tax_api import TaxSelection, tax_router
from .sop_api import sop_router
from .chat_api import chat_router
from .handover_api import handover_router
from .settings import ROOT, Settings, MAX_PDF_BYTES, MAX_BATCH_FILES
from amiga_ocr.live_budget import BudgetLedger
from amiga_ocr.openai_live import MEDIA_TYPES

# The Next.js dashboard runs on port 3000 and proxies /api/v1 here; its writes still need the session's CSRF token.
DASHBOARD_ORIGINS = {'http://127.0.0.1:3000', 'http://localhost:3000'}
# Windows does not register .woff2, so the self-hosted Figtree font would go out as application/octet-stream.
mimetypes.add_type('font/woff2', '.woff2')


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    invoice: dict
    reason: str = Field(min_length=5, max_length=500)
    tax_selection: TaxSelection | None = None


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    reason: str = Field(min_length=5, max_length=500)


class Approval(ReviewAction):
    source_reviewed: StrictBool
    # Stage 8: a signature needs the password at that moment and an explicit consent; the service answers both.
    password: str | None = Field(default=None, max_length=200)
    consent: StrictBool = False
    tax_adjustment_confirmed: StrictBool = False


class DirectorApproval(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    password: str | None = Field(default=None, max_length=200)
    consent: StrictBool = False


class Submission(BaseModel):
    """The PIC's submission to Finance: a ticked statement, plus a note whenever checks are still open."""
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)
    consent: StrictBool = False
    note: str | None = Field(default=None, max_length=500)


class NewClient(BaseModel):
    """A client a PIC opens for the team; the voucher code is suggested from the name when left empty."""
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=3, max_length=120)
    city: str | None = Field(default=None, max_length=60)
    sector: str | None = Field(default=None, max_length=80)
    npwp: str | None = Field(default=None, max_length=30)
    code: str | None = Field(default=None, max_length=3)


def signer_context(request):
    """Who signed from where: identification for PP 71/2019 Pasal 59 ayat (3) huruf e."""
    return {'client_ip':request.client.host if request.client else None,
            'user_agent':(request.headers.get('user-agent') or '')[:300] or None}


class BatchItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1,max_length=255,pattern=r'^[^/\\\x00-\x1f]+$')
    byte_size: StrictInt = Field(ge=0,le=1_000_000_000_000)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    tax_selection: TaxSelection | None = None


class BatchManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_id: str = Field(min_length=1,max_length=100)
    items: list[BatchItem] = Field(min_length=1,max_length=MAX_BATCH_FILES)


def create_app(settings=None, *, start_worker=True, live_client_factory=None):
    settings = settings or Settings.load()
    db = Database(settings)
    service = InvoiceService(db, settings, live_client_factory)
    service.review = review = ReviewService(service)
    batches = BatchService(service)
    clients = ClientService(db)
    worker = Worker(service)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(db.initialize)
        copied, skipped = await run_in_threadpool(service.backfill_files)
        if copied or skipped:
            print(f'request_files: {copied} file lama disalin ke database, {skipped} dilewati karena hash tidak cocok')
        if start_worker:
            worker.start()
        yield
        worker.close()

    app = FastAPI(title='AMIGA Invoice Review', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.service, app.state.worker = db, service, worker
    app.state.review = review
    app.state.batches = batches
    allowed_hosts = ['127.0.0.1', 'localhost'] + (['testserver'] if settings.test_mode else [])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    login_attempts = {}

    @app.middleware('http')
    async def request_boundary(request, call_next):
        # The EC2 HTTPS endpoint forwards directly here with Host 127.0.0.1:8787.
        # Every proxied path, including source documents and public QR verification,
        # needs the server-only secret. Browser session and CSRF checks stay below.
        if settings.proxy_secret and not hmac.compare_digest(
                request.headers.get('x-amiga-proxy-secret', '').encode(), settings.proxy_secret.encode()):
            return JSONResponse({'code':'ORIGIN_REJECTED','message':'Sumber permintaan tidak diizinkan.'},
                                status_code=403, headers={'Cache-Control':'no-store'})
        if request.method in ('POST','PATCH','PUT','DELETE'):
            origin = request.headers.get('origin')
            trusted_public = bool(settings.proxy_secret and origin == settings.public_base_url)
            local_origin = origin in DASHBOARD_ORIGINS or (urlsplit(origin or '').netloc == request.headers.get('host')
                                                         and urlsplit(origin or '').scheme == 'http')
            if origin and not (trusted_public or (not settings.proxy_secret and local_origin)):
                return JSONResponse({'code':'ORIGIN_REJECTED','message':'Sumber permintaan tidak diizinkan.'}, status_code=403)
            length = request.headers.get('content-length')
            batch_item = bool(re.fullmatch(r'/api/v1/intake-batches/[^/]+/items/[0-9]+',request.url.path))
            limit = MAX_PDF_BYTES if request.url.path == '/api/v1/requests' else 150_000
            if batch_item:
                # The route records oversize rejection per item before reading its body.
                limit = 1_000_000_000_000
            if length and (not length.isdigit() or int(length) > limit):
                return JSONResponse({'code':'FILE_TOO_LARGE','message':'Ukuran permintaan melebihi batas.'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self' blob:; object-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(AppError)
    async def application_error(request, error):
        return JSONResponse({'code':error.code,'message':str(error)} | ({'field':error.field} if error.field else {}),
                            status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({'code':'INVALID_PAYLOAD','message':'Data permintaan tidak valid.'}, status_code=422)

    def actor(request: Request):
        token = request.cookies.get('amiga_session','')
        user = db.session(token) if token else None
        if not user:
            raise AppError('UNAUTHENTICATED','Silakan masuk terlebih dahulu.',401)
        if request.method not in ('GET','HEAD','OPTIONS') and not hmac.compare_digest(request.headers.get('x-csrf-token',''),user['csrf']):
            raise AppError('CSRF_REJECTED','Sesi tidak valid. Muat ulang halaman.',403)
        return user

    def idempotency(request):
        key = request.headers.get('idempotency-key','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',key):
            raise AppError('IDEMPOTENCY_REQUIRED','Kunci unggahan tidak valid.')
        return key

    app.include_router(tax_router(actor))
    app.include_router(sop_router(actor))
    app.include_router(chat_router(actor, db))
    app.include_router(handover_router(actor, db, review))

    @app.get('/api/v1/health')
    def health():
        return {'status':'ok','worker_ready':worker.healthy,'scope':'LOCAL_DEMO'}

    @app.post('/api/v1/login')
    def login(payload: Login, request: Request):
        host = request.client.host if request.client else 'local'
        attempts = [t for t in login_attempts.get(host,[]) if time.monotonic()-t < 60]
        if len(attempts) >= 10:
            raise AppError('LOGIN_RATE_LIMIT','Terlalu banyak percobaan. Coba lagi sebentar.',429)
        login_attempts[host] = attempts + [time.monotonic()]
        result = db.login(payload.email.strip().lower(), payload.password)
        if not result:
            raise AppError('LOGIN_FAILED','Email atau kata sandi tidak cocok.',401)
        login_attempts[host] = []
        token, csrf = result
        response = JSONResponse({'csrf':csrf})
        response.set_cookie('amiga_session',token,httponly=True,samesite='strict',max_age=8*3600,
                            secure=settings.secure_cookies,path='/')
        return response

    @app.get('/api/v1/session')
    def session(user=Depends(actor)):
        return user

    @app.post('/api/v1/logout')
    def logout(request: Request, user=Depends(actor)):
        db.logout(request.cookies.get('amiga_session',''))
        response = JSONResponse({'ok':True})
        response.delete_cookie('amiga_session',path='/',secure=settings.secure_cookies,httponly=True,samesite='strict')
        return response

    @app.get('/api/v1/budget')
    def budget(user=Depends(actor)):
        from amiga_ocr.openai_live import read_dotenv
        from decimal import Decimal
        try:
            values = read_dotenv(ROOT / '.env')
            result = BudgetLedger(ROOT/'prototype/.local/spend.sqlite3',Decimal(values['AMIGA_STOP_USD'])).snapshot()
        except Exception:
            values, result = {}, {'available':False,'message':'Informasi anggaran tidak tersedia; pemrosesan tetap memeriksa ledger.'}
        try:
            bedrock = BudgetLedger(ROOT/'prototype/.local/spend-bedrock.sqlite3',Decimal(values.get('AMIGA_BEDROCK_STOP_USD','2.00')),
                                   BEDROCK_RESERVATION_MICRO_USD).snapshot()
            result['bedrock'] = {key: bedrock[key] for key in ('operational_ceiling_usd','attempt_count','remaining_calls',
                                                               'usage_cost_upper_estimate_usd')}
        except Exception:
            result['bedrock'] = {'available': False}
        result['reader'], result['fallback'] = settings.extraction_provider, settings.extraction_fallback
        return result

    @app.get('/api/v1/requests')
    def listing(client_id: str | None = None, user=Depends(actor)):
        assigned = [c['id'] for c in user['clients']]
        if client_id is not None and client_id not in assigned:
            raise AppError('NOT_FOUND','Klien tidak tersedia.',404)
        # Without a client the queue covers every assigned client, so a team sees its whole portfolio at once.
        scope, limit = ([client_id], 100) if client_id is not None else (assigned, 200)
        # A director sees signing work only: waiting, approved, or returned to Finance.
        signing = (" AND r.status IN ('AMIGA_REVIEWED','AMIGA_APPROVED','RETURNED')"
                   if user['role'] == 'AMIGA_DIRECTOR' else '')
        with db.transaction() as conn:
            rows = conn.execute('SELECT r.id,r.client_id,c.name AS client_name,r.filename,r.status,r.current_version,'
                                'r.created_at,r.mode,r.error_code,'
                                "r.submitted_at,v.snapshot->'invoice' AS invoice,v.snapshot->'tax' AS tax,"
                                "v.snapshot->'validation' AS validation,r.uploaded_by,"
                                "(r.submitted_at IS NULL AND EXISTS(SELECT 1 FROM audit_events a WHERE a.request_id=r.id "
                                "AND a.action='FINANCE_RETURNED')) AS returned_to_pic "
                                'FROM requests r JOIN clients c ON c.id=r.client_id LEFT JOIN invoice_versions v '
                                'ON v.request_id=r.id AND v.version=r.current_version WHERE r.client_id=ANY(%s)' + signing +
                                ' ORDER BY r.created_at DESC LIMIT %s', (scope, limit)).fetchall()
        for row in rows:
            row.update(queue_summary({'tax': row.pop('tax'), 'validation': row.pop('validation')}, row['status']))
            row['stage'] = stage(row['status'], row['submitted_at'])
            row['needs_other_reviewer'] = (row.pop('uploaded_by') == user['id']
                and user['role'] == 'FINANCE_REVIEWER' and row['current_version'] > 0
                and row['status'] not in ('AMIGA_REVIEWED', 'AMIGA_APPROVED'))
        return {'items':rows,'limit':limit}

    @app.post('/api/v1/requests', status_code=202)
    async def upload(request: Request, client_id: str, filename: str, user=Depends(actor)):
        if request.headers.get('content-type','').split(';')[0] not in MEDIA_TYPES:
            raise AppError('INVALID_DOCUMENT','Unggah invoice berupa PDF, JPG, atau PNG.',415)
        key = idempotency(request)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_PDF_BYTES:
                raise AppError('FILE_TOO_LARGE','Ukuran file maksimal 5 MB.',413)
        identifier, created = await run_in_threadpool(service.intake,bytes(data),user,client_id,filename,key)
        return {'request_id':identifier,'created':created}

    @app.post('/api/v1/demo/{name}', status_code=202)
    def demo(name: str, request: Request, client_id: str, user=Depends(actor)):
        data, _ = sample_input(name)
        identifier, created = service.intake(data,user,client_id,f'contoh-{name}.pdf',idempotency(request),name,
                                             tax_selection=taxes.SAMPLE_SELECTION)
        return {'request_id':identifier,'created':created}

    @app.post('/api/v1/intake-batches',status_code=201)
    def create_batch(payload: BatchManifest, request: Request, user=Depends(actor)):
        return batches.create(user,payload.client_id,[item.model_dump(exclude_none=True) for item in payload.items],idempotency(request))

    @app.get('/api/v1/intake-batches')
    def list_batches(client_id: str, user=Depends(actor)):
        return batches.listing(client_id,user)

    @app.get('/api/v1/intake-batches/{batch_id}')
    def batch_detail(batch_id: UUID, user=Depends(actor)):
        return batches.detail(batch_id,user)

    @app.post('/api/v1/intake-batches/{batch_id}/items/{position}',status_code=202)
    async def batch_upload(batch_id: UUID, position: int, request: Request, user=Depends(actor)):
        await run_in_threadpool(batches.authorize_upload,batch_id,position,user)
        too_large=int(request.headers.get('content-length','0'))>MAX_PDF_BYTES
        data=bytearray()
        if not too_large:
            async for chunk in request.stream():
                if len(data)+len(chunk)>MAX_PDF_BYTES:
                    too_large=True
                    break
                data.extend(chunk)
        return await run_in_threadpool(batches.receive,batch_id,position,user,bytes(data),
                                      content_type=request.headers.get('content-type',''),too_large=too_large)

    @app.post('/api/v1/demo-batches/mixed',status_code=201)
    def demo_batch(request: Request, client_id: str, user=Depends(actor)):
        return batches.demo(user,client_id,idempotency(request))

    @app.get('/api/v1/requests/{request_id}')
    def detail(request_id: UUID, user=Depends(actor)):
        return service.detail(request_id,user)

    @app.get('/api/v1/requests/{request_id}/document')
    def document(request_id: UUID, user=Depends(actor)):
        with db.transaction() as conn:
            row = db.scoped_request(conn,request_id,user)
            if not row:
                raise AppError('NOT_FOUND','Dokumen tidak tersedia.',404)
            # Served from the database copy after the upload hash is checked again.
            data = service.original_bytes(conn,row)
        name = quote(row['filename'])
        return Response(data,media_type=row['media_type'],
                        headers={'Content-Disposition':f"inline; filename*=UTF-8''{name}",'X-Content-SHA256':row['pdf_sha256']})

    @app.patch('/api/v1/requests/{request_id}/draft')
    def edit(request_id: UUID, payload: Edit, user=Depends(actor)):
        if len(payload.reason.strip()) < 5:
            raise AppError('REASON_REQUIRED','Tuliskan alasan koreksi minimal 5 karakter.')
        return service.edit(request_id,user,payload.expected_version,payload.invoice,payload.reason.strip(),
                            payload.tax_selection.model_dump() if payload.tax_selection else None)

    @app.post('/api/v1/requests/{request_id}/submit')
    def submit(request_id: UUID, payload: Submission, user=Depends(actor)):
        return service.submit(request_id,user,payload.expected_version,payload.consent,payload.note)

    @app.post('/api/v1/requests/{request_id}/finance-return')
    def finance_return(request_id: UUID, payload: ReviewAction, user=Depends(actor)):
        if len(payload.reason.strip()) < 5:
            raise AppError('REASON_REQUIRED','Tuliskan alasan pengembalian minimal 5 karakter.')
        return review.finance_return(request_id,user,payload.expected_version,payload.reason.strip())

    @app.post('/api/v1/clients', status_code=201)
    def create_client(payload: NewClient, user=Depends(actor)):
        return clients.create(user,payload.name,payload.city,payload.sector,payload.npwp,payload.code)

    @app.get('/api/v1/requests/{request_id}/preview/{page_number}')
    def preview(request_id: UUID, page_number: int, user=Depends(actor)):
        with db.transaction() as conn:
            row = db.scoped_request(conn,request_id,user)
        if not row:
            raise AppError('NOT_FOUND','Dokumen tidak tersedia.',404)
        return FileResponse(service.preview(row,page_number),media_type='image/png')

    @app.post('/api/v1/requests/{request_id}/review')
    def approve(request_id: UUID, payload: Approval, request: Request, user=Depends(actor)):
        if len(payload.reason.strip()) < 5:
            raise AppError('REASON_REQUIRED','Tuliskan catatan review minimal 5 karakter.')
        return review.approve(request_id,user,payload.expected_version,payload.reason.strip(),payload.source_reviewed,
                              password=payload.password,consent=payload.consent,
                              tax_adjustment_confirmed=payload.tax_adjustment_confirmed,**signer_context(request))

    @app.post('/api/v1/requests/{request_id}/voucher/retry')
    def retry_voucher(request_id: UUID, payload: ReviewAction, user=Depends(actor)):
        if len(payload.reason.strip()) < 5:
            raise AppError('REASON_REQUIRED','Tuliskan alasan render ulang minimal 5 karakter.')
        return review.retry(request_id,user,payload.expected_version,payload.reason.strip())

    @app.get('/api/v1/requests/{request_id}/voucher')
    def voucher(request_id: UUID, version: int | None = None, inline: bool = False, user=Depends(actor)):
        data, filename = review.download(request_id,user,version)
        disposition = 'inline' if inline else 'attachment'
        return Response(data,media_type='application/pdf',headers={'Content-Disposition':f'{disposition}; filename="{filename}"'})

    # Public on purpose: the QR on a signed voucher opens this without an account. It shows no amount or account.
    @app.get('/api/v1/verifikasi/{voucher_id}')
    def verification(voucher_id: UUID):
        result = review.verification(voucher_id)
        if not result:
            raise AppError('NOT_FOUND','Voucher tidak ditemukan.',404)
        return result

    @app.get('/verifikasi/{voucher_id}')
    def verification_page(voucher_id: UUID):
        result = review.verification(voucher_id)
        return HTMLResponse(render_page(result),status_code=200 if result else 404)

    @app.post('/api/v1/requests/{request_id}/director-approval')
    def director_approval(request_id: UUID, payload: DirectorApproval, request: Request, user=Depends(actor)):
        return review.director_approve(request_id,user,payload.expected_version,password=payload.password,
                                       consent=payload.consent,**signer_context(request))

    @app.post('/api/v1/requests/{request_id}/director-return')
    def director_return(request_id: UUID, payload: ReviewAction, request: Request, user=Depends(actor)):
        if len(payload.reason.strip()) < 5:
            raise AppError('REASON_REQUIRED','Tuliskan alasan pengembalian minimal 5 karakter.')
        return review.director_return(request_id,user,payload.expected_version,payload.reason.strip(),
                                      **signer_context(request))

    @app.get('/api/v1/requests/{request_id}/voucher/signed')
    def signed_voucher(request_id: UUID, version: int | None = None, inline: bool = False, user=Depends(actor)):
        data, filename = review.download_signed(request_id,user,version)
        disposition = 'inline' if inline else 'attachment'
        return Response(data,media_type='application/pdf',headers={'Content-Disposition':f'{disposition}; filename="{filename}"'})

    app.mount('/static',StaticFiles(directory=ROOT/'app/static'),name='static')

    @app.get('/')
    def index(request: Request):
        return RedirectResponse(f'http://{request.url.hostname}:3000/review', status_code=307)

    @app.get('/review')
    def workspace():
        return FileResponse(ROOT/'app/static/index.html')

    return app
