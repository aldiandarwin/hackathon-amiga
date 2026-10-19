"""Deterministic PoC tax arithmetic: a human picks the tax, code computes it, Finance confirms the rates."""

from decimal import Decimal, ROUND_HALF_UP, localcontext
import re

from . import settings  # noqa: F401  adds prototype/ to sys.path for amiga_ocr
from amiga_ocr.contracts import decimal_value
from amiga_ocr.validation import check

RULES_VERSION = 'pajak-poc.v2'
VERIFIED_ON = '2026-10-14'
STATUS_NOTE = 'Asumsi PoC; tarif dan pembulatan menunggu konfirmasi Finance.'
PASAL_17 = ((Decimal('60000000'), Decimal('0.05')), (Decimal('250000000'), Decimal('0.15')),
            (Decimal('500000000'), Decimal('0.25')), (Decimal('5000000000'), Decimal('0.30')), (None, Decimal('0.35')))
PPH = {
    'TANPA': {'label': 'Tanpa potongan PPh', 'short': 'Tanpa PPh', 'method': 'none', 'rate_text': '0%',
              'basis': 'Pernyataan pengguna', 'ref_ids': ('PJK-ASUMSI-POC',), 'source': None},
    'PPH21': {'label': 'PPh 21 bukan pegawai', 'short': 'PPh 21', 'method': 'pasal17',
              'dpp_ratio': Decimal('0.5'), 'no_npwp': Decimal('1.2'), 'no_npwp_basis': 'UU PPh Pasal 21 ayat (5a)',
              'rate_text': '50% bruto x tarif Pasal 17 (5% sampai 35%)', 'basis': 'PMK 168/2023',
              'ref_ids': ('PJK-PPH21-BUKAN-PEGAWAI', 'PJK-TARIF-PASAL-17'),
              'source': {'label': 'PMK 168/2023', 'url': 'https://jdih.kemenkeu.go.id/dok/pmk-168-tahun-2023'}},
    'PPH23': {'label': 'PPh 23 jasa atau sewa harta selain tanah/bangunan', 'short': 'PPh 23', 'method': 'flat',
              'rate': Decimal('0.02'), 'no_npwp': Decimal('2'), 'no_npwp_basis': 'UU PPh Pasal 23 ayat (1a)',
              'rate_text': '2% bruto, 4% tanpa NPWP',
              'basis': 'UU PPh Pasal 23', 'ref_ids': ('PJK-PPH23-JASA-SEWA-HARTA',),
              'source': {'label': 'UU PPh Pasal 23 (DJP)', 'url': 'https://www.pajak.go.id/id/pph-pasal-2326'}},
    'PPH4_2_SEWA': {'label': 'PPh 4(2) final sewa tanah/bangunan', 'short': 'PPh 4(2)', 'method': 'flat',
                    'rate': Decimal('0.10'), 'no_npwp': Decimal('1'), 'rate_text': '10% bruto, final',
                    'basis': 'UU PPh Pasal 4 ayat (2)', 'ref_ids': ('PJK-PPH4-2-SEWA-TANAH-BANGUNAN',),
                    'source': {'label': 'PP 34/2017', 'url': 'https://jdih.kemenkeu.go.id/download/'
                               'c9be149c-4489-4d9e-b1f6-912808e416c4/34TAHUN2017PP.pdf'}},
}
PPN = {'label': 'PPN 12% x DPP nilai lain 11/12 (efektif 11%)', 'rate': Decimal('0.12'),
       'basis': 'PMK 131/2024', 'ref_ids': ('PJK-PPN-DPP-NILAI-LAIN',),
       'source': {'label': 'PMK 131/2024', 'url': 'https://jdih.kemenkeu.go.id/dok/pmk-131-tahun-2024'}}
# Official sources checked 14 Okt 2026; the panel links them so a reviewer can verify a rate in one click.
ROUNDING_SOURCE = {'label': 'PER-11/PJ/2025 Pasal 129',
                   'url': 'https://www.pajak.go.id/sites/default/files/lampiran/PER-11_PJ_2025_0.pdf'}
COMMON_REFS = ('PJK-PEMBULATAN', 'PJK-ASUMSI-POC')
SAMPLE_SELECTION = {'pph': 'TANPA', 'ppn': False, 'recipient_has_npwp': True, 'faktur_number': None}
# One dropdown for the demo (Aldian, 14 Okt). PRESET_PPH follows the AMIGA real case; old ids stay valid for saved drafts.
PRESET_PPH = 'PPH23'
PRESETS = ({'id': 'TANPA_PAJAK', 'label': 'Tanpa pajak', 'pph': 'TANPA', 'ppn': False},
           {'id': 'PPN', 'label': 'PPN 11% saja', 'pph': 'TANPA', 'ppn': True},
           {'id': 'PPH', 'label': 'PPh 23 2% saja', 'pph': PRESET_PPH, 'ppn': False},
           {'id': 'PPN_PPH', 'label': 'PPN 11% + PPh 23 2%', 'pph': PRESET_PPH, 'ppn': True})
