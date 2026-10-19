"""Public verification page for one voucher. Server-rendered and escaped; styles come from /static/app.css (the CSP
blocks inline styles). It shows the number, status, signers and hashes only: no amount, account or vendor."""

from html import escape

STATUS = {
    'SAH': ('ready', 'Sah. Ditandatangani Finance dan Direksi AMIGA.'),
    'MENUNGGU_DIREKSI': ('processing', 'Menunggu tanda tangan direksi. Voucher ini baru ditandatangani Finance AMIGA.'),
    'DIGANTIKAN': ('exception', 'Diganti. Voucher ini tidak berlaku lagi karena datanya sudah dikoreksi atau dikembalikan.'),
}
# From amiga-demo-v7 the printed voucher has empty boxes for wet signatures; this page shows the approvals in the app.
WET_STATUS = STATUS | {
    'SAH': ('ready', 'Sah. Disetujui Finance dan Manajer Keuangan AMIGA. Tanda tangan basah ada di voucher cetak.'),
    'MENUNGGU_DIREKSI': ('processing', 'Menunggu persetujuan manajer keuangan. Voucher ini baru disetujui Finance AMIGA.'),
}


def signer_note(signer):
    if signer['code']:
        return f'Ditandatangani secara elektronik {escape(signer["signed_at"])}. Kode {escape(signer["code"])}'
    action = 'Diajukan' if signer['role'] == 'Diajukan Oleh' else 'Disetujui'
    return f'{action} di aplikasi AMIGA {escape(signer["signed_at"])}.'


def render_page(result):
    wet = bool(result and result.get('wet_signatures'))
    if result is None:
        body = ('<span class="eyebrow">VERIFIKASI VOUCHER</span><h1>Voucher tidak ditemukan</h1>'
                '<p class="muted">Periksa kembali kode QR atau tautan yang Anda terima.</p>')
    else:
        tone, label = (WET_STATUS if wet else STATUS)[result['status']]
        signers = ''.join(
            f'<li><strong>{escape(signer["role"])}</strong><span>{escape(signer["name"])}, {escape(signer["title"])}</span>'
            f'<small>{signer_note(signer)}</small></li>'
            for signer in result['signers'])
        hashes = ''.join(f'<p class="verify-hash"><span>{label}</span>{escape(value)}</p>'
                         for label, value in (('SHA-256 PDF final', result['final_pdf_sha256']),
                                              ('SHA-256 PDF draf', result['draft_pdf_sha256'])) if value)
        body = (f'<span class="eyebrow">VERIFIKASI VOUCHER</span><h1>{escape(result["number"])}</h1>'
                f'<p class="verify-status {tone}">{escape(label)}</p>'
                f'<h2>{"Persetujuan di aplikasi" if wet else "Penanda tangan"}</h2><ul class="verify-signers">{signers}</ul>'
                '<h2>Keutuhan isi</h2>'
                f'<p>Isi voucher cocok dengan {"persetujuan" if wet else "tanda tangan"}: '
                f'<strong>{"Ya" if result["content_matches"] else "Tidak"}</strong></p>'
                f'{hashes}<p class="muted">Cocokkan dengan hash file PDF yang Anda terima, misalnya lewat Get-FileHash '
                'di Windows.</p>')
    note = ('Tanda tangan basah ada di voucher cetak. Halaman ini mencatat persetujuan di aplikasi AMIGA.' if wet else
            'Tanda tangan elektronik tidak tersertifikasi (PP 71/2019 Pasal 60 ayat 4).')
    return ('<!doctype html><html lang="id"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Verifikasi Voucher · AMIGA</title>'
            '<link rel="icon" href="/static/brand/amiga-icon.png" type="image/png">'
            '<link rel="stylesheet" href="/static/app.css"></head><body class="verify-body"><main class="verify-card">'
            '<div class="brand"><img class="brand-logo" src="/static/brand/amiga-logo.png" '
            'alt="AMIGA" width="1080" height="304"></div>'
            f'{body}<p class="verify-note">Halaman ini sengaja tidak menampilkan nominal, rekening, atau vendor. '
            f'{note}</p></main></body></html>')
