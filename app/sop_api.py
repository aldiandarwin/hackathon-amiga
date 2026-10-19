"""SOP guidance for the review screen: one card per check code from the local corpus, plus free questions through
the Bedrock RAG in knowledge-base/tools/rag.py.

Only the user's question and the check code reach Bedrock; invoice data never does. When Bedrock fails, the answer
falls back to the nearest cards by local word score, so a reviewer always gets the SOP and never a dead end.
"""

import logging
import re
import sys
import time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from .service import AppError
from .settings import ROOT

TOOLS = ROOT / 'knowledge-base' / 'tools'
# student_9 lost S3 read access on 14 Okt 2026, so the app reads the cards from the repo; Bedrock still embeds and answers.
CARD_CACHE_SECONDS = 300
CODE = r'^[A-Z][A-Z0-9_]{2,60}$'
SOP_ID = r'^[A-Z]+-[A-Z0-9_-]{2,60}$'
FALLBACK_NOTICE = 'Robot Admin sedang tidak bisa dihubungi. Ini panduan terdekat yang bisa Anda baca.'
# rag.py words its warnings for engineers. The reviewer gets one plain sentence per kind, matched on rag.py's prefixes.
PLAIN_WARNINGS = (
    ('stopReason', 'Jawaban mungkin terpotong. Buka kartu sumbernya untuk langkah lengkap.'),
    ('jawaban tanpa sitasi', 'Jawaban ini tidak menyebut kartu SOP. Cocokkan dulu dengan kartu sebelum Anda bertindak.'),
    ('sitasi', 'Sebagian rujukan tidak cocok dengan kartu SOP. Cocokkan jawaban dengan kartu sumbernya.'),
)
OTHER_WARNING = 'Cocokkan jawaban ini dengan kartu sumbernya sebelum Anda bertindak.'
# Cards keep machine codes, because retrieval and the AI read them. The reviewer reads a card in screen words instead
# (Aldian, 16 Okt 2026): a check code becomes its card title, a status its label on screen, any other code a short
# phrase. The corpus itself is untouched; test_sop.py fails when a card shows a code these tables miss.
STATUS_WORDS = {  # as app/static/app.js shows them, plus the two statuses the queue never shows
    'QUEUED': 'Menunggu proses', 'PROCESSING': 'Sedang diproses', 'READY_FOR_REVIEW': 'Siap diperiksa',
    'EXCEPTION': 'Perlu perhatian', 'AMIGA_REVIEWED': 'Menunggu manajer keuangan',
    'AMIGA_APPROVED': 'Disetujui manajer keuangan', 'RETURNED': 'Dikembalikan manajer keuangan', 'INTAKE': 'Belum diajukan',
    'RETURNED_TO_PIC': 'Dikembalikan Finance ke PIC', 'SENT_TO_CLIENT': 'Terkirim ke klien',
}
CODE_WORDS = {
    'NOT_CHECKED': 'belum bisa diperiksa', 'PASSED': 'lolos', 'FAILED': 'gagal', 'WARNING': 'peringatan',
    'DECLARED_ZERO': 'dinyatakan nol', 'OCR_COMPLETE': 'halaman lengkap', 'SOURCE_EVIDENCE_MATCH': 'bukti sumber cocok',
    'LINE_TOTAL_MATCH': 'total baris cocok', 'SUBTOTAL_MATCH': 'subtotal cocok', 'TOTAL_MATCH': 'total cocok',
    'NPWP_MATCH': 'NPWP cocok', 'BANK_VERIFIED': 'rekening cocok',
    'AMIGA_DIRECTOR': 'Manajer Keuangan', 'FINANCE_REVIEWER': 'Finance', 'SYSTEM_ADMIN': 'admin sistem',
    'NOT_FOUND': 'data tidak ditemukan', 'VERSION_CONFLICT': 'versi bentrok', 'NO_CHANGES': 'tidak ada perubahan',
    'AMIGA_APPROVED_LOCKED': 'sudah disetujui manajer keuangan', 'INTAKE_LOCKED': 'sudah diajukan',
    'NOT_SUBMITTED': 'belum diajukan PIC', 'SELF_APPROVAL_FORBIDDEN': 'tidak boleh menyetujui sendiri',
    'INVALID_PAYLOAD': 'data tidak valid', 'REASON_REQUIRED': 'alasan wajib diisi', 'INVALID_TRANSITION': 'langkah tidak berlaku',
    'UNRESOLVED_EXCEPTION': 'isian wajib belum lengkap', 'SOURCE_REVIEW_REQUIRED': 'pemeriksaan sumber belum dikonfirmasi',
    'TAX_ADJUSTMENT_INVALID': 'tambahan PPN tidak berlaku',
    'TAX_ADJUSTMENT_CONFIRMATION_REQUIRED': 'konfirmasi tambahan PPN belum dicentang',
    'CONSENT_REQUIRED': 'pernyataan belum dicentang', 'SIGNATURE_PASSWORD_INVALID': 'password tidak cocok',
    'SIGNATURE_RATE_LIMIT': 'terlalu banyak percobaan persetujuan', 'REVIEWER_SIGNATURE_MISSING': 'persetujuan Finance belum ada',
    'CONTENT_MISMATCH': 'isi voucher tidak cocok', 'VOUCHER_TEMPLATE_UNSUPPORTED': 'template voucher lama',
    'VOUCHER_NOT_SIGNED': 'voucher belum disetujui', 'VOUCHER_SUPERSEDED': 'voucher tidak aktif lagi',
    'VOUCHER_NOT_READY': 'voucher belum siap', 'VOUCHER_UNAVAILABLE': 'file voucher tidak tersedia',
    'VOUCHER_CHANGED': 'file voucher berubah', 'HANDOVER_BUSY': 'pengiriman masih berjalan',
    'HANDOVER_NOT_CONFIGURED': 'pengiriman Telegram belum aktif', 'HANDOVER_FAILED': 'pengiriman gagal',
    'HANDOVER_UNCERTAIN': 'pengiriman belum pasti', 'CLIENT_EXISTS': 'klien sudah ada', 'VENDOR_EXISTS': 'vendor sudah ada',
    'CHAT_BUSY': 'Robot Admin sedang sibuk', 'LOGIN_FAILED': 'login gagal', 'LOGIN_RATE_LIMIT': 'terlalu banyak percobaan login',
    'CSRF_REJECTED': 'sesi tidak valid', 'ORIGIN_REJECTED': 'sumber permintaan ditolak',
    'INVALID_DOCUMENT_PATH': 'lokasi dokumen tidak sah', 'PREVIEW_FAILED': 'pratinjau gagal',
    'BATCH_LIMIT': 'batas jumlah file', 'MANIFEST_MISMATCH': 'file berbeda dari pilihan awal',
    'IDEMPOTENCY_CONFLICT': 'kunci batch bentrok', 'IDEMPOTENCY_REQUIRED': 'kunci unggahan tidak valid',
    'FILE_TOO_LARGE': 'file terlalu besar', 'PAGE_LIMIT': 'halaman terlalu banyak', 'ENCRYPTED_PDF': 'PDF berkata sandi',
    'INVALID_DOCUMENT': 'dokumen tidak bisa diproses', 'INVALID_FILENAME': 'nama file tidak sah',
    'FORBIDDEN': 'akses ditolak', 'UNAUTHENTICATED': 'belum masuk', 'REJECTED': '"Ditolak"',
}
TEXT_WORDS = {'demo-rules.v1': 'versi demo', 'brief-v2.0': 'brief hackathon', 'poc-teknis': 'keputusan teknis PoC',
              ' (n8n)': ''}
