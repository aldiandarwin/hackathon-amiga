"""Synthetic invoices for the final demo: same layout as the smoke pack, unique numbers, vendor in the demo master.

The smoke samples all carry INV-DEMO-001, so a fresh normal sample is held as POSSIBLE_DUPLICATE at approval.
These invoices use new numbers, PT Contoh Demo and its master account, so one live upload can go from AI
extraction through approval to voucher. PPN is printed exactly as the faktur rule computes it (12% x 11/12 of
DPP), so no TAX_PPN_DIFFERENT appears. No network.
"""

from io import BytesIO
from pathlib import Path
import hashlib
import json
import sys

import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_live_dataset import money  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output' / 'pdf' / 'demo-final'
ITEMS = (('Jasa desain materi promosi', '1', '2000000.00'),
         ('Jasa pengelolaan iklan digital', '1', '1500000.00'),
         ('Jasa penulisan konten', '2', '250000.00'))


def invoice(number):
    lines = [{'description': d, 'quantity': q, 'unit_price': p, 'stated_line_total': f'{int(q) * float(p):.2f}'}
             for d, q, p in ITEMS]
    return {'vendor_name': 'PT Contoh Demo', 'invoice_number': number, 'invoice_date': '2026-10-14',
            'currency': 'IDR', 'line_items': lines, 'stated_subtotal': '4000000.00', 'stated_discount_total': '0.00',
            'stated_tax_total': '440000.00', 'stated_total': '4440000.00',
            'payment': {'bank_name': 'Bank Contoh', 'account_holder': 'PT Contoh Demo', 'account_number': '00123456'}}


def draw(path, data):
    # Mirrors build_live_dataset.py so extraction sees the layout it was smoke-tested on.
    writer = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    writer.setTitle('AMIGA - Synthetic demo invoice ' + data['invoice_number'])
    writer.setFillColor(colors.HexColor('#17334A'))
    writer.rect(0, 735, 595, 107, fill=1, stroke=0)
    writer.setFillColor(colors.white)
    writer.setFont('Helvetica-Bold', 26)
    writer.drawString(42, 790, 'INVOICE')
    writer.setFont('Helvetica', 11)
    writer.drawString(42, 765, data['vendor_name'])
    writer.setFillColor(colors.HexColor('#A34400'))
    writer.setFont('Helvetica-Bold', 10)
    writer.drawString(42, 706, 'DATA SINTETIS - BUKAN TAGIHAN ATAU REKENING NYATA')
    writer.setFillColor(colors.HexColor('#17334A'))
    writer.setFont('Helvetica', 11)
    for y, text in ((676, 'Nomor invoice: ' + data['invoice_number']), (655, 'Tanggal invoice: ' + data['invoice_date']),
                    (634, 'Mata uang: ' + data['currency'])):
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
    for index, item in enumerate(data['line_items']):
        y = 549 - index * 38
        writer.drawString(50, y, item['description'])
        writer.drawRightString(335, y, item['quantity'])
        writer.drawRightString(440, y, money(item['unit_price']))
        writer.drawRightString(544, y, money(item['stated_line_total']))
        writer.setStrokeColor(colors.HexColor('#D8E0E7'))
        writer.line(42, y - 12, 553, y - 12)
    for y, label, key in ((423, 'Subtotal', 'stated_subtotal'), (398, 'Diskon', 'stated_discount_total'),
                          (373, 'PPN 11%', 'stated_tax_total'), (336, 'TOTAL IDR', 'stated_total')):
        writer.setFont('Helvetica-Bold' if key == 'stated_total' else 'Helvetica', 12)
        writer.drawString(310, y, label)
        writer.drawRightString(544, y, money(data[key]))
    writer.setFont('Helvetica-Bold', 12)
    writer.drawString(42, 274, 'Informasi pembayaran')
    writer.setFont('Helvetica', 11)
    writer.drawString(42, 247, 'Bank: ' + data['payment']['bank_name'])
    writer.drawString(42, 224, 'Atas nama: ' + data['payment']['account_holder'])
    writer.drawString(42, 201, 'Nomor rekening: ' + data['payment']['account_number'])
    writer.setFont('Helvetica', 9)
    writer.setFillColor(colors.HexColor('#667685'))
    writer.drawString(42, 63, f"AMIGA demo final | {data['invoice_number']} | halaman invoice 1/1")
    writer.showPage()
    writer.save()


