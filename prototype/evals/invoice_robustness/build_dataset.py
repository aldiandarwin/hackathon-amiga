"""Author immutable synthetic PDF/JSON fixtures. No network or application writes."""

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import textwrap

import pymupdf
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'prototype'))
from amiga_ocr.contracts import Context, validate_extraction
from amiga_ocr.validation import field_values, identity

DATA = ROOT / 'prototype/dataset/robustness-v1'
PDF_DIR = ROOT / 'output/pdf/robustness-v1'
PACK = ROOT / 'output/pdf/invoice-robustness-review-v1.pdf'
VERSION = 'invoice-robustness.v1'
INK = HexColor('#183C45')
TEAL = HexColor('#147C75')
LIGHT = HexColor('#EAF3F2')
W, H = A4


def canonical(cases):
    return '\n'.join(json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(',', ':')) for c in cases).encode()


def money(value):
    return f'{Decimal(value):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def specs():
    # Split membership and expectations are declared independently of the validator.
    return [
        ('r01', 'digital-normal', 'regression', 'field_extraction', 'digital', 1, 3, 'READY_FOR_REVIEW', []),
        ('r02', 'leading-zero-identifiers', 'regression', 'identifier_truncation', 'digital', 1, 3, 'READY_FOR_REVIEW', []),
        ('r03', 'decimal-tax-discount', 'regression', 'numeric_normalization', 'digital', 1, 3, 'READY_FOR_REVIEW', []),
        ('t01', 'five-page-line-items', 'targeted', 'page_or_row_omission', 'digital', 5, 20, 'READY_FOR_REVIEW', []),
        ('t02', 'scan-clean', 'targeted', 'raster_extraction', 'scan', 1, 3, 'READY_FOR_REVIEW', []),
        ('t03', 'scan-skew', 'targeted', 'raster_skew', 'skew', 1, 3, 'READY_FOR_REVIEW', []),
        ('t04', 'scan-low-resolution', 'targeted', 'raster_low_resolution', 'lowres', 1, 3, 'READY_FOR_REVIEW', []),
        ('t05', 'missing-bank-account', 'targeted', 'invented_bank_account', 'digital', 1, 3, 'EXCEPTION', ['MISSING_EVIDENCE:FAILED', 'BANK_UNVERIFIED:NOT_CHECKED']),
        ('t06', 'incorrect-stated-total', 'targeted', 'silent_total_correction', 'digital', 1, 3, 'EXCEPTION', ['TOTAL_MISMATCH:FAILED']),
        ('t07', 'duplicate-in-trusted-history', 'targeted', 'duplicate_detection', 'digital', 1, 3, 'EXCEPTION', ['POSSIBLE_DUPLICATE:FAILED']),
        ('h01', 'alternate-layout-two-pages', 'holdout', 'layout_generalization', 'alternate', 2, 8, 'READY_FOR_REVIEW', []),
        ('h02', 'partly-unreadable-account', 'holdout', 'illegible_value_abstention', 'masked', 1, 3, 'EXCEPTION', ['MISSING_EVIDENCE:FAILED', 'BANK_UNVERIFIED:NOT_CHECKED']),
        ('h03', 'unknown-vendor', 'holdout', 'unresolved_master_data', 'alternate', 1, 3, 'EXCEPTION', ['DUPLICATE_CHECK:NOT_CHECKED', 'BANK_UNVERIFIED:NOT_CHECKED']),
    ]


def invoice_for(short, count, serial):
    vendor = 'CV Lembar Simulasi' if short == 'h03' else ('PT Arsip Simulasi' if short.startswith('h') else 'PT Contoh Uji Nusantara')
    items = []
    for index in range(count):
        qty = Decimal(index % 3 + 1)
        price = Decimal(17500 + serial * 1100 + index * 725)
        if short == 'r03':
            qty, price = Decimal(['1.5', '2.25', '3'][index]), Decimal(['12345.60', '2500.40', '9100.25'][index])
        description = f'Perlengkapan administrasi contoh {index + 1:02d}'
        if short == 'h01':
            description = f'Layanan pengarsipan dokumen sintetis periode uji, paket {index + 1:02d}'
        items.append({'line_number': index + 1, 'description': description,
                      'quantity': format(qty, 'f'), 'unit_price': format(price, '.2f'),
                      'stated_line_total': format(qty * price, '.2f')})
    subtotal = sum(Decimal(item['stated_line_total']) for item in items)
    discount = Decimal('500.25') if short == 'r03' else Decimal('0.00')
    tax = Decimal('1250.50') if short == 'r03' else Decimal('0.00')
    total = subtotal - discount + tax + (Decimal('10000') if short == 't06' else Decimal(0))
    account = '000001230045' if short == 'r02' else f'003900{serial:04d}01'
    if short in ('t05', 'h02'):
        account = None
    return {'vendor_id': None, 'vendor_name': vendor,
        'invoice_number': '000042-INV-SIM' if short == 'r02' else f'SIM-2026-{serial:04d}',
        'invoice_date': '2026-10-13', 'due_date': '2026-10-27', 'currency': 'IDR',
        'line_items': items, 'stated_subtotal': format(subtotal, '.2f'),
        'stated_discount_total': format(discount, '.2f'), 'stated_tax_total': format(tax, '.2f'),
        'stated_total': format(total, '.2f'), 'payment': {'bank_name': 'Bank Simulasi',
        'account_holder': vendor, 'account_number': account}}


