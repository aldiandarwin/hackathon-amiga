"""Deterministic local demo voucher. Input is the immutable approval payload only."""

from datetime import datetime
from decimal import Decimal
from functools import partial
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import reportlab
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, CondPageBreak, Image

TEMPLATE_VERSION = 'amiga-demo-v8'
TEMPLATES = ('amiga-demo-v1', 'amiga-demo-v2', 'amiga-demo-v3', 'amiga-demo-v4', 'amiga-demo-v5', 'amiga-demo-v6',
             'amiga-demo-v7', 'amiga-demo-v8')
BULAN = ('Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober',
         'November', 'Desember')
INK = colors.HexColor('#173F35')
MUTED = colors.HexColor('#688071')
LINE = colors.HexColor('#DCE6DF')
LIGHT = colors.HexColor('#F1F6F2')
FONT_DIR = Path(reportlab.__file__).parent/'fonts'
pdfmetrics.registerFont(TTFont('Amiga',str(FONT_DIR/'Vera.ttf')))
pdfmetrics.registerFont(TTFont('AmigaBold',str(FONT_DIR/'VeraBd.ttf')))
pdfmetrics.registerFontFamily('Amiga',normal='Amiga',bold='AmigaBold')


def money(value):
    if value is None:
        return '-'
    return format(Decimal(value),',f').replace(',','_').replace('.',',').replace('_','.')


def tanggal(value):
    """'2026-10-14' or a datetime, printed the way AMIGA's voucher does: 14 Oktober 2026."""
    if value is None:
        return '-'
    day = value if isinstance(value, datetime) else datetime.strptime(value, '%Y-%m-%d')
    return f'{day.day} {BULAN[day.month - 1]} {day.year}'


SATUAN = ('', 'satu', 'dua', 'tiga', 'empat', 'lima', 'enam', 'tujuh', 'delapan', 'sembilan', 'sepuluh', 'sebelas')