# Stage 6 (14 Okt 2026): tax identity printed on the document so the reader fills it and nobody retypes it.
# NPWP and faktur numbers are deliberately fake (prefix 99) and every page says CONTOH.
VENDOR_NPWP = '99.123.456.7-012.000'
BUYER = ('PT Arunika Sejahtera', '99.765.432.1-098.000')


def invoice_v2(number, *, ppn):
    data = invoice(number)
    suffix = number.rsplit('-', 1)[1]
    data.update(vendor_npwp=VENDOR_NPWP, buyer_name=BUYER[0], buyer_npwp=BUYER[1], po_number='PO-ARS-2026-' + suffix,
                due_date='2026-10-28', faktur_number=None, faktur_date=None)
    if ppn:
        data.update(faktur_number=f'010.000-26.00000{suffix}', faktur_date='2026-10-14')  # 16 digits
    else:  # a vendor that charges no PPN: the photo samples pair with "PPh 23 2% saja"
        data.update(stated_tax_total=None, stated_total='4000000.00')
    return data


def draw_v2(data, *, faktur_page):
    buffer = BytesIO()
    writer = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    writer.setTitle('AMIGA - Synthetic demo invoice ' + data['invoice_number'])
    writer.setFillColor(colors.HexColor('#17334A'))
    writer.rect(0, 735, 595, 107, fill=1, stroke=0)
    writer.setFillColor(colors.white)
    writer.setFont('Helvetica-Bold', 26)
    writer.drawString(42, 790, 'INVOICE')
    writer.setFont('Helvetica', 11)
    writer.drawString(42, 765, data['vendor_name'])
    writer.drawString(300, 765, 'NPWP: ' + data['vendor_npwp'])
    writer.setFillColor(colors.HexColor('#A34400'))
    writer.setFont('Helvetica-Bold', 10)
    writer.drawString(42, 712, 'DATA SINTETIS - BUKAN TAGIHAN ATAU REKENING NYATA')
    writer.setFillColor(colors.HexColor('#17334A'))
    writer.setFont('Helvetica', 11)
    rows = (('Nomor invoice: ', data['invoice_number']), ('Tanggal invoice: ', data['invoice_date']),
            ('Jatuh tempo: ', data['due_date']), ('Nomor PO: ', data['po_number']), ('Mata uang: ', data['currency']))
    for index, (label, value) in enumerate(rows):
        writer.drawString(42, 688 - index * 19, label + value)
    writer.drawString(320, 688, 'Ditagihkan kepada:')
    writer.drawString(320, 669, data['buyer_name'])
    writer.drawString(320, 650, 'NPWP: ' + data['buyer_npwp'])
    writer.setFillColor(colors.HexColor('#EDF2F6'))
    writer.rect(42, 571, 511, 31, fill=1, stroke=0)
    writer.setFillColor(colors.HexColor('#17334A'))
    writer.setFont('Helvetica-Bold', 10)
    writer.drawString(50, 583, 'Deskripsi')
    writer.drawRightString(335, 583, 'Qty')
    writer.drawRightString(440, 583, 'Harga satuan')
    writer.drawRightString(544, 583, 'Jumlah')
    writer.setFont('Helvetica', 10)
    for index, item in enumerate(data['line_items']):
        y = 549 - index * 38
        writer.drawString(50, y, item['description'])
        writer.drawRightString(335, y, item['quantity'])
        writer.drawRightString(440, y, money(item['unit_price']))
        writer.drawRightString(544, y, money(item['stated_line_total']))
        writer.setStrokeColor(colors.HexColor('#D8E0E7'))
        writer.line(42, y - 12, 553, y - 12)
    totals = [(423, 'Subtotal', 'stated_subtotal'), (398, 'Diskon', 'stated_discount_total')]
    totals += [(373, 'PPN 11%', 'stated_tax_total')] if data['stated_tax_total'] else []
    for y, label, key in totals + [(336, 'TOTAL IDR', 'stated_total')]:
        writer.setFont('Helvetica-Bold' if key == 'stated_total' else 'Helvetica', 12)
        writer.drawString(310, y, label)
        writer.drawRightString(544, y, money(data[key]))
    writer.setFont('Helvetica-Bold', 12)
    writer.drawString(42, 274, 'Informasi pembayaran')
    writer.setFont('Helvetica', 11)
    writer.drawString(42, 247, 'Bank: ' + data['payment']['bank_name'])
    writer.drawString(42, 224, 'Atas nama: ' + data['payment']['account_holder'])
    writer.drawString(42, 201, 'Nomor rekening: ' + data['payment']['account_number'])
    writer.setFont('Helvetica', 9)
    writer.setFillColor(colors.HexColor('#667685'))
    writer.drawString(42, 63, f"AMIGA demo final | {data['invoice_number']} | halaman invoice 1/{2 if faktur_page else 1}")
    writer.showPage()
    if faktur_page:
        writer.setFillColor(colors.HexColor('#17334A'))
        writer.setFont('Helvetica-Bold', 16)
        writer.drawString(42, 790, 'FAKTUR PAJAK')
        writer.setFillColor(colors.HexColor('#A34400'))
        writer.setFont('Helvetica-Bold', 10)
        writer.drawString(42, 770, 'CONTOH, BUKAN DOKUMEN PAJAK SAH')
        writer.setFillColor(colors.HexColor('#17334A'))
        writer.setFont('Helvetica', 11)
        lines = ('Kode dan Nomor Seri Faktur Pajak: ' + data['faktur_number'], 'Tanggal faktur: ' + data['faktur_date'],
                 'Pengusaha Kena Pajak: ' + data['vendor_name'], 'NPWP: ' + data['vendor_npwp'],
                 'Pembeli Barang Kena Pajak / Penerima Jasa Kena Pajak: ' + data['buyer_name'],
                 'NPWP: ' + data['buyer_npwp'], 'Dasar Pengenaan Pajak: ' + money(data['stated_subtotal']),
                 'DPP Nilai Lain (11/12): ' + money('3666667.00'), 'PPN 12% x DPP Nilai Lain: ' + money(data['stated_tax_total']),
                 'Referensi invoice: ' + data['invoice_number'])
        for index, text in enumerate(lines):
            writer.drawString(42, 735 - index * 24, text)
        writer.setFont('Helvetica', 9)
        writer.setFillColor(colors.HexColor('#667685'))
        writer.drawString(42, 63, f"AMIGA demo final | {data['invoice_number']} | halaman faktur 2/2")
        writer.showPage()
    writer.save()
    return buffer.getvalue()


