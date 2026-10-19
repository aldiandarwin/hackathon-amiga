"""Create three synthetic invoice pages with frozen expected values; no network."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amiga_ocr.fixtures import scenario
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'prototype' / 'dataset'
PDF = ROOT / 'output' / 'pdf' / 'invoice-smoke-pack.pdf'


def money(value):
    return f'{Decimal(value):,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def build():
    if PDF.exists() or (DATA / 'cases.jsonl').exists():
        raise SystemExit('Frozen dataset already exists; create a new version instead of overwriting.')
    PDF.parent.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    writer = canvas.Canvas(str(PDF), pagesize=A4, invariant=1)
    writer.setTitle('AMIGA - Synthetic invoice smoke fixtures v1')
    cases = []
    for page, name in enumerate(('normal', 'missing_bank', 'wrong_total'), 1):
        sample = scenario(name)
        invoice = sample.invoice_payload['invoice']
        writer.setFillColor(colors.HexColor('#17334A'))
        writer.rect(0, 735, 595, 107, fill=1, stroke=0)
        writer.setFillColor(colors.white)
        writer.setFont('Helvetica-Bold', 26)
        writer.drawString(42, 790, 'INVOICE')
        writer.setFont('Helvetica', 11)
        writer.drawString(42, 765, invoice['vendor_name'])
        writer.setFillColor(colors.HexColor('#A34400'))
        writer.setFont('Helvetica-Bold', 10)
        writer.drawString(42, 706, 'DATA SINTETIS - BUKAN TAGIHAN ATAU REKENING NYATA')
        writer.setFillColor(colors.HexColor('#17334A'))
        writer.setFont('Helvetica', 11)
        for y, text in ((676, 'Nomor invoice: ' + invoice['invoice_number']),
                        (655, 'Tanggal invoice: ' + invoice['invoice_date']),
                        (634, 'Mata uang: ' + invoice['currency'])):
            writer.drawString(42, y, text)
        writer.setFillColor(colors.HexColor('#EDF2F6'))
        writer.rect(42, 571, 511, 31, fill=1, stroke=0)
        writer.setFillColor(colors.HexColor('#17334A'))
        writer.setFont('Helvetica-Bold', 10)
        writer.drawString(50, 583, 'Deskripsi')
        writer.drawRightString(335, 583, 'Qty')
        writer.drawRightString(440, 583, 'Harga satuan')
        writer.drawRightString(544, 583, 'Jumlah')
        writer.setFont('Helvetica', 10)
        for index, item in enumerate(invoice['line_items']):
            y = 549 - index * 38
            writer.drawString(50, y, item['description'])
            writer.drawRightString(335, y, item['quantity'])
            writer.drawRightString(440, y, money(item['unit_price']))
            writer.drawRightString(544, y, money(item['stated_line_total']))
            writer.setStrokeColor(colors.HexColor('#D8E0E7'))
            writer.line(42, y-12, 553, y-12)
        for y, label, key in ((423, 'Subtotal', 'stated_subtotal'), (398, 'Diskon', 'stated_discount_total'),
                              (373, 'Pajak', 'stated_tax_total'), (336, 'TOTAL IDR', 'stated_total')):
            writer.setFont('Helvetica-Bold' if key == 'stated_total' else 'Helvetica', 12)
            writer.drawString(310, y, label)
            writer.drawRightString(544, y, money(invoice[key]))
        writer.setFont('Helvetica-Bold', 12)
        writer.drawString(42, 274, 'Informasi pembayaran')
        writer.setFont('Helvetica', 11)
        writer.drawString(42, 247, 'Bank: ' + invoice['payment']['bank_name'])
        writer.drawString(42, 224, 'Atas nama: ' + invoice['payment']['account_holder'])
        account = invoice['payment']['account_number']
        if account is not None:
            writer.drawString(42, 201, 'Nomor rekening: ' + account)
        writer.setFont('Helvetica', 9)
        writer.setFillColor(colors.HexColor('#667685'))
        writer.drawString(42, 63, f'AMIGA test fixture v1 | {name} | halaman invoice 1/1')
        writer.showPage()
        cases.append({'case_id': f'amiga.pdf.{name}.v1',
                      'input': {'pdf': 'output/pdf/invoice-smoke-pack.pdf', 'pack_page': page,
                                'document_id': 'doc_' + name, 'invoice_page_count': 1},
                      'expected_behavior': {'invoice': invoice, 'status': sample.expected_status,
                                            'required_check_codes': list(sample.required_codes)},
                      'failure_category': {'normal': 'field_extraction', 'missing_bank': 'invented_bank_account',
                                           'wrong_total': 'silent_total_correction'}[name],
                      'severity': 'critical' if name == 'missing_bank' else 'high',
                      'split': 'regression', 'source': {'type': 'synthetic_boundary_case',
                          'artifact': 'amiga_ocr/fixtures.py', 'approval': 'ENGINEERING_FIXTURE_NOT_FINANCE_APPROVED'},
                      'metadata': {'scenario': name, 'used_for_tuning': False, 'dataset_version': 'smoke.v1'}})
    writer.save()
    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    for case in cases:
        case['input']['pdf_sha256'] = digest
    (DATA / 'cases.jsonl').write_text(''.join(json.dumps(case, ensure_ascii=False) + '\n' for case in cases), encoding='utf-8')
    print(json.dumps({'pdf': str(PDF), 'synthetic_cases': len(cases), 'pdf_sha256': digest}))


if __name__ == '__main__':
    build()