BLOCK_KEYS = ('rules_version', 'status', 'pph_id', 'pph_label', 'pph_short', 'currency', 'gross_total',
              'ppn_applied', 'ppn_amount', 'ppn_declared_zero', 'ppn_expected', 'dpp', 'pph_base',
              'withheld_total', 'net_payable', 'steps', 'assumptions', 'warnings', 'basis', 'ref_ids',
              'faktur_number', 'faktur_source', 'invoice_total', 'ppn_origin', 'ppn_adjustment_amount',
              'adjustment_reason', 'vendor_reminder')
# Same digit rule as TaxSelection: a faktur number outside 13 to 17 digits counts as unread, never as half right.
FAKTUR_DIGITS = re.compile(r'\d{13,17}')
RENT = re.compile(r'\bsewa\b', re.I)
RENT_PROPERTY = re.compile(r'\bsewa\b.*\b(kantor|gedung|gudang|ruang|ruko|rumah|apartemen|toko|kios|studio|tanah|lahan|bangunan'
                           r'|co-?working|serviced office)\b', re.I)
SERVICE_CHARGE = re.compile(r'\bservice charge\b', re.I)
CONSTRUCTION = re.compile(r'\b(renovasi|konstruksi|pengecatan|pekerjaan sipil)\b', re.I)
LICENSE = re.compile(r'\b(lisensi|license|royalti|royalty|hak cipta|waralaba|franchise)\b', re.I)
GOODS = re.compile(r'^\s*(pembelian|pengadaan)\b', re.I)
NOT_GOODS = re.compile(r'\b(jasa|sewa|pemasangan|instalasi)\b', re.I)
SERVICE = re.compile(r'\b(jasa|layanan|konsultan\w*|pemeliharaan|perbaikan|servis|maintenance|kebersihan|cleaning|keamanan)\b',
                     re.I)
PRINTED_PPH = re.compile(r'\bpph\b|\bpotongan pajak\b', re.I)
COMPANY = re.compile(r'^\s*(pt|cv)\b', re.I)


def rp(value):
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def money(value):
    with localcontext() as context:
        context.prec = 60
        return format(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'f')


def pasal17(base):
    tax, lower = Decimal(0), Decimal(0)
    for upper, rate in PASAL_17:
        top = base if upper is None else min(base, upper)
        if top > lower:
            tax += (top - lower) * rate
        if upper is None or base <= upper:
            break
        lower = upper
    return tax


def withhold(rule, dpp, multiplier):
    if rule['method'] == 'pasal17':
        base = rp(dpp * rule['dpp_ratio'])
        return base, rp(pasal17(base) * multiplier)
    if rule['method'] == 'flat':
        return dpp, rp(dpp * rule['rate'] * multiplier)
    return dpp, Decimal(0)


def normalize_selection(raw):
    if raw is None:
        return None
    if raw.get('pph') not in PPH:
        raise ValueError('Jenis potongan PPh tidak dikenal.')
    ppn = raw.get('ppn') is True
    faktur = (raw.get('faktur_number') or '').strip() or None
    result = {'pph': raw['pph'], 'ppn': ppn, 'recipient_has_npwp': raw.get('recipient_has_npwp', True) is not False,
              'faktur_number': faktur if ppn else None}
    adjustment = raw.get('ppn_adjustment', 'NONE')
    if adjustment not in ('NONE', 'ADD_ON'):
        raise ValueError('Perlakuan penyesuaian PPN tidak dikenal.')
    if adjustment == 'ADD_ON':
        reason = (raw.get('ppn_adjustment_reason') or '').strip()
        if not ppn or not 5 <= len(reason) <= 500:
            raise ValueError('Tambahan PPN memerlukan pilihan PPN dan alasan minimal 5 karakter.')
        result.update(ppn_adjustment=adjustment, ppn_adjustment_reason=reason)
    return result


def declared_zero(invoice, selection):
    if selection and not selection['ppn'] and invoice['stated_tax_total'] is None:
        return frozenset({'stated_tax_total'})
    return frozenset()