def author_pdf(case, spec, invoice):
    short, _, _, _, style, page_count, _, _, _ = spec
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    pdf.setTitle('Invoice sintetis ' + short.upper())
    pdf.setAuthor('AMIGA Tim 9 - synthetic test data')
    evidence = {path: None for path, _ in field_values(invoice)}
    transcripts = [[] for _ in range(page_count)]
    count_per_page = (len(invoice['line_items']) + page_count - 1) // page_count
    lowcontrast = style == 'lowres'

    def write(page, x, y, value, path=None, *, size=10, bold=False, right=False, color=None):
        text = str(value)
        pdf.setFillColor(color or (HexColor('#737B7D') if lowcontrast else INK))
        pdf.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
        (pdf.drawRightString if right else pdf.drawString)(x, y, text)
        transcripts[page - 1].append(text)
        if path and evidence[path] is None:
            evidence[path] = {'document_id': case, 'page': page, 'raw_value': text, 'bbox': None}

    for page in range(1, page_count + 1):
        alternate = style == 'alternate'
        pdf.setFillColor(LIGHT)
        pdf.rect(0, H - 118, W, 118, stroke=0, fill=1)
        write(page, 40, H - 50, 'INVOICE' if not alternate else 'TAGIHAN', size=28, bold=True, color=TEAL)
        write(page, W - 40, H - 42, 'AMIGA / TIM 9', size=10, right=True)
        write(page, 40, H - 76, invoice['vendor_name'], 'vendor_name', size=12, bold=True)
        write(page, 40, H - 98, 'DATA SINTETIS - BUKAN TAGIHAN ATAU REKENING NYATA', size=8)
        write(page, 40, 698, 'Kepada: PT Penerima Simulasi', size=9)
        write(page, 40, 677, 'Nomor dokumen' if alternate else 'Nomor invoice', size=8)
        write(page, 40, 660, invoice['invoice_number'], 'invoice_number', size=12, bold=True)
        write(page, 290, 677, 'Tanggal terbit', size=8)
        write(page, 290, 660, invoice['invoice_date'], 'invoice_date')
        write(page, 425, 677, 'Jatuh tempo', size=8)
        write(page, 425, 660, invoice['due_date'], 'due_date')
        write(page, 40, 633, 'Mata uang:', size=9)
        write(page, 104, 633, invoice['currency'], 'currency', size=9, bold=True)
        pdf.setFillColor(TEAL)
        pdf.rect(40, 581, W - 80, 28, stroke=0, fill=1)
        for x, label, right in ((49, 'URAIAN', False), (331, 'QTY', True), (433, 'HARGA SATUAN', True), (W - 49, 'JUMLAH', True)):
            write(page, x, 591, label, size=8, bold=True, right=right, color=white)
        start = (page - 1) * count_per_page
        for offset, item in enumerate(invoice['line_items'][start:start + count_per_page]):
            index = start + offset
            y = 557 - offset * 53
            parts = textwrap.wrap(item['description'], width=39)
            # Preserve one atomic description across wrapped visual lines in annotation.
            for line, part in enumerate(parts):
                write(page, 49, y - line * 13, part, size=9)
            evidence[f'line_items[{index}].description'] = {'document_id': case, 'page': page,
                'raw_value': item['description'], 'bbox': None}
            for key, x in (('quantity', 331), ('unit_price', 433), ('stated_line_total', W - 49)):
                raw = item[key] if key == 'quantity' else money(item[key])
                write(page, x, y, raw, f'line_items[{index}].{key}', size=9, right=True)
            pdf.setStrokeColor(HexColor('#D8E4E4'))
            pdf.line(40, y - 34, W - 40, y - 34)
        if page == page_count:
            for y, label, key in ((300, 'Subtotal', 'stated_subtotal'), (277, 'Diskon tercetak', 'stated_discount_total'),
                                  (254, 'Pajak tercetak', 'stated_tax_total'), (214, 'TOTAL IDR', 'stated_total')):
                write(page, 300, y, label, size=10, bold=key == 'stated_total')
                write(page, W - 49, y, money(invoice[key]), key, size=11, bold=key == 'stated_total', right=True)
            write(page, 40, 176, 'INFORMASI PEMBAYARAN SINTETIS', size=9, bold=True)
            write(page, 40, 156, invoice['payment']['bank_name'], 'payment.bank_name', size=10)
            write(page, 40, 138, invoice['payment']['account_holder'], 'payment.account_holder', size=10)
            if invoice['payment']['account_number']:
                write(page, 40, 118, 'Nomor rekening:', size=9)
                write(page, 135, 118, invoice['payment']['account_number'], 'payment.account_number', size=11, bold=True)
            elif short == 'h02':
                write(page, 40, 118, 'Nomor rekening: 0039', size=10)
                pdf.setFillColor(HexColor('#626B6C'))
                pdf.rect(174, 113, 78, 15, fill=1, stroke=0)
                write(page, 260, 118, '5501', size=10)
        else:
            write(page, 40, 304, 'Rincian dilanjutkan di halaman berikutnya.', size=10)
            write(page, 40, 281, 'Ringkasan total dan informasi pembayaran ada di halaman terakhir.', size=9)
        write(page, 40, 57, 'Simulasi pengujian dokumen | ' + short.upper(), size=8)
        write(page, W - 40, 57, f'Halaman {page} / {page_count}', size=8, right=True)
        pdf.showPage()
    pdf.save()
    raw = buffer.getvalue()
    if style in ('scan', 'skew', 'lowres', 'masked'):
        doc = pymupdf.open(stream=raw, filetype='pdf')
        scanned = BytesIO()
        pdf = canvas.Canvas(scanned, pagesize=A4, invariant=1)
        pdf.setTitle('Invoice sintetis ' + short.upper())
        for page in doc:
            dpi = 80 if style == 'lowres' else 145
            png = page.get_pixmap(dpi=dpi, alpha=False).tobytes('png')
            pdf.saveState()
            if style == 'skew':
                pdf.translate(W / 2, H / 2)
                pdf.rotate(2.5)
                pdf.scale(0.93, 0.93)
                pdf.translate(-W / 2, -H / 2)
            pdf.drawImage(ImageReader(BytesIO(png)), 0, 0, width=W, height=H)
            pdf.restoreState()
            pdf.showPage()
        pdf.save()
        raw = scanned.getvalue()
        doc.close()
    return raw, evidence, ['\n'.join(lines) for lines in transcripts]


