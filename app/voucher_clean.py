"""Frozen v6 print design: AMIGA branding, one amount summary, and verifiable signatures.

v7 keeps the same page and replaces only the signature section: three empty boxes for wet signatures (Admin Intake,
Finance Reviewer, Manajer Keuangan), without specimens, electronic-signature text or codes. v6 stays byte-identical.
"""

from datetime import datetime
from decimal import Decimal
from functools import partial
import hashlib
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (Flowable, HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

# Frozen to the approved app/static/app.css palette; old templates keep their own colors.
BRAND = {'ink': '#1F2A3A', 'navy': '#324158', 'muted': '#5B6779', 'teal': '#4497A1',
         'teal_strong': '#2E6E76', 'teal_soft': '#E3F0F1', 'pink': '#FF80B4',
         'pink_soft': '#FFF0F6', 'line': '#DAD8D8', 'line_soft': '#ECEAEA'}
LOGO = Path(__file__).parent / 'static/brand/amiga-logo.png'
LOGO_SHA256 = '701c7d3ebd4850aee5102e86917090145054fa5a033f66717d8a092f03b196c4'


def render_clean(payload, signoff=None, specimens=None):
    # Imported lazily: voucher_pdf registers the frozen fonts before dispatching here.
    from .voucher_pdf import money, qr_code, tanggal, terbilang

    tax, invoice = payload.get('tax'), payload['invoice']
    if not tax or tax.get('status') != 'COMPUTED':
        raise ValueError('Voucher v6 requires a computed tax block')
    logo_bytes = LOGO.read_bytes()
    if hashlib.sha256(logo_bytes).hexdigest() != LOGO_SHA256:
        raise ValueError('The frozen v6 logo changed; preserve this asset before changing the template')
    palette = {key: colors.HexColor(value) for key, value in BRAND.items()}
    final, specimens = signoff is not None, specimens or {}
    wet = payload['template_version'] in ('amiga-demo-v7', 'amiga-demo-v8')
    reviewer = payload['signatures']['reviewer']
    currency = 'Rp' if invoice['currency'] == 'IDR' else invoice['currency']
    width, height = A4
    usable = width - 84

    normal = ParagraphStyle('v6-body', fontName='Amiga', fontSize=9, leading=13,
                            textColor=palette['ink'], splitLongWords=1)
    muted = ParagraphStyle('v6-muted', parent=normal, fontSize=7.5, leading=11, textColor=palette['muted'])
    bold = ParagraphStyle('v6-bold', parent=normal, fontName='AmigaBold')
    label = ParagraphStyle('v6-label', parent=bold, fontSize=7.2, leading=11, textColor=palette['teal_strong'])
    right = ParagraphStyle('v6-right', parent=normal, alignment=TA_RIGHT)
    right_bold = ParagraphStyle('v6-right-bold', parent=right, fontName='AmigaBold')
    centered = ParagraphStyle('v6-centered', parent=normal, alignment=TA_CENTER)
    centered_bold = ParagraphStyle('v6-centered-bold', parent=bold, alignment=TA_CENTER)
    centered_small = ParagraphStyle('v6-centered-small', parent=muted, alignment=TA_CENTER)

    def p(value, style=normal):
        return Paragraph(escape(str(value if value is not None else '-')).replace('\n', '<br/>'), style)

    def amount(value):
        return currency + ' ' + money(value)

    def jakarta(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Jakarta'))

    def frame(canvas, document):
        canvas.saveState()
        canvas.drawImage(ImageReader(BytesIO(logo_bytes)), 42, height-72, width=139, height=139*304/1080, mask='auto')
        canvas.setFillColor(palette['navy'])
        canvas.setFont('AmigaBold', 14)
        canvas.drawRightString(width-42, height-43, 'VOUCHER PENGELUARAN')
        canvas.setFont('Amiga', 9)
        canvas.setFillColor(palette['muted'])
        canvas.drawRightString(width-42, height-60, payload['number'])
        if wet:
            status = 'FINAL - DISETUJUI' if final else 'DRAF - MENUNGGU MANAJER KEUANGAN'
        else:
            status = 'FINAL - DITANDATANGANI' if final else 'DRAF - MENUNGGU DIREKSI'
        canvas.setFont('AmigaBold', 7)
        badge_width = canvas.stringWidth(status, 'AmigaBold', 7) + 20
        canvas.setFillColor(palette['teal_soft'] if final else palette['pink_soft'])
        canvas.roundRect(width-42-badge_width, height-83, badge_width, 16, 8, stroke=0, fill=1)
        canvas.setFillColor(palette['teal_strong'] if final else palette['navy'])
        canvas.drawRightString(width-52, height-77, status)
        canvas.setStrokeColor(palette['pink'])
        canvas.setLineWidth(2)
        canvas.line(42, height-97, width-42, height-97)
        canvas.setLineWidth(.5)
        canvas.setStrokeColor(palette['line_soft'])
        canvas.line(42, 46, width-42, 46)
        canvas.setFont('Amiga', 7)
        canvas.setFillColor(palette['muted'])
        canvas.drawString(42, 32, payload['number'])
        canvas.drawRightString(width-42, 32, 'Halaman '+str(document.page))
        canvas.restoreState()

    payment = invoice['payment']
    faktur = tax.get('faktur_number') or (payload.get('tax_selection') or {}).get('faktur_number')
    left = [p('KLIEN', label), p(payload['client']['name'], bold), Spacer(1, 12),
            p('DIBAYARKAN KEPADA', label), p(invoice['vendor_name'], bold)]
    if invoice.get('vendor_npwp'):
        left.append(p('NPWP '+invoice['vendor_npwp'], muted))
    right_info = [p('REFERENSI INVOICE', label), p(invoice['invoice_number'], bold),
                  p('Tanggal invoice: '+tanggal(invoice['invoice_date']), muted),
                  p('Tanggal voucher: '+tanggal(jakarta(payload['approved_at'])), muted)]
    if invoice.get('due_date'):
        right_info.append(p('Jatuh tempo: '+tanggal(invoice['due_date']), muted))
    if invoice.get('po_number'):
        right_info.append(p('PO: '+invoice['po_number'], muted))
    if faktur:
        right_info.append(p('Faktur pajak: '+faktur, muted))
    info = Table([[left, right_info]], colWidths=[usable*.51, usable*.49])
    info.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                             ('RIGHTPADDING',(0,0),(-1,-1),16),('TOPPADDING',(0,0),(-1,-1),0),
                             ('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    header_text = ParagraphStyle('v6-table-header', parent=bold, fontSize=7.5, leading=11,
                                textColor=palette['teal_strong'])
    header_right = ParagraphStyle('v6-table-header-right', parent=header_text, alignment=TA_RIGHT)
    rows = [[p('NO', header_text), p('KETERANGAN', header_text), p('QTY', header_right),
             p('HARGA SATUAN', header_right), p('JUMLAH', header_right)]]
    for item in invoice['line_items']:
        rows.append([p(item['line_number'], muted), p(item['description']), p(item['quantity'], right),
                     p(money(item.get('unit_price')), right), p(money(item.get('stated_line_total')), right)])
    lines = Table(rows, colWidths=[32, usable-248, 40, 84, 92], repeatRows=1, splitByRow=1, splitInRow=1)
    lines.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),palette['teal_soft']),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.5,palette['teal']),
        ('LINEBELOW',(0,1),(-1,-1),.4,palette['line_soft']),('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))

    adjusted = tax.get('ppn_origin') == 'INTERNAL_ADJUSTMENT'
    if adjusted:
        summary_rows = [('Total invoice', tax.get('invoice_total') or invoice['stated_total'])]
    else:
        summary_rows = [('Subtotal', invoice['stated_subtotal'])]
        if Decimal(invoice.get('stated_discount_total') or '0'):
            summary_rows.append(('Diskon', '-'+money(invoice['stated_discount_total'])))
        if Decimal(invoice.get('stated_other_charges_total') or '0'):
            summary_rows.append(('Biaya lain', invoice['stated_other_charges_total']))
    if Decimal(tax.get('ppn_amount') or '0'):
        summary_rows.append(('PPN tambahan' if adjusted else 'PPN', tax['ppn_amount']))
    if Decimal(tax['withheld_total']):
        summary_rows.extend([('Total tagihan', tax['gross_total']),
                             ('Potongan '+tax['pph_short'], '-'+money(tax['withheld_total']))])
    total_cells = []
    for title, value in summary_rows:
        # Negative values have already been formatted for a readable discount/withholding.
        printed = value if isinstance(value, str) and value.startswith('-') else money(value)
        total_cells.append([p(title, muted), p(printed, right)])
    total_cells.append([p('JUMLAH KE VENDOR', label), p(amount(tax['net_payable']), right_bold)])
    totals = Table(total_cells, colWidths=[176, 142])
    totals.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),
        ('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('LINEABOVE',(0,-1),(-1,-1),1,palette['pink']),('BACKGROUND',(0,-1),(-1,-1),palette['teal_soft']),
        ('TOPPADDING',(0,-1),(-1,-1),10),('BOTTOMPADDING',(0,-1),(-1,-1),10)]))
    bank = [p('REKENING TUJUAN', label), p(payment['bank_name'], bold), p(payment['account_number']),
            p('a.n. '+str(payment['account_holder'] or '-'), muted), Spacer(1, 12),
            p('TERBILANG', label), p(terbilang(tax['net_payable']), muted)]
    summary = Table([[bank, totals]], colWidths=[usable-318, 318])
    summary.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
        ('RIGHTPADDING',(0,0),(0,0),18),('RIGHTPADDING',(1,0),(1,0),0),('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0)]))

    class VerificationQR(Flowable):
        def __init__(self, url):
            super().__init__()
            self.width = self.height = 65
            self.url = url
            self.hAlign = 'CENTER'

        def draw(self):
            renderPDF.draw(qr_code(self.url, 65), self.canv, 0, 0)
            self.canv.linkURL(self.url, (0, 0, 65, 65), relative=1, thickness=0)

    def signer(title, signature):
        data = specimens.get(signature.get('specimen_sha256') or '')
        stamp = Image(BytesIO(data), width=108, height=36, kind='proportional') if data else Spacer(1,36)
        return [p(title, centered), Spacer(1, 4), stamp, p(signature['name'], centered_bold),
                p(signature.get('title') or '', centered_small), p('Ditandatangani secara elektronik', centered_small),
                p(jakarta(signature['signed_at']).strftime('%d-%m-%Y %H:%M WIB'), centered_small),
                p('Kode verifikasi: '+signature['code'], centered_small)]

    def wet_box(person, fallback_title):
        # Room for a wet signature after printing, a line to sign on, then the printed name and title.
        box = [Spacer(1, 50), HRFlowable(width='80%', thickness=.6, color=palette['muted'], spaceAfter=5)]
        if person.get('name'):
            box.append(p(person['name'], centered_bold))
        return box + [p(person.get('title') or fallback_title, centered_small)]

    if wet:
        # 15 Okt 2026, Aldian: three wet signatures on the printed voucher. The approvals in the app stay on record and
        # behind the QR, but no specimen, electronic-signature text or code is printed.
        caption = ParagraphStyle('v7-caption', parent=label, alignment=TA_CENTER)
        submitter = payload.get('submitter') or {'name': payload['uploader']['name']}
        approver = signoff['director'] if final else payload.get('assigned_director') or {}
        if payload['template_version'] == 'amiga-demo-v8':
            # 17 Okt 2026, Aldian: two wet signatures, the PIC and the vendor receiving the payment. Finance and the
            # Manajer Keuangan still approve in the app; their approvals stay behind the QR, not on the print.
            vendor = {'name': invoice['vendor_name'], 'title': 'Vendor penerima pembayaran'}
            signatures = Table([[p('Diajukan Oleh', caption), p('Diterima Oleh', caption)],
                                [wet_box(submitter, 'Admin Intake AMIGA'), wet_box(vendor, 'Vendor penerima pembayaran')]],
                               colWidths=[usable/2]*2)
        else:
            signatures = Table([[p('Diajukan Oleh', caption), p('Diperiksa Oleh', caption), p('Disetujui Oleh', caption)],
                                [wet_box(submitter, 'Admin Intake AMIGA'), wet_box(reviewer, 'Finance Reviewer AMIGA'),
                                 wet_box(approver, 'Manajer Keuangan AMIGA')]], colWidths=[usable/3]*3)
        signatures.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('GRID',(0,0),(-1,-1),.6,palette['line']),('BACKGROUND',(0,0),(-1,0),palette['teal_soft']),
            ('TOPPADDING',(0,0),(-1,0),6),('BOTTOMPADDING',(0,0),(-1,0),6),
            ('TOPPADDING',(0,1),(-1,1),4),('BOTTOMPADDING',(0,1),(-1,1),10)]))
        section = [signatures]
        if final:
            qr = Table([[VerificationQR(signoff['verify_url']),
                         p('Klik / pindai QR untuk melihat jejak persetujuan di aplikasi AMIGA.', muted)]],
                       colWidths=[80, usable-80])
            qr.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),
                                    ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
            section.append(qr)
    else:
        director = payload.get('assigned_director') or {}
        director_box = (signer('Disetujui Oleh', signoff['director']) if final else
                        [p('Disetujui Oleh', centered), Spacer(1,40),
                         p(director.get('name') or 'Direksi AMIGA', centered_bold),
                         p(director.get('title') or 'Direksi AMIGA', centered_small),
                         p('Menunggu tanda tangan', centered_small)])
        verification = ([VerificationQR(signoff['verify_url']), Spacer(1,4), p('Klik / pindai QR', centered_small)]
                        if final else '')
        signatures = Table([[signer('Diajukan Oleh', reviewer), verification, director_box]],
                           colWidths=[(usable-85)/2, 85, (usable-85)/2])
        signatures.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('LINEABOVE',(0,0),(0,0),.6,palette['line']),('LINEABOVE',(2,0),(2,0),.6,palette['line']),
            ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
        section = [signatures]
    stream = BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, leftMargin=42, rightMargin=42, topMargin=114,
        bottomMargin=57, invariant=1, title='Voucher Pengeluaran '+payload['number'], author='AMIGA')
    story = [info, Spacer(1,22), lines, Spacer(1,18), KeepTogether([summary]), Spacer(1,26),
             KeepTogether(section), Spacer(1,12),
             p('Pembayaran dilakukan oleh klien di luar aplikasi.', centered_small)]
    document.build(story, onFirstPage=frame, onLaterPages=frame, canvasmaker=partial(Canvas,invariant=1))
    return stream.getvalue()