def hints(invoice, selection):
    """Advisory and per line: a keyword never picks the tax, it only asks a human to look again."""
    lines = [item['description'] or '' for item in invoice['line_items']]

    def seen(pattern):
        return any(pattern.search(line) for line in lines)

    vendor, pph, found = invoice['vendor_name'] or '', selection['pph'], []
    if pph == 'PPH21' and COMPANY.search(vendor):
        found.append('PPh 21 untuk orang pribadi; nama vendor tampak badan usaha.')
    if pph == 'PPH23' and seen(RENT_PROPERTY):
        found.append('Sewa tanah/bangunan biasanya PPh 4(2) final 10%, bukan PPh 23.')
    elif pph == 'PPH23' and seen(SERVICE_CHARGE):
        found.append('Service charge gedung ikut dasar PPh 4(2) sewa 10% (PP 34/2017), bukan PPh 23.')
    if pph == 'PPH21' and seen(RENT):
        found.append('Sewa biasanya PPh 4(2) atau PPh 23, bukan PPh 21.')
    if pph == 'PPH4_2_SEWA' and not seen(RENT):
        found.append('PPh 4(2) di tabel ini khusus sewa tanah/bangunan; baris invoice tidak menyebut sewa.')
    if pph == 'PPH23' and seen(LICENSE):
        found.append('Lisensi atau hak pakai bisa royalti PPh 23 15%, bukan jasa 2%; hitung manual.')
    if seen(CONSTRUCTION):
        found.append('Jasa konstruksi atau renovasi kena PPh 4(2) final 1,75% sampai 6% sesuai SBU/SKK (PP 9/2022); '
                     'belum dihitung sistem.')
    if pph in ('PPH21', 'PPH23') and lines and all(GOODS.search(line) and not NOT_GOODS.search(line) for line in lines):
        found.append('Pembelian barang bukan objek PPh 21/23; PPh 22 hanya bila klien ditetapkan pemungut (PMK 51/2025).')
    if pph == 'TANPA' and (seen(SERVICE) or seen(RENT)):
        found.append('Baris menyebut jasa atau sewa; biasanya ada potongan PPh. Periksa pilihan pajak.')
    if pph != 'TANPA' and seen(PRINTED_PPH):
        found.append('Invoice memuat baris PPh; pastikan potongan tidak dihitung dua kali.')
    return found


def identity_checks(invoice, selection, block):
    """Faktur and NPWP read from the document (schema v2). Fills the faktur fields of the block."""
    found = []
    if selection['ppn']:
        typed, read = selection.get('faktur_number'), invoice.get('faktur_number')
        # A number Finance typed in review wins over the one read from the document; both stay in history.
        faktur, source = (typed, 'REVIEWER') if typed else (read, 'DOKUMEN')
        if faktur and FAKTUR_DIGITS.fullmatch(re.sub(r'\D', '', faktur)):
            block.update(faktur_number=faktur, faktur_source=source)
        else:
            found.append(check('TAX_FAKTUR_NOT_FOUND', 'FAILED',
                               'Nomor faktur pajak tidak terbaca dengan format yang sah; isi dari faktur aslinya.'
                               if faktur else 'PPN dipilih, tetapi nomor faktur pajak tidak ada di dokumen.',
                               field='faktur_number'))
    # Snapshots made before schema v2 never asked the document for an NPWP, so silence is not a finding there.
    if 'vendor_npwp' in invoice and selection['pph'] != 'TANPA' and selection['recipient_has_npwp']:
        npwp = invoice['vendor_npwp']
        # Messages stay on one source line: SOP cards quote them and bangun_korpus.py matches the raw source.
        if not npwp:
            message = 'NPWP vendor tidak terlihat di dokumen. Pastikan vendor punya NPWP sebelum potongan PPh dihitung.'
            found.append(check('NPWP_CHECK', 'NOT_CHECKED', message, field='vendor_npwp', blocking=False))
        elif len(re.sub(r'\D', '', npwp)) not in (15, 16):
            message = 'NPWP vendor terbaca, tetapi jumlah digitnya bukan 15 atau 16. Cocokkan dengan dokumen.'
            found.append(check('NPWP_CHECK', 'FAILED', message, field='vendor_npwp', blocking=False))
    return found


def compute(invoice, selection):
    """Tax block plus checks. Numbers come only from the invoice and this table, never from a model."""
    block = dict.fromkeys(BLOCK_KEYS) | {'rules_version': RULES_VERSION, 'steps': [], 'assumptions': [STATUS_NOTE],
                                          'warnings': [], 'ref_ids': list(COMMON_REFS)}
    if selection is None:
        return block | {'status': 'NOT_SELECTED'}, [check('TAX_SELECTION_REQUIRED', 'NOT_CHECKED',
            'Jenis potongan pajak belum dipilih; approval ditahan sampai Finance memilih.', blocking=False)]
    block, checks = _compute(invoice, selection, block)
    return block, checks + identity_checks(invoice, selection, block)