SCREEN_CODE = re.compile(r'\b(?:[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|QUEUED|PROCESSING|EXCEPTION|INTAKE|RETURNED|PASSED|FAILED|WARNING'
                         r'|FORBIDDEN|UNAUTHENTICATED|REJECTED)\b')
log = logging.getLogger(__name__)


class SopQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pertanyaan: str = Field(min_length=3, max_length=500)
    kode: str | None = Field(default=None, pattern=CODE)


def rag_module():
    """Imported lazily so the app still starts when boto3 or AWS credentials are missing."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import rag
    rag.SUMBER_KARTU = 'lokal'
    rag.CACHE_KARTU_DETIK = CARD_CACHE_SECONDS
    return rag


def plain_title(heading, kode=None):
    """A card heading in plain words. An exception card's H1 'CODE: description', or 'CODE ...: description', keeps
    only the description; other headings stay whole. First letter uppercase, no trailing period."""
    title = heading.strip()
    if kode and title.startswith(kode):
        title = title.partition(':')[2].strip() or kode.replace('_', ' ').lower()
    title = title.rstrip('.').strip()
    return title[:1].upper() + title[1:]


def card_label(card):
    return plain_title(card['judul'], card['kode'])


def reference(sop_id, judul):
    # Exception cards are named EXC-<code>; bangun_korpus.py rejects any exception card that is not.
    return {'sop_id': sop_id, 'judul': judul,
            'label': plain_title(judul, sop_id[4:] if sop_id.startswith('EXC-') else None)}


def screen_text(teks, labels):
    """A card body in screen words; labels maps each check code to its card title. Where the card already says what
    the screen shows, the code is dropped instead of translated, so nothing is said twice."""
    def word(code):
        if code in labels:
            return f'"{labels[code]}"'
        return f'"{STATUS_WORDS[code]}"' if code in STATUS_WORDS else CODE_WORDS.get(code, code)

    def kept(code, after=''):  # a check or a status is a subject worth naming, anything else is noise next to its message
        return word(code) + after if code in labels or code in STATUS_WORDS else ''

    code = SCREEN_CODE.pattern
    # "lolos sebagai LINE_TOTAL_MATCH, SUBTOTAL_MATCH, dan TOTAL_MATCH": passing says it all.
    teks = re.sub(rf'lolos sebagai {code}(?:(?:,? dan |, ){code})*', 'lolos', teks)
    # "Server menolak dengan INTAKE_LOCKED": the refusal is the point, its code is not.
    teks = re.sub(rf'\b(menolak|ditolak) dengan ({code})', lambda m: m[1] + (' dengan ' + kept(m[2]) if kept(m[2]) else ''), teks)
    # 'masuk EXCEPTION dan tampil "Perlu perhatian"': the screen label already follows.
    teks = re.sub(rf'{code}(?:,| dan)? (?:tampil|di layar) (?=")', '', teks)
    # 'Muncul HANDOVER_FAILED? Artinya "Pengiriman gagal."': ask with the message the screen shows.
    teks = re.sub(rf'Muncul {code}\? Artinya "([^"]+?)\.?"', r'Muncul pesan "\1"?', teks)
    # '- VERSION_CONFLICT, "Versi sudah berubah."' and '- NOT_FOUND: akun tidak ditugaskan': the message stands alone.
    teks = re.sub(rf'({code}), (misalnya )?(?=")', lambda m: kept(m[1], ', ') + (m[2] or ''), teks)
    teks = re.sub(rf'^(\s*-\s+)({code})([:.]) ', lambda m: m[1] + kept(m[2], m[3] + ' '), teks, flags=re.M)
    teks = SCREEN_CODE.sub(lambda m: word(m[0]), teks)
    for text, words in TEXT_WORDS.items():
        teks = teks.replace(text, words)
    # A bullet that now opens with a small letter gets its capital back.
    return re.sub(r'^(\s*-\s+)([a-z])', lambda m: m[1] + m[2].upper(), teks, flags=re.M)


def card_view(card, labels):
    return {**{key: card[key] for key in ('sop_id', 'kode', 'kategori', 'judul', 'teks')}, 'label': card_label(card),
            'teks_layar': screen_text(card['teks'], labels)}


def plain_warnings(warnings):
    plain = []
    for text in warnings:
        message = next((m for prefix, m in PLAIN_WARNINGS if text.startswith(prefix)), OTHER_WARNING)
        if message not in plain:
            plain.append(message)
    return plain


def nearest_cards(rag, question, limit=3):
    cards, _ = rag.muat_kartu()
    chunks = [chunk for card in cards for chunk in rag.potong(card)]
    scores = rag.skor_kata(chunks, question)
    ranked = sorted(range(len(chunks)), key=lambda i: -scores[i])
    by_id = {card['sop_id']: card for card in cards}
    return [{'sop_id': sop_id, 'judul': by_id[sop_id]['judul'], 'label': card_label(by_id[sop_id])}
            for sop_id in list(dict.fromkeys(chunks[i]['sop_id'] for i in ranked))[:limit]]


def sop_router(actor):
    router = APIRouter(prefix='/api/v1/sop')

    @router.get('/kartu')
    def card(kode: str | None = Query(default=None, pattern=CODE),
             sop_id: str | None = Query(default=None, pattern=SOP_ID), user=Depends(actor)):
        if bool(kode) == bool(sop_id):
            raise AppError('INVALID_PAYLOAD', 'Isi salah satu: kode atau sop_id.')
        cards, _ = rag_module().muat_kartu()
        found = next((c for c in cards if (c['kode'] == kode if kode else c['sop_id'] == sop_id)), None)
        if not found:
            raise AppError('NOT_FOUND', 'Kartu SOP untuk kode ini belum ada.', 404)
        return card_view(found, {c['kode']: card_label(c) for c in cards if c['kode']})

    @router.get('/label')
    def labels(user=Depends(actor)):
        """Plain title per check code, for buttons and check lists. Local cards only, from the same card cache."""
        cards, _ = rag_module().muat_kartu()
        return {'labels': {c['kode']: card_label(c) for c in sorted(cards, key=lambda c: c['kode'] or '') if c['kode']}}

    @router.post('/tanya')
    def ask(body: SopQuestion, user=Depends(actor)):
        rag = rag_module()
        question = body.pertanyaan.strip()
        if body.kode:
            question = f'Kode {body.kode}. {question}'
        started = time.monotonic()
        try:
            result = rag.jawab(question)
        except Exception as error:  # credentials, network or Bedrock: the reviewer still gets the nearest SOP cards
            log.warning('SOP RAG fallback after %s', type(error).__name__)
            return {'mode': 'cadangan', 'jawaban': None, 'referensi': nearest_cards(rag, question),
                    'peringatan': [FALLBACK_NOTICE],
                    'latensi_ms': round((time.monotonic() - started) * 1000), 'model': None}
        return {'mode': 'rag', 'jawaban': result['jawaban'],
                'referensi': [reference(r['sop_id'], r['judul']) for r in result['referensi']],
                'peringatan': plain_warnings(result['peringatan']),
                'latensi_ms': round((time.monotonic() - started) * 1000), 'model': result['model']}

    return router
