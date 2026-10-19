"""What the Robot Admin chat may read, and how it finds it.

Every tool reads invoices through visible_rows, the queue's own rule (GET /api/v1/requests): the user's assigned clients,
and for the director only the signing statuses. Database.scoped_request is not used here, because it lets a director
open an invoice the queue never shows, and the chat must not reveal more than the queue does.

Only an allowlist of invoice fields leaves this module: no payment block, no NPWP, no PDF text. Free text from a vendor
document is untrusted, so it is flattened to one line, clipped, and long digit runs are masked.
"""

from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation
import re

from .presentation import queue_summary
from .service import stage
from .sop_api import card_label, nearest_cards, rag_module

# What the queue shows. The final approver is the Manajer Keuangan, named as on the dashboard (web/lib/status.ts).
STATUS_LABELS = {
    'QUEUED': 'Menunggu proses', 'PROCESSING': 'Sedang diproses', 'INTAKE': 'Belum diajukan PIC',
    'RETURNED_TO_PIC': 'Dikembalikan Finance ke PIC', 'READY_FOR_REVIEW': 'Siap diperiksa Finance',
    'EXCEPTION': 'Perlu perhatian', 'AMIGA_REVIEWED': 'Menunggu manajer keuangan', 'AMIGA_APPROVED': 'Disetujui final',
    'RETURNED': 'Dikembalikan ke Finance',
}
ACTION_LABELS = {
    'UPLOADED': 'Diunggah', 'BATCH_RECEIVED': 'Diterima lewat unggah massal', 'EXTRACTED': 'Dibaca AI',
    'EXTRACTION_FAILED': 'Gagal dibaca AI', 'PROCESS_INTERRUPTED': 'Proses baca terputus', 'DRAFT_EDITED': 'Data dikoreksi',
    'VENDOR_REGISTERED': 'Vendor baru didaftarkan', 'VENDOR_UPDATED': 'Data vendor diperbarui',
    'INTAKE_SUBMITTED': 'Diajukan PIC ke Finance', 'FINANCE_RETURNED': 'Dikembalikan Finance ke PIC',
    'REVIEW_APPROVED': 'Disetujui Finance', 'APPROVAL_INVALIDATED': 'Persetujuan batal karena data berubah',
    'VOUCHER_READY': 'Voucher siap', 'VOUCHER_FAILED': 'Voucher gagal dibuat', 'VOUCHER_RETRY': 'Voucher dibuat ulang',
    'SIGN_FAILED': 'Persetujuan ditolak: password salah', 'DIRECTOR_APPROVED': 'Disetujui manajer keuangan',
    'DIRECTOR_RETURNED': 'Dikembalikan manajer keuangan ke Finance', 'SIGNED_VOUCHER_READY': 'Voucher final tersedia',
    'SIGNED_VOUCHER_FAILED': 'Pembuatan voucher final gagal', 'SIGNED_VOUCHER_RETRY': 'Voucher final dibuat ulang',
    'VOUCHER_SENT': 'Voucher final dikirim ke klien lewat Telegram',
    'VOUCHER_SEND_FAILED': 'Pengiriman voucher ke klien belum berhasil',
}
ROLE_LABELS = {'PIC': 'PIC', 'FINANCE_REVIEWER': 'Finance', 'AMIGA_DIRECTOR': 'Manajer Keuangan'}
# The peran values a SOP card may carry (knowledge-base/tools/bangun_korpus.py PERAN), named as the chat names users.
CARD_ROLES = {'pic-klien': 'PIC', 'finance-reviewer': 'Finance', 'amiga-director': 'Manajer Keuangan',
              'robot-admin': 'Robot Admin', 'intake-support': 'Intake support', 'service-lead': 'Service lead',
              'system-admin': 'Admin sistem'}