def _compute(invoice, selection, block):
    rule = PPH[selection['pph']]
    block.update(status='NOT_COMPUTED', pph_id=selection['pph'], pph_label=rule['label'], pph_short=rule['short'],
                 currency=invoice['currency'], ppn_applied=selection['ppn'],
                 basis=rule['basis'] + (' + ' + PPN['basis'] if selection['ppn'] else ''),
                 ref_ids=list(dict.fromkeys(rule['ref_ids'] + (PPN['ref_ids'] if selection['ppn'] else ()) + COMMON_REFS)),
                 warnings=hints(invoice, selection))
    stated_tax, checks = invoice['stated_tax_total'], []
    add_on = selection.get('ppn_adjustment') == 'ADD_ON'
    if add_on and (not selection['ppn'] or (stated_tax is not None and decimal_value(stated_tax) != 0)
                   or len((selection.get('ppn_adjustment_reason') or '').strip()) < 5):
        return block, [check('TAX_ADJUSTMENT_INVALID', 'FAILED',
            'Tambahan PPN hanya untuk invoice tanpa nominal PPN, dengan alasan yang dicatat.', field='stated_tax_total')]
    if selection['ppn'] and (stated_tax is None or decimal_value(stated_tax) <= 0):
        checks.append(check('TAX_PPN_MISSING', 'FAILED', 'PPN dipilih, tetapi nominal pajak invoice kosong atau nol.',
                            field='stated_tax_total'))
    if not selection['ppn'] and stated_tax is not None and decimal_value(stated_tax) != 0:
        checks.append(check('TAX_PPN_CONFLICT', 'FAILED',
                            'Invoice mencantumkan pajak, tetapi pilihan menyatakan tanpa PPN.', field='stated_tax_total'))
    # A PPN conflict is reported, not a stop: Finance decides, and the voucher still needs an amount to pay.
    if invoice['stated_total'] is None or invoice['currency'] != 'IDR':
        return block, checks
    with localcontext() as context:
        context.prec = 60
        invoice_total = gross = decimal_value(invoice['stated_total'])
        ppn = decimal_value(stated_tax) if stated_tax is not None else Decimal(0)
        dpp = gross - ppn
        if dpp <= 0:
            return block, checks
        # PER-11/PJ/2025 Pasal 129: the faktur rounds DPP nilai lain to rupiah first, then the 12% PPN.
        other_base = rp(dpp * 11 / 12) if selection['ppn'] else None
        expected = rp(other_base * PPN['rate']) if selection['ppn'] else None
        if add_on:
            ppn = expected
            gross = invoice_total + ppn
            block.update(rules_version='pajak-poc.v3', ppn_origin='INTERNAL_ADJUSTMENT',
                         ppn_adjustment_amount=money(ppn), adjustment_reason=selection['ppn_adjustment_reason'])
            block['vendor_reminder'] = (
                f"Yth. Tim {invoice.get('vendor_name') or 'Vendor'}, invoice {invoice.get('invoice_number') or '-'} "
                'belum mencantumkan nominal PPN. AMIGA mencatat perhitungan tambahan PPN untuk pemeriksaan internal. '
                'Mohon konfirmasi status PKP dan perlakuan PPN transaksi ini. Apabila PPN terutang, mohon kirimkan '
                'invoice revisi serta faktur pajak yang sesuai. Voucher ini bukan faktur pajak atau bukti pemungutan PPN.')
            block['assumptions'].append('Total invoice diperlakukan sebagai nilai sebelum PPN atas pilihan pengguna; '
                                        'tambahan PPN bukan hasil baca dokumen dan harus dikonfirmasi Finance serta vendor.')
        else:
            block['ppn_origin'] = 'DOCUMENT' if stated_tax is not None else 'USER_DECLARED_ZERO'
            block['ppn_adjustment_amount'] = '0.00'
        if not add_on and expected is not None and expected != ppn:
            checks.append(check('TAX_PPN_DIFFERENT', 'FAILED', 'PPN tertulis berbeda dari hitungan faktur '
                                '(12% x DPP nilai lain 11/12, dibulatkan per langkah); cocokkan dengan faktur pajak.',
                                field='stated_tax_total', blocking=False))
        multiplier = Decimal(1) if selection['recipient_has_npwp'] else rule.get('no_npwp', Decimal(1))
        base, withheld = withhold(rule, dpp, multiplier)
        net = gross - withheld
        # Some vendors print the PPh deduction themselves; computing it again would withhold it twice.
        subtotal = invoice.get('stated_subtotal')
        discount = decimal_value(invoice.get('stated_discount_total') or '0')
        other = decimal_value(invoice.get('stated_other_charges_total') or '0')
        if withheld > 1 and subtotal is not None:
            before = decimal_value(subtotal) - discount + other
            if abs(before + ppn - gross - withhold(rule, before, multiplier)[1]) <= 1:
                block['warnings'].append('Total tercetak tampaknya sudah dipotong PPh; koreksi Total ke nilai '
                                         'sebelum potongan agar PPh tidak terpotong dua kali.')
            # A real discount also lowers the PPN; a PPh printed as discount leaves PPN on the full subtotal.
            if (discount and selection['ppn'] and expected != ppn
                    and abs(discount - withhold(rule, decimal_value(subtotal), multiplier)[1]) <= 1):
                block['warnings'].append('Diskon sama dengan potongan PPh atas subtotal; bila itu PPh tercetak, '
                                         'ubah Diskon ke 0 dan Total ke nilai sebelum potongan.')
    if stated_tax is None and not add_on:
        block['assumptions'].append('Nominal pajak kosong dihitung 0 karena pilihan tanpa PPN, bukan hasil baca dokumen.'
                                    if not selection['ppn'] else
                                    'PPN dipilih, tetapi PPN tertulis kosong. Dihitung 0 sampai Finance mengisinya.')
    if multiplier != 1:
        block['assumptions'].append(f"Penerima tanpa NPWP/NIK: tarif dikali {multiplier} ({rule['no_npwp_basis']}).")
    steps = ([('Total invoice sumber', invoice_total), ('PPN tambahan (perhitungan internal)', ppn),
              ('Total tagihan setelah penyesuaian', gross), ('Nilai sebelum PPN', dpp)] if add_on else
             [('Total invoice', gross), ('PPN tertulis di invoice', ppn), ('Nilai sebelum PPN', dpp)])
    if selection['ppn']:
        steps += [('DPP nilai lain PPN (11/12)', other_base), ('PPN menurut faktur (12% x DPP nilai lain)', expected)]
    if rule['method'] == 'pasal17':
        steps.append(('Dasar PPh 21 (50% nilai sebelum PPN)', base))
    steps += [(f"Potongan {rule['short']}", withheld), ('Jumlah dibayarkan', net)]
    block.update(status='COMPUTED', invoice_total=money(invoice_total), gross_total=money(gross), ppn_amount=money(ppn),
                 ppn_declared_zero=stated_tax is None and not add_on,
                 ppn_expected=money(expected) if expected is not None else None, dpp=money(dpp), pph_base=money(base),
                 withheld_total=money(withheld), net_payable=money(net),
                 steps=[{'label': label, 'value': money(value)} for label, value in steps])
    return block, checks