def as_image(pdf, fmt):
    """First page as a phone photo (JPEG: tilted, soft, paper tone) or a clean scan (PNG)."""
    with pymupdf.open(stream=pdf, filetype='pdf') as document:
        png = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes('png')
    image = Image.open(BytesIO(png)).convert('RGB')
    out = BytesIO()
    if fmt == 'jpeg':
        image = image.rotate(1.4, expand=True, fillcolor=(236, 233, 226)).filter(ImageFilter.GaussianBlur(0.6))
        image.save(out, 'JPEG', quality=82)
    else:
        image.save(out, 'PNG', optimize=True)
    return out.getvalue()


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    # 002 was uploaded in the gladi, 003 is for the live demo, 004 is a spare if the live upload must be retried.
    for number in ('INV-DEMO-002', 'INV-DEMO-003', 'INV-DEMO-004'):
        path = OUT / (number.lower() + '.pdf')
        data = invoice(number)
        if not path.exists():  # demo files are frozen once made; only missing ones are drawn
            draw(path, data)
        manifest.append({'pdf': str(path.relative_to(ROOT)).replace('\\', '/'),
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'expected_invoice': data})
    # 005 PDF with faktur page and 006 phone photo are for the stage 6 live demo; 007 and 008 are their spares.
    for number, kind in (('INV-DEMO-005', 'pdf'), ('INV-DEMO-006', 'jpeg'), ('INV-DEMO-007', 'pdf'),
                         ('INV-DEMO-008', 'png')):
        data = invoice_v2(number, ppn=kind == 'pdf')
        path = OUT / (number.lower() + {'pdf': '.pdf', 'jpeg': '.jpg', 'png': '.png'}[kind])
        if not path.exists():
            pdf = draw_v2(data, faktur_page=kind == 'pdf')
            path.write_bytes(pdf if kind == 'pdf' else as_image(pdf, kind))
        manifest.append({'file': str(path.relative_to(ROOT)).replace('\\', '/'),
                         'media_type': {'pdf': 'application/pdf', 'jpeg': 'image/jpeg', 'png': 'image/png'}[kind],
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                         'tax_preset': 'PPN 11% + PPh 23 2%' if kind == 'pdf' else 'PPh 23 2% saja',
                         'expected_invoice': data})
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps([{'file': m.get('pdf') or m['file'], 'sha256': m['sha256']} for m in manifest], indent=2))


if __name__ == '__main__':
    build()