def build():
    if DATA.exists() or PDF_DIR.exists() or PACK.exists():
        raise SystemExit('Frozen output already exists. Author a new dataset version instead of overwriting.')
    DATA.mkdir(parents=True)
    PDF_DIR.mkdir(parents=True)
    cases, pack_writer, catalog = [], PdfWriter(), []
    cover_buffer = BytesIO()
    cover = canvas.Canvas(cover_buffer, pagesize=A4, invariant=1)
    cover.setFillColor(INK)
    cover.setFont('Helvetica-Bold', 26)
    cover.drawString(42, 777, 'AMIGA / INVOICE TEST PACK')
    cover.setFont('Helvetica', 12)
    cover.drawString(42, 749, '13 dokumen sintetis - robustness v1')
    cover.setFont('Helvetica', 10)
    for y, line in enumerate(('Paket ini untuk review manusia. Jangan unggah seluruh paket sebagai satu invoice.',
                              'Gunakan PDF terpisah pada folder robustness-v1 untuk pengujian aplikasi.',
                              'Angka, nama, rekening dan riwayat sepenuhnya sintetis.',
                              'Jawaban rekayasa belum disahkan Finance. Holdout belum dievaluasi.')):
        cover.drawString(42, 713 - y * 17, line)
    pack_page = 2
    for serial, spec in enumerate(specs(), 1):
        short, label, split, category, style, pages, item_count, status, blockers = spec
        case_id = f'amiga.robust.{short}.v1'
        invoice = invoice_for(short, item_count, serial)
        pdf, evidence, transcript = author_pdf(case_id, spec, invoice)
        path = PDF_DIR / f'{short}.pdf'
        path.write_bytes(pdf)
        raster = style in ('scan', 'skew', 'lowres', 'masked')
        vendor = 'vendor_synthetic_' + short
        context = Context(client_id='eval_client', request_id=case_id, uploaded_by='eval_pic',
            vendor_directory={} if short == 'h03' else {identity(invoice['vendor_name']): vendor},
            bank_accounts={vendor: (invoice['payment']['account_number'] or '009900000099',)},
            bank_master_loaded=True, history_loaded=True,
            previous_invoices=({'client_id': 'eval_client', 'vendor_id': vendor,
                'invoice_number': invoice['invoice_number'], 'request_id': 'eval_previous_approved', 'active': True},) if short == 't07' else ())
        payload = {'invoice': invoice, 'source_evidence': evidence}
        validate_extraction(payload)
        case = {'case_id': case_id, 'input': {'pdf': path.relative_to(ROOT).as_posix(),
                'pdf_sha256': sha256(pdf).hexdigest(), 'document_id': case_id,
                'invoice_page_count': pages, 'source_kind': 'RASTER_ONLY' if raster else 'DIGITAL_TEXT',
                'context': asdict(context)},
            'expected_behavior': {'invoice': invoice, 'source_evidence': evidence,
                'annotated_pages': transcript, 'status': status, 'blocking_checks': blockers,
                'required_checks': ['OCR_COMPLETE:PASSED'], 'line_item_count': item_count},
            'failure_category': category, 'severity': 'critical' if short in ('r02', 't05', 't06', 't07', 'h02') else 'high',
            'split': split, 'used_for_tuning': False,
            'source': {'type': 'synthetic_boundary_case', 'artifact': 'prototype/evals/invoice_robustness/build_dataset.py',
                'approval': 'ENGINEERING_FIXTURE_NOT_FINANCE_APPROVED', 'basis': 'Explicit product criteria and existing demo contract; not an observed OCR incident'},
            'forbidden_behavior': ['invent absent values', 'repair stated total silently', 'discard line items', 'drop identifier leading zeros', 'approve payment'],
            'metadata': {'dataset_version': VERSION, 'name': label, 'style': style,
                'family': 'targeted-scan' if short in ('t02', 't03', 't04') else short,
                'review_pack_pages': [pack_page, pack_page + pages - 1],
                'gold_status': 'ENGINEERING_DRAFT', 'human_visual_review': 'SEE_VERIFICATION_REPORT'}}
        cases.append(case)
        cover.setFont('Helvetica-Bold', 10)
        cover.drawString(42, 610 - serial * 30, short.upper())
        cover.setFont('Helvetica', 10)
        cover.drawString(85, 610 - serial * 30, label)
        cover.drawRightString(W - 42, 610 - serial * 30, f'{split} | hlm {pack_page}-{pack_page + pages - 1}')
        catalog.append(f'| {short.upper()} | {label} | {split} | {pages} | {item_count} | {status} |')
        pack_page += pages
    cover.showPage()
    cover.save()
    pack_writer.append(PdfReader(BytesIO(cover_buffer.getvalue())))
    for case in cases:
        pack_writer.append(PdfReader(ROOT / case['input']['pdf']))
    with PACK.open('wb') as stream:
        pack_writer.write(stream)
    (DATA / 'cases.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases), encoding='utf-8')
    # Input-only export has no answers, bank master or historical records for model consumption.
    inputs = [{'case_id': c['case_id'], 'pdf': c['input']['pdf'], 'pdf_sha256': c['input']['pdf_sha256'],
               'invoice_page_count': c['input']['invoice_page_count'], 'split': c['split']} for c in cases]
    (DATA / 'inputs-only.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in inputs), encoding='utf-8')
    (DATA / 'CATALOG.md').write_text('# Synthetic invoice robustness v1\n\n13 kasus rekayasa; bukan invoice klien. Jawaban belum disahkan Finance.\n\n'
        '| ID | Kasus | Split | Halaman | Items | Status validasi ideal |\n|---|---|---|---|---|---|\n' + '\n'.join(catalog)
        + '\n\nStatus ideal memakai transkrip authoring lengkap. Status scan pada aplikasi tetap memerlukan review visual; lihat README.\n', encoding='utf-8')
    manifest = {'dataset_version': VERSION, 'dataset_sha256': sha256(canonical(cases)).hexdigest(),
                'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
                'cases_jsonl_sha256': sha256((DATA / 'cases.jsonl').read_bytes()).hexdigest(),
                'pack_sha256': sha256(PACK.read_bytes()).hexdigest(), 'case_count': len(cases), 'invoice_pages': pack_page - 2}
    (DATA / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    build()