def _words(number):
    if number < 12:
        return SATUAN[number]
    if number < 20:
        return _words(number - 10) + ' belas'
    if number < 100:
        return _words(number // 10) + ' puluh' + (' ' + _words(number % 10) if number % 10 else '')
    if number < 200:
        return 'seratus' + (' ' + _words(number - 100) if number > 100 else '')
    if number < 1000:
        return _words(number // 100) + ' ratus' + (' ' + _words(number % 100) if number % 100 else '')
    if number < 2000:
        return 'seribu' + (' ' + _words(number - 1000) if number > 1000 else '')
    for size, name in ((10**12, 'triliun'), (10**9, 'miliar'), (10**6, 'juta'), (10**3, 'ribu')):
        if number >= size:
            return _words(number // size) + ' ' + name + (' ' + _words(number % size) if number % size else '')


def terbilang(value):
    """Amount in Indonesian words, as a payment voucher prints it under the nominal."""
    amount = Decimal(value)
    rupiah = int(amount)
    sen = int((amount - rupiah) * 100)
    words = (_words(rupiah) if rupiah else 'nol') + ' rupiah' + (' ' + _words(sen) + ' sen' if sen else '')
    return words[0].upper() + words[1:]


def qr_code(url, size=66):
    widget = QrCodeWidget(url)
    left, bottom, right, top = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (right - left), 0, 0, size / (top - bottom), 0, 0])
    drawing.add(widget)
    return drawing


def render_voucher(payload, signoff=None, specimens=None):
    if payload['template_version'] not in TEMPLATES:
        raise ValueError('Unsupported frozen template version')
    if payload['template_version'] in ('amiga-demo-v6', 'amiga-demo-v7', 'amiga-demo-v8'):
        from .voucher_clean import render_clean
        return render_clean(payload, signoff, specimens)
    if payload['template_version'] in ('amiga-demo-v4', 'amiga-demo-v5'):
        return render_signed(payload, signoff, specimens)
    if signoff is not None:
        raise ValueError('Only amiga-demo-v4 prints electronic signatures')
    if payload['template_version'] == 'amiga-demo-v3':
        return render_pengeluaran(payload)
    # v1 stays byte-identical for vouchers frozen before the tax block existed.
    tax = payload.get('tax') if payload['template_version'] == 'amiga-demo-v2' else None
    if payload['template_version'] == 'amiga-demo-v2' and (not tax or tax['status'] != 'COMPUTED'):
        raise ValueError('Voucher v2 requires a computed tax block')
    invoice = payload['invoice']
    stream = BytesIO()
    normal = ParagraphStyle('body',fontName='Amiga',fontSize=8.5,leading=13,textColor=INK,spaceAfter=3,splitLongWords=1)
    small = ParagraphStyle('small',parent=normal,fontSize=7,leading=10,textColor=MUTED)
    bold = ParagraphStyle('bold',parent=normal,fontName='AmigaBold')
    right = ParagraphStyle('right',parent=normal,alignment=TA_RIGHT,fontSize=8)
    heading = ParagraphStyle('heading',parent=bold,fontSize=11,leading=16,spaceBefore=10,spaceAfter=7)

    def p(value,style=normal):
        return Paragraph(escape(str(value if value is not None else '-')).replace('\n','<br/>'),style)

    def metadata_row(label,value):
        return [p(label,small),p(value)]

    def page_frame(canvas,document):
        width,height=A4
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.setFont('AmigaBold',19)
        canvas.drawString(42,height-47,'AMIGA')
        canvas.setFont('Amiga',8)
        canvas.setFillColor(MUTED)
        canvas.drawString(42,height-63,'ROBOT ADMIN / INTERNAL REVIEW')
        canvas.setFillColor(colors.HexColor('#F7ECD8'))
        canvas.roundRect(width-175,height-65,133,31,6,fill=1,stroke=0)
        canvas.setFillColor(colors.HexColor('#966A25'))
        canvas.setFont('AmigaBold',8)
        canvas.drawCentredString(width-108.5,height-45,'DEMO - BUKAN OTORISASI')
        canvas.drawCentredString(width-108.5,height-57,'PEMBAYARAN')
        canvas.setStrokeColor(LINE)
        canvas.line(42,49,width-42,49)
        canvas.setFont('Amiga',7)
        canvas.setFillColor(MUTED)
        canvas.drawString(42,35,payload['number']+' / v'+str(payload['invoice_version']))
        canvas.drawRightString(width-42,35,'Halaman '+str(document.page))
        canvas.restoreState()

    document=SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=86,bottomMargin=60,invariant=1,
        title='Voucher Demo '+payload['number'],author='AMIGA Robot Admin - Local Demo')
    story=[p('Voucher review invoice',ParagraphStyle('title',parent=bold,fontSize=23,leading=30)),
           p(payload['number'],small),Spacer(1,12)]
    approved_time=datetime.fromisoformat(payload['approved_at']).astimezone(ZoneInfo('Asia/Jakarta')).strftime('%d-%m-%Y %H:%M WIB')
    info=Table([metadata_row('KLIEN',payload['client']['name']),metadata_row('VENDOR',invoice['vendor_name']),
        metadata_row('NOMOR INVOICE',invoice['invoice_number']),metadata_row('TANGGAL INVOICE',invoice['invoice_date']),
        metadata_row('VERSI DISETUJUI',str(payload['invoice_version'])+' / '+approved_time)],colWidths=[119,392])
    info.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.extend([info,CondPageBreak(100),p('Rincian invoice',heading)])
    rows=[[p('NO',small),p('DESKRIPSI',small),p('QTY',small),p('HARGA SATUAN',small),p('JUMLAH',small)]]
    for item in invoice['line_items']:
        rows.append([p(item['line_number'],small),p(item['description']),p(item['quantity'],right),
                     p(money(item['unit_price']),right),p(money(item['stated_line_total']),right)])
    # v2 is tighter so the extra tax rows cost no page that v1 did not need.
    pad=5 if tax else 7
    items=Table(rows,colWidths=[27,208,43,113,120],repeatRows=1,splitByRow=1,splitInRow=1)
    items.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LINEBELOW',(0,0),(-1,-1),.4,LINE),('TOPPADDING',(0,0),(-1,-1),pad),('BOTTOMPADDING',(0,0),(-1,-1),pad)]))
    story.extend([items,Spacer(1,15)])
    # Schema v3: a charge printed below the subtotal; payloads signed before it have no such key.
    other=invoice.get('stated_other_charges_total')
    extra=[('Biaya lain',other)] if other and Decimal(other) else []
    if tax:
        rows=[('Subtotal',invoice['stated_subtotal']),('Diskon',invoice['stated_discount_total'])]+extra+[('PPN',tax['ppn_amount']),
              ('TOTAL INVOICE',invoice['stated_total']),('Potongan '+tax['pph_short'],tax['withheld_total']),
              ('JUMLAH DIBAYARKAN',tax['net_payable'])]
        padding=2
    else:
        rows=[('Subtotal',invoice['stated_subtotal']),('Diskon',invoice['stated_discount_total'])]+extra+[
              ('Pajak',invoice['stated_tax_total']),('TOTAL INVOICE',invoice['stated_total'])]
        padding=5
    totals=Table([[p(label,small),p(invoice['currency']+' '+money(value),right)] for label,value in rows],colWidths=[100,143])
    totals.setStyle(TableStyle([('BACKGROUND',(0,-1),(-1,-1),LIGHT),('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding)]))
    summary=Table([[[p('Informasi rekening',heading),p(invoice['payment']['bank_name'],bold),
        p('Nomor rekening: '+str(invoice['payment']['account_number'] or '-')),
        p('Atas nama: '+str(invoice['payment']['account_holder'] or '-'))],totals]],colWidths=[268,243],splitInRow=1)
    summary.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
    story.append(summary)
    if tax:
        faktur=payload['tax_selection']['faktur_number'] if tax['ppn_applied'] else None
        story.append(p('Pajak dihitung sistem: '+tax['pph_label']+' ('+tax['basis']+')'
                       +(', dasar PPh '+invoice['currency']+' '+money(tax['pph_base']) if tax['pph_id']!='TANPA' else '')
                       +', aturan '+tax['rules_version']+'. '+' '.join(tax['assumptions'])
                       +(' Faktur pajak '+faktur+' (input manual).' if faktur else ''),small))
    story.extend([p('Jejak review internal',heading),p('Pengunggah: '+payload['uploader']['name']),
        p('Finance Reviewer: '+payload['reviewer']['name']),p('Catatan: '+payload['review_note']),
        p('Konfirmasi sumber: seluruh field dan halaman telah diperiksa oleh reviewer.',small)])
    if payload['source_review']['reviewed_checks']:
        story.append(p('Pemeriksaan sumber yang dikonfirmasi manual: '+str(len(payload['source_review']['reviewed_checks'])),small))
    story.append(KeepTogether(([] if tax else [Spacer(1,12)])+[p('BATAS OTORISASI',bold),
        p('Dokumen demo ini mencatat review data invoice internal. Persetujuan pembayaran oleh klien dan eksekusi pembayaran dilakukan di luar aplikasi. Template serta penomoran belum merupakan format resmi Finance.',small),
        Spacer(1,10),p('Request: '+payload['request_id'],small),p('SHA-256 dokumen sumber: '+payload['source_document_sha256'],small),
        p('Template: '+payload['template_version']+' / Sumber: '+('data sintetis' if payload['source_mode']=='REPLAY' else 'dokumen unggahan'),small)]))
    document.build(story,onFirstPage=page_frame,onLaterPages=page_frame,canvasmaker=partial(Canvas,invariant=1))
    return stream.getvalue()


def render_pengeluaran(payload):
    """amiga-demo-v3 follows AMIGA's own Voucher Pengeluaran: header block, one table of payment lines, TOTAL, and the
    Diajukan Oleh / Disetujui Oleh boxes. Client approval stays outside the app, so that box is left blank.
    It is a separate function so v1 and v2 keep rendering byte for byte as before."""
    tax = payload.get('tax')
    if not tax or tax['status'] != 'COMPUTED':
        raise ValueError('Voucher v3 requires a computed tax block')
    invoice = payload['invoice']
    currency = invoice['currency']
    stream = BytesIO()
    normal = ParagraphStyle('body',fontName='Amiga',fontSize=8.5,leading=12,textColor=INK,splitLongWords=1)
    small = ParagraphStyle('small',parent=normal,fontSize=7,leading=10,textColor=MUTED)
    bold = ParagraphStyle('bold',parent=normal,fontName='AmigaBold')
    right = ParagraphStyle('right',parent=normal,alignment=TA_RIGHT)
    right_bold = ParagraphStyle('rightbold',parent=bold,alignment=TA_RIGHT)
    centered = ParagraphStyle('centered',parent=normal,alignment=TA_CENTER)
    centered_bold = ParagraphStyle('centeredbold',parent=bold,alignment=TA_CENTER)
    centered_small = ParagraphStyle('centeredsmall',parent=small,alignment=TA_CENTER)
    heading = ParagraphStyle('heading',parent=bold,fontSize=10,leading=14,spaceBefore=8,spaceAfter=4)

    def p(value,style=normal):
        return Paragraph(escape(str(value if value is not None else '-')).replace('\n','<br/>'),style)

    def page_frame(canvas,document):
        # Same frame as v1 and v2, so every voucher keeps the demo badge and the page footer.
        width,height=A4
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.setFont('AmigaBold',19)
        canvas.drawString(42,height-47,'AMIGA')
        canvas.setFont('Amiga',8)
        canvas.setFillColor(MUTED)
        canvas.drawString(42,height-63,'ROBOT ADMIN / INTERNAL REVIEW')
        canvas.setFillColor(colors.HexColor('#F7ECD8'))
        canvas.roundRect(width-175,height-65,133,31,6,fill=1,stroke=0)
        canvas.setFillColor(colors.HexColor('#966A25'))
        canvas.setFont('AmigaBold',8)
        canvas.drawCentredString(width-108.5,height-45,'DEMO - BUKAN OTORISASI')
        canvas.drawCentredString(width-108.5,height-57,'PEMBAYARAN')
        canvas.setStrokeColor(LINE)
        canvas.line(42,49,width-42,49)
        canvas.setFont('Amiga',7)
        canvas.setFillColor(MUTED)
        canvas.drawString(42,35,payload['number']+' / v'+str(payload['invoice_version']))
        canvas.drawRightString(width-42,35,'Halaman '+str(document.page))
        canvas.restoreState()

    document=SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=82,bottomMargin=58,invariant=1,
        title='Voucher Pengeluaran '+payload['number'],author='AMIGA Robot Admin - Local Demo')
    approved=datetime.fromisoformat(payload['approved_at']).astimezone(ZoneInfo('Asia/Jakarta'))
    story=[p('VOUCHER PENGELUARAN',ParagraphStyle('title',parent=bold,fontSize=16,leading=21,alignment=TA_CENTER)),Spacer(1,8)]
    header=Table([[p('Nomor',small),p(payload['number'],bold)],
                  [p('Nama',small),p(payload['reviewer']['name']+' (Finance Reviewer AMIGA)')],
                  [p('Klien',small),p(payload['client']['name'])],
                  [p('Peruntukan',small),p('Pembayaran invoice '+invoice['invoice_number']+' kepada '+invoice['vendor_name'])],
                  [p('Tanggal/Periode',small),p(tanggal(approved))],
                  [p('Nominal',small),p(currency+' '+money(tax['net_payable']),bold)]],colWidths=[105,406])
    header.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,LINE),('BACKGROUND',(0,0),(0,-1),LIGHT),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    story.extend([header,Spacer(1,10)])
    when=tanggal(invoice['invoice_date'])
    rows=[[p('NO',small),p('TANGGAL',small),p('KETERANGAN',small),p('JUMLAH',small),p('HARGA',small)]]
    for item in invoice['line_items']:
        rows.append([p(item['line_number'],small),p(when),p(item['description']),p(item['quantity'],right),
                     p(money(item['stated_line_total']),right)])
    discount=Decimal(invoice['stated_discount_total'] or '0')
    if discount:
        rows.append(['','',p('Diskon'),'',p('-'+money(discount),right)])
    other=Decimal(invoice.get('stated_other_charges_total') or '0')
    if other:
        rows.append(['','',p('Biaya lain'),'',p(money(other),right)])
    # Stage 6 tax blocks carry the faktur number and where it came from; older payloads only had the typed one.
    faktur=(tax.get('faktur_number') or payload['tax_selection']['faktur_number']) if tax['ppn_applied'] else None
    faktur_note=' (dibaca dari dokumen).' if tax.get('faktur_source')=='DOKUMEN' else ' (input manual).'
    # Printed PPN counts even when Finance kept "tanpa PPN", so the rows still add up to the total.
    if Decimal(tax['ppn_amount'] or '0'):
        rows.append(['','',p('PPN'+(' (faktur '+faktur+')' if faktur else '')),'',p(money(tax['ppn_amount']),right)])
    if Decimal(tax['withheld_total']):
        rows.append(['','',p('Potongan '+tax['pph_short']),'',p('-'+money(tax['withheld_total']),right)])
    rows.append([p('TOTAL',bold),'','','',p(currency+' '+money(tax['net_payable']),right_bold)])
    lines=Table(rows,colWidths=[28,94,229,50,110],repeatRows=1,splitByRow=1)
    lines.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,LINE),('BACKGROUND',(0,0),(-1,0),LIGHT),('BACKGROUND',(0,-1),(-1,-1),LIGHT),
        ('SPAN',(0,-1),(3,-1)),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    payment=invoice['payment']
    story.extend([lines,Spacer(1,5),
        p('Transfer ke '+str(payment['bank_name'] or '-')+' nomor '+str(payment['account_number'] or '-')+' atas nama '
          +str(payment['account_holder'] or '-')+'. Rekening cocok dengan master vendor saat approval.',small),
        p('Pajak dihitung sistem: '+tax['pph_label']+' ('+tax['basis']+')'
          +(', dasar PPh '+currency+' '+money(tax['pph_base']) if tax['pph_id']!='TANPA' else '')
          +', aturan '+tax['rules_version']+'. '+' '.join(tax['assumptions'])
          +(' Faktur pajak '+faktur+faktur_note if faktur else ''),small)])

    def box(title,name,role,note):
        return [p(title,centered),Spacer(1,22),p(name,centered_bold),p(role,centered_small),p(note,centered_small)]

    boxes=Table([[box('Diajukan Oleh',payload['reviewer']['name'],'Finance Reviewer AMIGA',
                      'Review disetujui di aplikasi '+approved.strftime('%d-%m-%Y %H:%M WIB')),'',
                  box('Disetujui Oleh','(....................................)','Client Approver',
                      'Persetujuan pembayaran di luar aplikasi')]],colWidths=[215,81,215])
    boxes.setStyle(TableStyle([('BOX',(0,0),(0,0),.6,LINE),('BOX',(2,0),(2,0),.6,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.extend([Spacer(1,10),KeepTogether([boxes]),p('Jejak review internal',heading),
        p('Pengunggah: '+payload['uploader']['name']+'. Finance Reviewer: '+payload['reviewer']['name']+'.'),
        p('Catatan: '+payload['review_note']),
        p('Konfirmasi sumber: seluruh field dan halaman telah diperiksa oleh reviewer.',small)])
    if payload['source_review']['reviewed_checks']:
        story.append(p('Pemeriksaan sumber yang dikonfirmasi manual: '+str(len(payload['source_review']['reviewed_checks'])),small))
    story.append(KeepTogether([Spacer(1,4),p('BATAS OTORISASI',bold),
        p('Dokumen demo ini mencatat review data invoice internal. Persetujuan pembayaran oleh klien dan eksekusi pembayaran '
          'dilakukan di luar aplikasi. Format mengikuti contoh Voucher Pengeluaran AMIGA. Template dan penomoran resmi '
          'menunggu persetujuan Finance.',small),
        Spacer(1,4),p('Request: '+payload['request_id'],small),p('SHA-256 dokumen sumber: '+payload['source_document_sha256'],small),
        p('Template: '+payload['template_version']+' / Sumber: '+('data sintetis' if payload['source_mode']=='REPLAY' else 'dokumen unggahan'),small)]))
    document.build(story,onFirstPage=page_frame,onLaterPages=page_frame,canvasmaker=partial(Canvas,invariant=1))
    return stream.getvalue()


def render_signed(payload, signoff=None, specimens=None):
    """amiga-demo-v4: AMIGA's Voucher Pengeluaran with two electronic signatures. Without a signoff it is the draft
    issued right after Finance signs (brief p6: within 3 s of the reviewer approval), with the director box waiting.
    With a signoff it is the final copy: both signatures, a QR to the verification page and the content hash.
    `specimens` maps a specimen hash to its PNG; a box shows the signer's specimen only once that signer has signed.
    Payment still happens outside the app, which the authorization text keeps saying."""
    specimens = specimens or {}
    tax = payload.get('tax')
    if not tax or tax['status'] != 'COMPUTED':
        raise ValueError('Voucher v4 requires a computed tax block')
    invoice, currency = payload['invoice'], payload['invoice']['currency']
    reviewer = payload['signatures']['reviewer']
    current_layout = payload['template_version'] == 'amiga-demo-v5'
    adjusted = (payload['template_version'] == 'amiga-demo-v5'
                and tax.get('ppn_origin') == 'INTERNAL_ADJUSTMENT')
    final = signoff is not None
    stream = BytesIO()
    normal = ParagraphStyle('body',fontName='Amiga',fontSize=8 if current_layout else 8.5,
                            leading=10 if current_layout else 11,textColor=INK,splitLongWords=1)
    small = ParagraphStyle('small',parent=normal,fontSize=6.8 if current_layout else 7,
                           leading=8 if current_layout else 9,textColor=MUTED)
    bold = ParagraphStyle('bold',parent=normal,fontName='AmigaBold')
    right = ParagraphStyle('right',parent=normal,alignment=TA_RIGHT)
    right_bold = ParagraphStyle('rightbold',parent=bold,alignment=TA_RIGHT)
    centered = ParagraphStyle('centered',parent=normal,alignment=TA_CENTER)
    centered_bold = ParagraphStyle('centeredbold',parent=bold,alignment=TA_CENTER)
    centered_small = ParagraphStyle('centeredsmall',parent=small,alignment=TA_CENTER)
    label = ParagraphStyle('label',parent=bold,fontSize=7.5,leading=10)

    def p(value,style=normal):
        return Paragraph(escape(str(value if value is not None else '-')).replace('\n','<br/>'),style)

    def jakarta(value):
        return datetime.fromisoformat(value).astimezone(ZoneInfo('Asia/Jakarta'))

    def page_frame(canvas,document):
        width,height=A4
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.setFont('AmigaBold',19)
        canvas.drawString(42,height-47,'AMIGA')
        canvas.setFont('Amiga',8)
        canvas.setFillColor(MUTED)
        canvas.drawString(42,height-63,'ROBOT ADMIN / VOUCHER PENGELUARAN')
        canvas.setFillColor(colors.HexColor('#DCEFE4' if final else '#F7ECD8'))
        canvas.roundRect(width-185,height-65,143,31,6,fill=1,stroke=0)
        canvas.setFillColor(INK if final else colors.HexColor('#966A25'))
        canvas.setFont('AmigaBold',8)
        canvas.drawCentredString(width-113.5,height-45,'FINAL - DITANDATANGANI' if final else 'DRAF - MENUNGGU')
        canvas.drawCentredString(width-113.5,height-57,'SECARA ELEKTRONIK' if final else 'TANDA TANGAN DIREKSI')
        canvas.setStrokeColor(LINE)
        canvas.line(42,49,width-42,49)
        canvas.setFont('Amiga',7)
        canvas.setFillColor(MUTED)
        canvas.drawString(42,35,payload['number']+' / v'+str(payload['invoice_version']))
        canvas.drawRightString(width-42,35,'Halaman '+str(document.page))
        canvas.restoreState()

    document=SimpleDocTemplate(stream,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=82,bottomMargin=58,invariant=1,
        title='Voucher Pengeluaran '+payload['number'],author='AMIGA Robot Admin - Local Demo')
    approved=jakarta(payload['approved_at'])
    story=[p('VOUCHER PENGELUARAN',ParagraphStyle('title',parent=bold,fontSize=16,leading=20,alignment=TA_CENTER)),Spacer(1,6)]
    header=Table([[p('Nomor',small),p(payload['number'],bold)],
                  [p('Nama',small),p(reviewer['name']+' ('+reviewer['title']+')')],
                  [p('Klien',small),p(payload['client']['name'])],
                  [p('Peruntukan',small),p('Pembayaran invoice '+invoice['invoice_number']+' kepada '+invoice['vendor_name'])],
                  [p('Tanggal/Periode',small),p(tanggal(approved))],
                  [p('Nominal',small),p(currency+' '+money(tax['net_payable']),bold)],
                  [p('Terbilang',small),p(terbilang(tax['net_payable']))]],colWidths=[105,406])
    header.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,LINE),('BACKGROUND',(0,0),(0,-1),LIGHT),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    payment=invoice['payment']
    faktur=(tax.get('faktur_number') or payload['tax_selection']['faktur_number']) if tax['ppn_applied'] else None
    payee=[p('Dibayarkan kepada',label),p(invoice['vendor_name']),p('NPWP: '+str(invoice.get('vendor_npwp') or '-'),small),
           p('Bank: '+str(payment['bank_name'] or '-'),small),p('No. rekening: '+str(payment['account_number'] or '-'),small),
           p('Atas nama: '+str(payment['account_holder'] or '-'),small)]
    reference=[p('Referensi',label),p('Invoice '+invoice['invoice_number']+', '+tanggal(invoice['invoice_date'])),
               p('Jatuh tempo: '+(tanggal(invoice['due_date']) if invoice.get('due_date') else '-'),small),
               p('PO: '+str(invoice.get('po_number') or '-'),small),p('Faktur pajak: '+str(faktur or '-'),small)]
    parties=Table([[payee,reference]],colWidths=[255.5,255.5])
    parties.setStyle(TableStyle([('BOX',(0,0),(0,0),.4,LINE),('BOX',(1,0),(1,0),.4,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    story.extend([header,Spacer(1,6),parties,Spacer(1,6)])
    when=tanggal(invoice['invoice_date'])
    rows=[[p('NO',small),p('TANGGAL',small),p('KETERANGAN',small),p('JUMLAH',small),p('HARGA',small)]]
    for item in invoice['line_items']:
        # Like AMIGA's own voucher, the unit price sits in the description and HARGA is the line amount.
        detail=[p(item['description'])]+([p(str(item['quantity'])+' x '+currency+' '+money(item['unit_price']),small)]
                                         if item.get('unit_price') is not None else [])
        rows.append([p(item['line_number'],small),p(when),detail,p(item['quantity'],right),
                     p(money(item['stated_line_total']),right)])
    discount=Decimal(invoice['stated_discount_total'] or '0')
    if discount:
        rows.append(['','',p('Diskon'),'',p('-'+money(discount),right)])
    other=Decimal(invoice.get('stated_other_charges_total') or '0')
    if other:
        rows.append(['','',p('Biaya lain'),'',p(money(other),right)])
    # Printed PPN counts even when Finance kept "tanpa PPN", so the rows still add up to the total.
    if Decimal(tax['ppn_amount'] or '0'):
        rows.append(['','',p(('PPN tambahan (internal)' if adjusted else 'PPN')+(' (faktur '+faktur+')' if faktur else '')),'',p(money(tax['ppn_amount']),right)])
    if Decimal(tax['withheld_total']):
        rows.append(['','',p('Potongan '+tax['pph_short']),'',p('-'+money(tax['withheld_total']),right)])
    rows.append([p('TOTAL',bold),'','','',p(currency+' '+money(tax['net_payable']),right_bold)])
    lines=Table(rows,colWidths=[28,94,229,50,110],repeatRows=1,splitByRow=1)
    lines.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,LINE),('BACKGROUND',(0,0),(-1,0),LIGHT),('BACKGROUND',(0,-1),(-1,-1),LIGHT),
        ('SPAN',(0,-1),(3,-1)),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    faktur_note=' (dibaca dari dokumen).' if tax.get('faktur_source')=='DOKUMEN' else ' (input manual).'
    story.extend([lines,Spacer(1,4),
        p('Pajak dihitung sistem: '+tax['pph_label']+' ('+tax['basis']+')'
          +(', dasar PPh '+currency+' '+money(tax['pph_base']) if tax['pph_id']!='TANPA' else '')
          +', aturan '+tax['rules_version']+'. '+' '.join(tax['assumptions'])
          +(' Faktur pajak '+faktur+faktur_note if faktur else ''),small)])

    if adjusted:
        reconciliation = [('Total invoice sumber (tetap)', tax['invoice_total']),
                          ('Tambahan PPN - perhitungan internal', tax['ppn_adjustment_amount']),
                          ('Tagihan setelah penyesuaian, sebelum PPh', tax['gross_total']),
                          ('Potongan '+tax['pph_short'], tax['withheld_total']),
                          ('Nominal ke vendor', tax['net_payable'])]
        summary = Table([[p(title,small),p(currency+' '+money(value),right)] for title,value in reconciliation],
                        colWidths=[365,146])
        summary.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('VALIGN',(0,0),(-1,-1),'TOP'),
                                    ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        story.extend([Spacer(1,5),summary,p('Alasan penyesuaian: '+tax['adjustment_reason'],small),
                      p('CATATAN KONFIRMASI PAJAK KEPADA VENDOR',label),p(tax['vendor_reminder'],small)])
    if payload['template_version'] == 'amiga-demo-v5' and Decimal(tax['withheld_total']):
        story.append(p('Potongan '+tax['pph_short']+' dihitung oleh AMIGA sesuai pilihan yang diperiksa Finance. '
                       'Dokumen bukti potong disiapkan oleh pihak pemotong; voucher ini bukan bukti potong pajak.',small))

    def signed(title,signature):
        png=specimens.get(signature.get('specimen_sha256') or '')
        stamp=Image(BytesIO(png),width=105,height=35) if png else Spacer(1,3)
        return [p(title,centered),stamp,p(signature['name'],centered_bold),p(signature['title'],centered_small),
                p('Ditandatangani secara elektronik',centered_small),
                p(jakarta(signature['signed_at']).strftime('%d-%m-%Y %H:%M WIB'),centered_small),
                p('Kode verifikasi: '+signature['code'],centered_small)]

    director=payload.get('assigned_director')
    approval=(signed('Disetujui Oleh',signoff['director']) if final else
              [p('Disetujui Oleh',centered),Spacer(1,3),p(director['name'] if director else '(Direksi AMIGA)',centered_bold),
               p(director['title'] if director else 'Direksi AMIGA',centered_small),p('Menunggu tanda tangan',centered_small)])
    middle=[qr_code(signoff['verify_url']),p('Pindai untuk verifikasi',centered_small)] if final else ''
    boxes=Table([[signed('Diajukan Oleh',reviewer),middle,approval]],colWidths=[205,101,205])
    boxes.setStyle(TableStyle([('BOX',(0,0),(0,0),.6,LINE),('BOX',(2,0),(2,0),.6,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.extend([Spacer(1,8),KeepTogether([boxes]),Spacer(1,4)])
    if final:
        story.extend([p('Verifikasi keaslian: '+signoff['verify_url'],small),
                      p('SHA-256 isi voucher: '+signoff['content_sha256'],small)])
    story.append(p('Jejak review: diunggah '+payload['uploader']['name']+', diperiksa '+reviewer['name']
                   +'. Catatan: '+payload['review_note']
                   +(' Pemeriksaan sumber yang dikonfirmasi manual: '+str(len(payload['source_review']['reviewed_checks']))+'.'
                     if payload['source_review']['reviewed_checks'] else ''),small))
    story.append(KeepTogether([Spacer(1,4),p('BATAS OTORISASI',bold),
        # The draft is handed out before the BOD signs, so only the final copy may say the BOD approved it.
        p('Voucher ini disiapkan AMIGA Robot Admin dari dokumen klien, diperiksa Finance AMIGA, dan '
          +('disetujui Direksi AMIGA.' if final else 'menunggu persetujuan Direksi AMIGA.')
          +' Persetujuan pembayaran dan transfer tetap dilakukan klien di luar aplikasi, dan AMIGA tidak mentransfer '
          'dana. Tanda tangan elektronik di voucher ini tidak tersertifikasi (PP 71/2019 Pasal 60 ayat 4). Keasliannya '
          'dicek lewat kode QR atau halaman verifikasi.',small),
        Spacer(1,3),p('Request: '+payload['request_id'],small),p('SHA-256 dokumen sumber: '+payload['source_document_sha256'],small),
        p('Template: '+payload['template_version']+' / Sumber: '+('data sintetis' if payload['source_mode']=='REPLAY' else 'dokumen unggahan'),small)]))
    document.build(story,onFirstPage=page_frame,onLaterPages=page_frame,canvasmaker=partial(Canvas,invariant=1))
    return stream.getvalue()