# What the asker can do now, per role and stage. The invoice screen still enforces it; this keeps the chat from advising
# a step the asker cannot take (16 Okt 2026: "pilih opsi tanpa PPN" was told to the Manajer Keuangan).
NEXT_STEPS = {
    ('PIC', 'INTAKE'): 'Cocokkan isian dengan dokumen dan koreksi kalau perlu, lalu ajukan ke Finance di layar invoice.',
    ('PIC', 'FINANCE'): 'Tidak ada tindakan untuk PIC. Finance sedang memeriksa invoice ini.',
    ('PIC', 'DIRECTOR'): 'Tidak ada tindakan untuk PIC. Invoice menunggu persetujuan manajer keuangan.',
    ('FINANCE_REVIEWER', 'INTAKE'): 'Tidak ada tindakan untuk Finance. Invoice belum diajukan PIC.',
    ('FINANCE_REVIEWER', 'FINANCE'): ('Periksa invoice dan koreksi kalau perlu, lalu setujui atau kembalikan ke PIC '
                                      'di layar invoice.'),
    ('FINANCE_REVIEWER', 'DIRECTOR'): 'Tidak ada tindakan untuk Finance. Invoice menunggu persetujuan manajer keuangan.',
    ('AMIGA_DIRECTOR', 'FINANCE'): 'Tidak ada tindakan untuk Anda. Finance sedang memeriksa ulang invoice ini.',
    ('AMIGA_DIRECTOR', 'DIRECTOR'): ('Setujui, atau kembalikan ke Finance kalau ada yang perlu dicek ulang. Keduanya '
                                     'di layar invoice.'),
}
FINAL_STEP = 'Selesai. Voucher final sudah tersedia, jadi tidak ada tindakan lagi di AMIGA.'
# The PIC hands the final voucher to the client from Hubungi klien (16 Okt 2026).
PIC_FINAL_STEP = 'Voucher final sudah tersedia. Kirim ke klien lewat menu Hubungi klien kalau belum terkirim.'
# Open checks that never touch the sums, shown next to their label so the chat names them as reminders, not faults.
REMINDERS = {'TAX_FAKTUR_NOT_FOUND': 'pengingat bukti PPN dari faktur pajak, angka invoice tidak terpengaruh'}
# Aldian approved sending return reasons; other audit notes stay home.
RETURN_ACTIONS = {'FINANCE_RETURNED', 'DIRECTOR_RETURNED'}
SORTS = ('relevan', 'terbaru', 'terlama', 'terbesar')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
ISO_DAY = re.compile(r'\d{4}-\d{2}-\d{2}')
DIGITS = re.compile(r'\d{8,}')
WIB = timezone(timedelta(hours=7))
MAX_ROWS = 5000
# Two words count as one spelled differently from this 3-gram Dice up: katering and catering score 0.75, while
# konsumsi and konsultasi score 0.56. A whole-document n-gram score could not tell them apart (0.18 against 0.25).
CLOSE_WORD = 0.6
# Words almost every invoice or question shares. Left in, "jasa desain" also pulls in "jasa konsultasi pajak".
GENERIC_WORDS = frozenset('''invoice invoicenya tagihan faktur jasa biaya pembayaran bayar layanan yang dan atau untuk dari
    ke di apa saja mana ada berapa bulan ini itu tolong cari carikan tampilkan semua dengan serupa mirip sama soal tentang
    yg dong kah nya pt cv'''.split())
NOT_FOUND = 'Invoice tidak ditemukan atau di luar akses Anda.'


def visible_rows(conn, user, ids=None):
    """The queue's rule without its 200-row page, so an old invoice stays findable."""
    params, only = [[c['id'] for c in user['clients']]], ''
    if ids is not None:
        ids = [i.lower() for i in ids if isinstance(i, str) and UUID.fullmatch(i.lower())]
        if not ids:
            return []
        params, only = params + [ids], ' AND r.id=ANY(%s::uuid[])'
    signing = (" AND r.status IN ('AMIGA_REVIEWED','AMIGA_APPROVED','RETURNED')"
               if user['role'] == 'AMIGA_DIRECTOR' else '')
    return conn.execute('SELECT r.id,r.client_id,c.name AS client_name,r.status,r.current_version,r.submitted_at,'
                        "r.created_at,v.snapshot->'invoice' AS invoice,v.snapshot->'tax' AS tax,"
                        "v.snapshot->'validation' AS validation,"
                        "(r.submitted_at IS NULL AND EXISTS(SELECT 1 FROM audit_events a WHERE a.request_id=r.id "
                        "AND a.action='FINANCE_RETURNED')) AS returned_to_pic "
                        'FROM requests r JOIN clients c ON c.id=r.client_id LEFT JOIN invoice_versions v '
                        'ON v.request_id=r.id AND v.version=r.current_version WHERE r.client_id=ANY(%s)' + signing + only +
                        f' ORDER BY r.created_at DESC LIMIT {MAX_ROWS}', params).fetchall()