def selection_changes(before, after):
    old, new = before or {}, after or {}
    return {f'tax_selection.{key}': {'before': old.get(key), 'after': new.get(key)}
            for key in ('pph', 'ppn', 'recipient_has_npwp', 'faktur_number', 'ppn_adjustment', 'ppn_adjustment_reason')
            if old.get(key) != new.get(key)}


def options():
    """Dropdown content plus a worked example per option, produced by the same arithmetic."""
    sample = {'stated_total': '2000000.00', 'stated_tax_total': '0.00', 'currency': 'IDR',
              'vendor_name': None, 'line_items': []}
    rows = []
    for pph_id, rule in PPH.items():
        block, _ = compute(sample, {'pph': pph_id, 'ppn': False, 'recipient_has_npwp': True, 'faktur_number': None})
        rows.append({'id': pph_id, 'label': rule['label'], 'short': rule['short'], 'rate_text': rule['rate_text'],
                     'basis': rule['basis'], 'ref_ids': list(rule['ref_ids']), 'source': rule['source'],
                     'example': {'gross': block['gross_total'], 'withheld': block['withheld_total'],
                                 'net': block['net_payable']}})
    return {'rules_version': RULES_VERSION, 'verified_on': VERIFIED_ON, 'status_note': STATUS_NOTE,
            'presets': [dict(preset) for preset in PRESETS], 'pph': rows,
            'ppn': {'label': PPN['label'], 'basis': PPN['basis'], 'ref_ids': list(PPN['ref_ids']), 'source': PPN['source']},
            'rounding_source': ROUNDING_SOURCE}