def clean(value, limit=200, mask=True):
    """Untrusted document text: one line, clipped, and digit runs of 8 or more masked, since they may be accounts."""
    if not isinstance(value, str):
        return None
    text = ' '.join(value.split())
    if mask:
        text = DIGITS.sub('[angka disamarkan]', text)
    return (text[:limit] + '…' if len(text) > limit else text) or None


def amount(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if value is not None and number.is_finite() else None


def money(value, currency=None):
    """Indonesian notation, computed here so the model never adds or formats numbers itself."""
    number = amount(value)
    if number is None:
        return None
    text = f'{number:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    text = text[:-3] if text.endswith(',00') else text
    return ('Rp ' if (currency or 'IDR') == 'IDR' else f'{currency} ') + text


def shown_status(row, issue_count):
    """The queue's status as app.js shownStatus derives it, plus the return to the PIC that the queue flags apart."""
    if row['returned_to_pic']:
        return 'RETURNED_TO_PIC'
    where = stage(row['status'], row['submitted_at'])
    if where == 'INTAKE' and row['current_version'] > 0:
        return 'INTAKE'
    if where == 'FINANCE' and row['status'] == 'EXCEPTION' and not issue_count:
        return 'READY_FOR_REVIEW'
    return row['status']


def invoice_card(row):
    """The allowlisted view of one invoice: what the model reads, and what the widget shows as a card."""
    invoice = row['invoice'] or {}
    summary = queue_summary({'tax': row['tax'], 'validation': row['validation']}, row['status'])
    status = shown_status(row, summary['issue_count'])
    items = [text for text in (clean(item.get('description'), 160) for item in invoice.get('line_items') or []) if text]
    return {'id': str(row['id']), 'nomor': clean(invoice.get('invoice_number'), 60, mask=False),
            'vendor': clean(invoice.get('vendor_name'), 120), 'klien': row['client_name'],
            'tanggal': clean(invoice.get('invoice_date'), 10, mask=False),
            'jatuh_tempo': clean(invoice.get('due_date'), 10, mask=False),
            'total_teks': money(invoice.get('stated_total'), invoice.get('currency')),
            'status': status, 'status_label': STATUS_LABELS.get(status, status),
            'item': items[:5], 'jumlah_item': len(items), 'diunggah': row['created_at'].astimezone(WIB).date().isoformat()}


def doc_text(card):
    return ' '.join(filter(None, [card['vendor'], card['nomor'], card['klien'], *card['item'], card['status_label']]))


def day_of(card):
    return card['tanggal'] if card['tanggal'] and ISO_DAY.fullmatch(card['tanggal']) else card['diunggah']


def topic_words(text):
    return [word for word in re.findall(r'\w+', text.casefold())
            if word not in GENERIC_WORDS and len(word) >= 2 and not word.isdigit()][:12]


def topic(text):
    return ' '.join(topic_words(text)) or text


def trigrams(word):
    padded = f' {word} '
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def mentions(text, words_in_text, word):
    """The word itself, inside a longer one (desainnya), or the same word spelled another way (catering)."""
    if len(word) < 4:
        return word in words_in_text
    grams = trigrams(word)
    return word in text or any(2 * len(grams & trigrams(other)) / (len(grams) + len(trigrams(other))) >= CLOSE_WORD
                               for other in words_in_text if len(other) >= 4)


def topic_match(texts, words):
    """Per word, because the model sends a topic with its synonyms: one text score lets an invoice matching three of
    them bury one matching a single synonym. A document is found when it mentions a query word, and ranked by the
    sum of its per-word n-gram scores."""
    docs, rag = [{'teks': text} for text in texts], rag_module()
    per_doc = list(zip(*[rag.skor_kata(docs, word) for word in words]))
    found = []
    for text in texts:
        lowered = text.casefold()
        in_text = set(re.findall(r'\w+', lowered))
        found.append(any(mentions(lowered, in_text, word) for word in words))
    return found, [sum(scores) for scores in per_doc]


def search_invoices(conn, user, kata_kunci=None, vendor=None, klien=None, status=None, dari_tanggal=None,
                    sampai_tanggal=None, nominal_min=None, nominal_maks=None, urutan='relevan', batas=8):
    """Topic search plus filters over every invoice the user may see. Counts and totals cover all matches."""
    pairs = [(row, invoice_card(row)) for row in visible_rows(conn, user)]
    low = amount(nominal_min) if nominal_min is not None else None
    high = amount(nominal_maks) if nominal_maks is not None else None

    def keep(row, card):
        total = amount((row['invoice'] or {}).get('stated_total'))
        return ((not vendor or vendor.casefold() in (card['vendor'] or '').casefold())
                and (not klien or klien.casefold() in card['klien'].casefold())
                and (status not in STATUS_LABELS or card['status'] == status)
                and (not dari_tanggal or not ISO_DAY.fullmatch(dari_tanggal) or day_of(card) >= dari_tanggal)
                and (not sampai_tanggal or not ISO_DAY.fullmatch(sampai_tanggal) or day_of(card) <= sampai_tanggal)
                and (low is None or (total is not None and total >= low))
                and (high is None or (total is not None and total <= high)))

    pairs = [pair for pair in pairs if keep(*pair)]
    ranked, words = [(0.0, pair) for pair in pairs], topic_words(kata_kunci or '')
    if words and pairs:
        found, rank = topic_match([doc_text(card) for _, card in pairs], words)
        ranked = [(score, pair) for hit, score, pair in zip(found, rank, pairs) if hit]
    if urutan not in SORTS or (urutan == 'relevan' and not words):
        urutan = 'terbaru'
    if urutan == 'relevan':
        ranked.sort(key=lambda entry: -entry[0])
    elif urutan == 'terbesar':
        ranked.sort(key=lambda entry: -(amount((entry[1][0]['invoice'] or {}).get('stated_total')) or Decimal(-1)))
    else:
        ranked.sort(key=lambda entry: day_of(entry[1][1]), reverse=urutan == 'terbaru')
    totals = {}
    for _, (row, _card) in ranked:
        invoice = row['invoice'] or {}
        value = amount(invoice.get('stated_total'))
        if value is not None:
            totals[invoice.get('currency') or 'IDR'] = totals.get(invoice.get('currency') or 'IDR', Decimal(0)) + value
    limit = min(max(int(batas or 8), 1), 10)
    result = {'jumlah_cocok': len(ranked), 'total_semua': [money(value, code) for code, value in totals.items()],
              'hasil': [card | ({'skor': round(score, 3)} if score else {}) for score, (_, card) in ranked[:limit]]}
    # A filter the user never meant ("kemarin" read as yesterday) can hide the answer. The model was told to retry
    # looser and still did not, so the empty result carries the topic matches without the filters.
    filtered = any(value not in (None, '') for value in (vendor, klien, status, dari_tanggal, sampai_tanggal,
                                                         nominal_min, nominal_maks))
    if not ranked and words and filtered:
        loose = search_invoices(conn, user, kata_kunci=kata_kunci, batas=5)
        if loose['jumlah_cocok']:
            result['tanpa_filter'] = loose
    return result


def resolve(conn, user, reference):
    """The model sometimes passes the invoice number where an id belongs. An id passes through; a number resolves to
    the single visible invoice that carries it, and anything else stays unresolved."""
    if isinstance(reference, str) and UUID.fullmatch(reference.strip().lower()):
        return reference.strip().lower()
    wanted = ' '.join(str(reference or '').split()).casefold()
    matches = [row for row in visible_rows(conn, user) if wanted
               and ' '.join(str((row['invoice'] or {}).get('invoice_number') or '').split()).casefold() == wanted]
    return str(matches[0]['id']) if len(matches) == 1 else None


def similar_invoices(conn, user, invoice_id, batas=5):
    """Invoices whose items read like this one; the vendor name only when the source has no items, since a shared word
    such as "Nusantara" in two vendor names says nothing about the work. Only visible invoices take part."""
    pairs, wanted = [invoice_card(row) for row in visible_rows(conn, user)], resolve(conn, user, invoice_id)
    source = next((card for card in pairs if card['id'] == wanted), None)
    if not source:
        return {'galat': NOT_FOUND}
    others = [card for card in pairs if card['id'] != source['id']]
    if not others:
        return {'acuan': source, 'jumlah_cocok': 0, 'hasil': []}
    words = topic_words(' '.join(source['item'])) or topic_words(source['vendor'] or '')
    if not words:
        return {'acuan': source, 'jumlah_cocok': 0, 'hasil': []}
    found, rank = topic_match([doc_text(card) for card in others], words)
    ranked = sorted(((score, card) for hit, score, card in zip(found, rank, others) if hit), key=lambda e: -e[0])
    limit = min(max(int(batas or 5), 1), 10)
    return {'acuan': source, 'jumlah_cocok': len(ranked),
            'hasil': [card | {'skor': round(score, 3)} for score, card in ranked[:limit]]}


def sop_labels():
    cards, _ = rag_module().muat_kartu()
    return {card['kode']: card_label(card) for card in cards if card['kode']}


def product(item):
    quantity, price = amount(item.get('quantity')), amount(item.get('unit_price'))
    return quantity * price if quantity is not None and price is not None else None


def reckon(invoice):
    """The invoice's own sums, worked out here because the model never adds: subtotal, discount, other charges and PPN
    against the total, and the lines against the subtotal. A price that already holds the PPN is named, so the chat does
    not call a consistent invoice wrong (SIPLah laptop, 16 Okt 2026). Also returns, per open check the sums prove
    harmless, the reason to show next to its label."""
    def rp(value):
        return money(value, invoice.get('currency'))

    subtotal, total = amount(invoice.get('stated_subtotal')), amount(invoice.get('stated_total'))
    discount, other, tax = (amount(invoice.get(key)) for key in
                            ('stated_discount_total', 'stated_other_charges_total', 'stated_tax_total'))
    items = invoice.get('line_items') or []
    lines, products = [amount(item.get('stated_line_total')) for item in items], [product(item) for item in items]
    line_sum = sum(lines, Decimal(0)) if items and None not in lines else None
    notes, reasons, matches = [], {}, None
    if subtotal is not None and total is not None:
        calculated = subtotal - (discount or 0) + (other or 0) + (tax or 0)
        words = [f'Subtotal {rp(subtotal)}', *([f'dikurangi diskon {rp(discount)}'] if discount else []),
                 *([f'ditambah biaya lain {rp(other)}'] if other else []), *([f'ditambah PPN {rp(tax)}'] if tax else [])]
        sums = ' '.join(words) + (f' menjadi {rp(calculated)}' if len(words) > 1 else '')
        matches = calculated == total
        notes.append(f'{sums}, sama dengan total tertulis.' if matches
                     else f'{sums}, sedangkan total tertulis {rp(total)}, selisih {rp(abs(total - calculated))}.')
    if invoice.get('stated_discount_total') is None:
        notes.append('Diskon tidak tertulis di invoice' + (', dan totalnya tetap cocok tanpa diskon.' if matches else '.'))
        if matches:
            reasons['INSUFFICIENT_CALCULATION_EVIDENCE'] = 'diskon tidak tertulis, dan totalnya tetap cocok tanpa diskon'
    if line_sum is not None and subtotal is not None:
        if tax and line_sum == subtotal + tax:
            notes.append(f'Jumlah total baris {rp(line_sum)} sudah termasuk PPN, karena sama dengan subtotal ditambah '
                         'PPN. Subtotal tidak perlu diubah.')
            reasons['SUBTOTAL_MISMATCH'] = 'harga di baris sudah termasuk PPN, jadi subtotal tetap benar'
        elif line_sum != subtotal:
            notes.append(f'Jumlah total baris {rp(line_sum)}, sedangkan subtotal tertulis {rp(subtotal)}.')
        elif tax and None not in products and sum(products, Decimal(0)) == subtotal + tax:
            notes.append('Harga satuan tertulis sudah termasuk PPN, sedangkan total baris sudah nilai sebelum PPN.')
            reasons['LINE_TOTAL_MISMATCH'] = 'harga satuan tertulis sudah termasuk PPN, jadi total baris tetap benar'
    return {'total_cocok': matches, 'catatan': notes}, reasons


def arithmetic(invoice):
    return reckon(invoice)[0]


def next_step(user, row):
    where = stage(row['status'], row['submitted_at'])
    if where == 'FINAL':
        return PIC_FINAL_STEP if user['role'] == 'PIC' else FINAL_STEP
    if user['role'] == 'PIC' and where == 'INTAKE' and row['status'] in ('QUEUED', 'PROCESSING'):
        return 'Tunggu AI selesai membaca dokumen.'
    if user['role'] == 'PIC' and row['returned_to_pic']:
        return 'Baca alasan Finance di riwayat, koreksi isiannya, lalu ajukan lagi ke Finance.'
    return NEXT_STEPS.get((user['role'], where), 'Tidak ada tindakan yang menunggu Anda di invoice ini.')


def who(event):
    return f"{event['name']} ({event['title'] or ROLE_LABELS.get(event['role'], event['role'])})"


def finance_decision(row, events, describe):
    """Finance's approval that the director decides on: who, when, and which checks Finance let stand. Finance's note
    stays home, since only return reasons may leave (15 Okt 2026)."""
    approvals = [event for event in events if event['action'] == 'REVIEW_APPROVED']
    if row['status'] not in ('AMIGA_REVIEWED', 'AMIGA_APPROVED') or not approvals:
        return None
    event, codes = approvals[-1], []
    # Older approvals stored the open checks as bare codes, later ones as {code, field}.
    for entry in (event['changes'] or {}).get('open_checks') or []:
        code = entry.get('code') if isinstance(entry, dict) else entry
        if isinstance(code, str) and code not in codes:
            codes.append(code)
    return {'oleh': who(event), 'waktu': event['created_at'].astimezone(WIB).strftime('%Y-%m-%d %H:%M WIB'),
            'catatan_terbuka': [describe(code) for code in codes]}


def invoice_detail(conn, user, invoice_id):
    """One invoice with its items, its sums, open checks, Finance's decision, the asker's next step and the trail."""
    wanted = resolve(conn, user, invoice_id)
    rows = visible_rows(conn, user, [wanted]) if wanted else []
    if not rows:
        return {'galat': NOT_FOUND}
    row, labels = rows[0], sop_labels()
    invoice = row['invoice'] or {}
    currency = invoice.get('currency')
    summary = queue_summary({'tax': row['tax'], 'validation': row['validation']}, row['status'])
    events = conn.execute('SELECT a.action,a.reason,a.changes,a.created_at,u.name,u.role,u.title FROM audit_events a '
                          'JOIN users u ON u.id=a.actor_id WHERE a.request_id=%s ORDER BY a.created_at,a.id',
                          (row['id'],)).fetchall()
    trail = [{'waktu': event['created_at'].astimezone(WIB).strftime('%Y-%m-%d %H:%M WIB'),
              'aksi': ACTION_LABELS.get(event['action'], event['action'].replace('_', ' ').lower()),
              'oleh': who(event)}
             | ({'alasan': clean(event['reason'], 300)} if event['action'] in RETURN_ACTIONS else {})
             for event in events]
    checked, reasons = reckon(invoice)
    reasons = REMINDERS | reasons

    def describe(code):
        label = labels.get(code, code.replace('_', ' ').lower())
        return f'{label}: {reasons[code]}' if code in reasons else label

    decision = finance_decision(row, events, describe)
    return invoice_card(row) | {
        'item': [{'deskripsi': clean(item.get('description'), 160), 'total_teks': money(item.get('stated_line_total'), currency)}
                 for item in (invoice.get('line_items') or [])[:20]],
        'subtotal_teks': money(invoice.get('stated_subtotal'), currency),
        'diskon_teks': money(invoice.get('stated_discount_total'), currency),
        'pajak_teks': money(invoice.get('stated_tax_total'), currency),
        'nilai_bayar_teks': money(summary['net_payable'], currency),
        'cek_angka': checked,
        'kendala_terbuka': [describe(code) for code in summary['issue_codes']],
        **({'keputusan_finance': decision} if decision else {}),
        'langkah_anda': next_step(user, row),
        'riwayat': trail[-15:]}


def sop_view(card):
    roles = [role.strip() for role in (card.get('peran') or '').split(',') if role.strip()]
    return {'sop_id': card['sop_id'], 'judul': card_label(card), 'peran': [CARD_ROLES.get(role, role) for role in roles],
            'teks': card['teks'][:2000]}


def search_sop(question, limit=3):
    """The nearest cards by the same local word score as the SOP panel's fallback; no Titan call, so no throttling."""
    rag = rag_module()
    cards, _ = rag.muat_kartu()
    by_id = {card['sop_id']: card for card in cards}
    return {'kartu': [sop_view(by_id[ref['sop_id']]) for ref in nearest_cards(rag, question, limit)]}


def sop_card(kode):
    cards, _ = rag_module().muat_kartu()
    found = next((card for card in cards if card['kode'] == kode), None)
    return {'kartu': [sop_view(found)]} if found else {'galat': 'Kartu SOP untuk kode ini belum ada.'}
