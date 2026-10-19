"""Pure tax engine and declared-zero validation tests; no database and no network."""

from copy import deepcopy
from decimal import Decimal
import unittest

from app import settings  # noqa: F401  adds prototype/ to sys.path
from app import taxes
from app.service import inspect_pdf, sample_input
from amiga_ocr.contracts import Context, OCRDocument, OCRPage, Rules, decimal_value
from amiga_ocr.validation import validate_invoice


def invoice(total, tax='0.00', vendor='Budi Santoso', lines=('Jasa konsultan',), currency='IDR'):
    return {'stated_total': total, 'stated_tax_total': tax, 'currency': currency, 'vendor_name': vendor,
            'line_items': [{'line_number': i + 1, 'description': d, 'quantity': None, 'unit_price': None,
                            'stated_line_total': None} for i, d in enumerate(lines)]}


def pick(pph, ppn=False, npwp=True, faktur=None):
    return {'pph': pph, 'ppn': ppn, 'recipient_has_npwp': npwp, 'faktur_number': faktur}


FAKTUR = '0400250012345678'


def sample_case(tax=None):
    pdf, saved = sample_input('normal')
    extraction = {'invoice': deepcopy(saved['invoice']), 'source_evidence': deepcopy(saved['source_evidence'])}
    extraction['invoice']['stated_tax_total'] = tax
    if tax is None:
        extraction['source_evidence'].pop('stated_tax_total', None)
    for entry in extraction['source_evidence'].values():
        if entry:
            entry['document_id'] = 'doc'
    pages = inspect_pdf(pdf)
    document = OCRDocument('doc', 'test', 'none', tuple(OCRPage(i + 1, text, bool(text)) for i, text in enumerate(pages)),
                           len(pages), all(pages), {})
    return extraction, document


def codes(validation):
    return {c['code'] for c in validation['checks']}


class DeclaredZeroValidationTests(unittest.TestCase):
    def run_case(self, **kwargs):
        extraction, document = sample_case()
        return validate_invoice(extraction, document, Context('client_a', 'req', 'pic_a'), Rules(), **kwargs)

    def test_null_tax_stays_unchecked_without_declaration(self):
        validation = self.run_case()
        self.assertIn('INSUFFICIENT_CALCULATION_EVIDENCE', codes(validation))
        self.assertNotIn('TOTAL_MATCH', codes(validation))
        self.assertNotIn('DECLARED_ZERO', codes(validation))

    def test_declared_zero_tax_allows_total_check(self):
        validation = self.run_case(declared_zero=frozenset({'stated_tax_total'}))
        self.assertIn('TOTAL_MATCH', codes(validation))
        self.assertNotIn('INSUFFICIENT_CALCULATION_EVIDENCE', codes(validation))
        zero = [(c['field'], c['status'], c['blocking']) for c in validation['checks'] if c['code'] == 'DECLARED_ZERO']
        self.assertEqual(zero, [('stated_tax_total', 'PASSED', False)])
        self.assertEqual(validation['calculated_total'], '500000.00')

    def test_empty_discount_counts_as_none_only_when_the_total_closes(self):
        # 16 Okt 2026, Aldian: no discount line is the usual case, so it is not missing data when the total closes.
        extraction, document = sample_case(tax='0.00')
        extraction['invoice']['stated_discount_total'] = None
        validation = validate_invoice(extraction, document, Context('client_a', 'req', 'pic_a'), Rules())
        self.assertEqual([c['message'] for c in validation['checks'] if c['code'] == 'TOTAL_MATCH'],
                         ['Total cocok tanpa diskon; invoice tidak mencantumkan diskon.'])
        self.assertNotIn('INSUFFICIENT_CALCULATION_EVIDENCE', codes(validation))
        # A gap could be a discount the reader missed, so the total stays unchecked.
        extraction['invoice']['stated_total'] = '490000.00'
        validation = validate_invoice(extraction, document, Context('client_a', 'req', 'pic_a'), Rules())
        self.assertIn('INSUFFICIENT_CALCULATION_EVIDENCE', codes(validation))
        self.assertFalse({'TOTAL_MATCH', 'TOTAL_MISMATCH'} & codes(validation))

    def test_declared_zero_rejects_other_fields(self):
        with self.assertRaises(ValueError):
            self.run_case(declared_zero=frozenset({'stated_total'}))

    def test_engine_declares_zero_only_for_explicit_no_ppn_and_empty_tax(self):
        self.assertEqual(taxes.declared_zero(invoice('1000.00', tax=None), pick('TANPA')), frozenset({'stated_tax_total'}))
        self.assertEqual(taxes.declared_zero(invoice('1000.00', tax=None), pick('TANPA', ppn=True, faktur=FAKTUR)), frozenset())
        self.assertEqual(taxes.declared_zero(invoice('1000.00'), pick('TANPA')), frozenset())
        self.assertEqual(taxes.declared_zero(invoice('1000.00', tax=None), None), frozenset())


class TaxArithmeticTests(unittest.TestCase):
    # name, invoice kwargs, selection, withheld_total, net_payable
    CASES = [
        ('meeting example', dict(total='2000000.00', tax=None), pick('PPH21'), '50000.00', '1950000.00'),
        ('pph21 without npwp', dict(total='2000000.00'), pick('PPH21', npwp=False), '60000.00', '1940000.00'),
        ('pph21 layer edge', dict(total='120000000.00'), pick('PPH21'), '3000000.00', '117000000.00'),
        ('pph21 one rupiah past edge', dict(total='120000002.00'), pick('PPH21'), '3000000.00', '117000002.00'),
        ('pph21 second layer', dict(total='130000000.00'), pick('PPH21'), '3750000.00', '126250000.00'),
        ('pph21 four layers', dict(total='1200000000.00'), pick('PPH21'), '124000000.00', '1076000000.00'),
        ('pph21 half-up on tax', dict(total='100020.00'), pick('PPH21'), '2501.00', '97519.00'),
        ('pph23 half-up', dict(total='1234525.00'), pick('PPH23'), '24691.00', '1209834.00'),
        ('pph23 without npwp', dict(total='1000000.00'), pick('PPH23', npwp=False), '40000.00', '960000.00'),
        ('pph23 with ppn', dict(total='1110000.00', tax='110000.00'), pick('PPH23', ppn=True, faktur=FAKTUR),
         '20000.00', '1090000.00'),
        ('pph4(2) without npwp has no surcharge', dict(total='5000000.00', lines=('Sewa ruang kantor',)),
         pick('PPH4_2_SEWA', npwp=False), '500000.00', '4500000.00'),
        ('sample default', dict(total='500000.00', vendor='PT Contoh Demo', lines=('Barang contoh A',)),
         taxes.SAMPLE_SELECTION, '0.00', '500000.00'),
        ('decimal total', dict(total='500000.00'), pick('PPH23'), '10000.00', '490000.00'),
        # Worked examples from the team's reference docs (14 Okt), verified against official sources.
        ('doc pph23 + ppn 10 juta', dict(total='11100000.00', tax='1100000.00', lines=('Jasa konsultansi',)),
         pick('PPH23', ppn=True, faktur=FAKTUR), '200000.00', '10900000.00'),
        ('doc sewa gudang 20 juta', dict(total='20000000.00', lines=('Sewa gudang',)), pick('PPH4_2_SEWA'),
         '2000000.00', '18000000.00'),
        ('doc honor 10 juta', dict(total='10000000.00', lines=('Honor tenaga ahli',)), pick('PPH21'),
         '250000.00', '9750000.00'),
    ]

    def test_withheld_and_net_payable(self):
        for name, data, selection, withheld, net in self.CASES:
            with self.subTest(name):
                block, checks = taxes.compute(invoice(**data), selection)
                self.assertEqual(block['status'], 'COMPUTED')
                self.assertEqual((block['withheld_total'], block['net_payable']), (withheld, net))
                self.assertFalse([c for c in checks if c['blocking']])

    def test_meeting_example_shows_its_steps_and_declared_zero(self):
        block, _ = taxes.compute(invoice('2000000.00', tax=None), pick('PPH21'))
        self.assertEqual(block['pph_base'], '1000000.00')
        self.assertTrue(block['ppn_declared_zero'])
        self.assertTrue(any('dihitung 0' in text for text in block['assumptions']))
        self.assertEqual([s['label'] for s in block['steps']],
                         ['Total invoice', 'PPN tertulis di invoice', 'Nilai sebelum PPN',
                          'Dasar PPh 21 (50% nilai sebelum PPN)',
                          'Potongan PPh 21', 'Jumlah dibayarkan'])

    def test_half_up_applies_to_the_pph21_base(self):
        block, _ = taxes.compute(invoice('1001.00'), pick('PPH21'))
        self.assertEqual((block['pph_base'], block['withheld_total']), ('501.00', '25.00'))

    def test_missing_npwp_is_stated_as_an_assumption(self):
        block, _ = taxes.compute(invoice('1000000.00'), pick('PPH23', npwp=False))
        self.assertTrue(any('tanpa NPWP/NIK' in text for text in block['assumptions']))

    def test_missing_npwp_cites_the_law(self):
        block, _ = taxes.compute(invoice('1000000.00'), pick('PPH23', npwp=False))
        self.assertTrue(any('UU PPh Pasal 23 ayat (1a)' in text for text in block['assumptions']))

    def test_ppn_rows_show_the_faktur_arithmetic(self):
        block, _ = taxes.compute(invoice('11100000.00', tax='1100000.00'), pick('PPH23', ppn=True, faktur=FAKTUR))
        steps = {s['label']: s['value'] for s in block['steps']}
        self.assertEqual(steps['DPP nilai lain PPN (11/12)'], '9166667.00')
        self.assertEqual(steps['PPN menurut faktur (12% x DPP nilai lain)'], '1100000.00')

    def test_money_rounds_half_up_at_any_size(self):
        self.assertEqual(taxes.money(Decimal('917.125')), '917.13')
        self.assertEqual(taxes.money(Decimal('1E+30')), '1000000000000000000000000000000.00')

    def test_ppn_matching_two_step_formula_passes_quietly(self):
        block, checks = taxes.compute(invoice('1110000.00', tax='110000.00'), pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual(block['ppn_expected'], '110000.00')
        self.assertEqual(checks, [])

    def test_ppn_from_one_step_rounding_is_a_non_blocking_warning(self):
        """PER-11/PJ/2025 Pasal 129 rounds DPP nilai lain first, so a one-step 11% (110.005) is Rp1 off the faktur (110.004)."""
        block, checks = taxes.compute(invoice('1110046.00', tax='110005.00'), pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual(block['status'], 'COMPUTED')
        self.assertEqual(block['ppn_expected'], '110004.00')
        self.assertEqual([(c['code'], c['blocking']) for c in checks], [('TAX_PPN_DIFFERENT', False)])
        self.assertEqual((block['withheld_total'], block['net_payable']), ('20001.00', '1090045.00'))


class TaxStatusTests(unittest.TestCase):
    def test_no_selection_is_not_selected_and_does_not_block_status(self):
        block, checks = taxes.compute(invoice('1000.00'), None)
        self.assertEqual(block['status'], 'NOT_SELECTED')
        self.assertEqual([(c['code'], c['status'], c['blocking']) for c in checks],
                         [('TAX_SELECTION_REQUIRED', 'NOT_CHECKED', False)])

    # 15 Okt 2026: a PPN conflict is flagged for Finance to decide, and the amounts are computed regardless.
    def test_ppn_selected_without_printed_tax_is_flagged_and_counts_zero(self):
        block, checks = taxes.compute(invoice('1110000.00', tax=None), pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual((block['status'], block['ppn_amount'], block['net_payable']), ('COMPUTED', '0.00', '1087800.00'))
        self.assertEqual([(c['code'], c['blocking']) for c in checks],
                         [('TAX_PPN_MISSING', True), ('TAX_PPN_DIFFERENT', False)])
        self.assertIn('PPN dipilih, tetapi PPN tertulis kosong. Dihitung 0 sampai Finance mengisinya.', block['assumptions'])

    def test_ppn_selected_with_zero_or_negative_printed_tax_is_flagged(self):
        for tax in ('0.00', '-5000.00'):
            with self.subTest(tax=tax):
                block, checks = taxes.compute(invoice('500000.00', tax=tax), pick('PPH23', ppn=True, faktur=FAKTUR))
                self.assertEqual(block['status'], 'COMPUTED')
                self.assertEqual([(c['code'], c['blocking']) for c in checks],
                                 [('TAX_PPN_MISSING', True), ('TAX_PPN_DIFFERENT', False)])

    def test_printed_tax_without_ppn_selection_is_flagged_and_uses_the_printed_ppn(self):
        block, checks = taxes.compute(invoice('555000.00', tax='55000.00'), pick('PPH23'))
        self.assertEqual((block['status'], block['ppn_amount'], block['dpp'], block['withheld_total'], block['net_payable']),
                         ('COMPUTED', '55000.00', '500000.00', '10000.00', '545000.00'))
        self.assertEqual([(c['code'], c['blocking']) for c in checks], [('TAX_PPN_CONFLICT', True)])

    def test_unusable_totals_are_not_computed(self):
        for name, data in [('total null', dict(total=None)), ('usd', dict(total='1000.00', currency='USD')),
                           ('negative', dict(total='-1000.00'))]:
            with self.subTest(name):
                block, checks = taxes.compute(invoice(**data), pick('PPH23'))
                self.assertEqual((block['status'], checks), ('NOT_COMPUTED', []))
                self.assertIsNone(block['withheld_total'])


class TaxHintTests(unittest.TestCase):
    CASES = [
        (dict(vendor='PT Maju'), 'PPH21', 'PPh 21 untuk orang pribadi; nama vendor tampak badan usaha.'),
        (dict(lines=('Sewa gedung',)), 'PPH23', 'Sewa tanah/bangunan biasanya PPh 4(2) final 10%, bukan PPh 23.'),
        (dict(lines=('sewa genset',)), 'PPH21', 'Sewa biasanya PPh 4(2) atau PPh 23, bukan PPh 21.'),
        (dict(lines=('Jasa servis',)), 'PPH4_2_SEWA',
         'PPh 4(2) di tabel ini khusus sewa tanah/bangunan; baris invoice tidak menyebut sewa.'),
        # Keyword taxonomy borrowed from the team's reference docs (14 Okt).
        (dict(lines=('Sewa gudang Cikarang',)), 'PPH23', 'Sewa tanah/bangunan biasanya PPh 4(2) final 10%, bukan PPh 23.'),
        (dict(lines=('Sewa co-working space',)), 'PPH23', 'Sewa tanah/bangunan biasanya PPh 4(2) final 10%, bukan PPh 23.'),
        (dict(lines=('Sewa studio produksi video', 'Sewa lighting')), 'PPH23',
         'Sewa tanah/bangunan biasanya PPh 4(2) final 10%, bukan PPh 23.'),
        (dict(lines=('Service charge Oktober',)), 'PPH23',
         'Service charge gedung ikut dasar PPh 4(2) sewa 10% (PP 34/2017), bukan PPh 23.'),
        (dict(lines=('Lisensi software tahunan',)), 'PPH23',
         'Lisensi atau hak pakai bisa royalti PPh 23 15%, bukan jasa 2%; hitung manual.'),
        (dict(lines=('Renovasi ruang rapat',)), 'PPH23',
         'Jasa konstruksi atau renovasi kena PPh 4(2) final 1,75% sampai 6% sesuai SBU/SKK (PP 9/2022); belum dihitung sistem.'),
        (dict(lines=('Pembelian laptop', 'Pengadaan printer')), 'PPH23',
         'Pembelian barang bukan objek PPh 21/23; PPh 22 hanya bila klien ditetapkan pemungut (PMK 51/2025).'),
        (dict(lines=('Layanan pengarsipan dokumen',)), 'TANPA',
         'Baris menyebut jasa atau sewa; biasanya ada potongan PPh. Periksa pilihan pajak.'),
        (dict(lines=('Jasa konsultan', 'PPh 23 dipotong')), 'PPH23',
         'Invoice memuat baris PPh; pastikan potongan tidak dihitung dua kali.'),
    ]

    def test_object_mismatch_hints(self):
        for data, pph, hint in self.CASES:
            with self.subTest(pph=pph, hint=hint):
                block, _ = taxes.compute(invoice('1000000.00', **data), pick(pph))
                self.assertEqual(block['warnings'], [hint])

    def test_total_printed_after_pph_is_flagged(self):
        # Synthetic twin of a real case: subtotal 4.000.000 + PPN 400.000 - PPh 23 80.000 printed as the total.
        data = invoice('4320000.00', tax='400000.00', lines=('Unit AC',)) | {'stated_subtotal': '4000000.00',
                                                                             'stated_discount_total': '0.00'}
        block, _ = taxes.compute(data, pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual(block['warnings'], ['Total tercetak tampaknya sudah dipotong PPh; koreksi Total ke nilai '
                                             'sebelum potongan agar PPh tidak terpotong dua kali.'])

    def test_pph_printed_as_discount_is_flagged(self):
        data = invoice('4320000.00', tax='400000.00', lines=('Unit AC',)) | {'stated_subtotal': '4000000.00',
                                                                             'stated_discount_total': '80000.00'}
        block, _ = taxes.compute(data, pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual(block['warnings'], ['Diskon sama dengan potongan PPh atas subtotal; bila itu PPh tercetak, '
                                             'ubah Diskon ke 0 dan Total ke nilai sebelum potongan.'])

    def test_genuine_discount_equal_to_the_pph_rate_is_not_flagged(self):
        # 2% early-payment discount on 5.000.000, PPN 539.000 follows the faktur formula on 4.900.000.
        with_ppn = invoice('5439000.00', tax='539000.00', lines=('Jasa konsultan',)) | {'stated_subtotal': '5000000.00',
                                                                                       'stated_discount_total': '100000.00'}
        block, checks = taxes.compute(with_ppn, pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual((block['warnings'], checks), ([], []))
        without_ppn = invoice('4900000.00', lines=('Jasa konsultan',)) | {'stated_subtotal': '5000000.00',
                                                                          'stated_discount_total': '100000.00'}
        block, _ = taxes.compute(without_ppn, pick('PPH23'))
        self.assertEqual(block['warnings'], [])

    def test_gross_total_is_not_flagged_as_net(self):
        data = invoice('4400000.00', tax='400000.00', lines=('Jasa konsultan',)) | {'stated_subtotal': '4000000.00',
                                                                                    'stated_discount_total': '0.00'}
        block, _ = taxes.compute(data, pick('PPH23', ppn=True, faktur=FAKTUR))
        self.assertEqual(block['warnings'], [])

    def test_keywords_do_not_pair_across_lines(self):
        block, _ = taxes.compute(invoice('1000000.00', lines=('Sewa genset', 'Antar ke kantor')), pick('PPH23'))
        self.assertEqual(block['warnings'], [])

    def test_matching_object_has_no_hint(self):
        block, _ = taxes.compute(invoice('1000000.00', lines=('Sewa ruang kantor',)), pick('PPH4_2_SEWA'))
        self.assertEqual(block['warnings'], [])


class TaxContractTests(unittest.TestCase):
    def test_block_has_a_closed_key_set_in_every_status(self):
        for selection, data in [(None, {}), (pick('PPH23', ppn=True, faktur=FAKTUR), dict(tax=None)),
                                (pick('PPH21'), {})]:
            block, _ = taxes.compute(invoice('2000000.00', **data), selection)
            self.assertEqual(set(block), set(taxes.BLOCK_KEYS))

    def test_money_values_are_plain_decimal_strings(self):
        block, _ = taxes.compute(invoice('1110000.00', tax='110000.00'), pick('PPH23', ppn=True, faktur=FAKTUR))
        for key in ('gross_total', 'ppn_amount', 'ppn_expected', 'dpp', 'pph_base', 'withheld_total', 'net_payable'):
            decimal_value(block[key])
        for step in block['steps']:
            decimal_value(step['value'])

    def test_reference_ids_are_listed_once(self):
        for pph_id in taxes.PPH:
            for ppn in (False, True):
                with self.subTest(pph=pph_id, ppn=ppn):
                    block, _ = taxes.compute(invoice('1110000.00', tax='110000.00' if ppn else '0.00'),
                                             pick(pph_id, ppn=ppn, faktur=FAKTUR if ppn else None))
                    self.assertEqual(len(block['ref_ids']), len(set(block['ref_ids'])))

    def test_options_come_from_the_rule_table(self):
        options = taxes.options()
        self.assertEqual(options['rules_version'], 'pajak-poc.v2')
        self.assertEqual([row['id'] for row in options['pph']], ['TANPA', 'PPH21', 'PPH23', 'PPH4_2_SEWA'])
        example = next(row['example'] for row in options['pph'] if row['id'] == 'PPH21')
        self.assertEqual(example, {'gross': '2000000.00', 'withheld': '50000.00', 'net': '1950000.00'})

    def test_sources_are_official_https_links(self):
        rules = taxes.options()
        sources = [row['source'] for row in rules['pph'] if row['source']] + [rules['ppn']['source'], rules['rounding_source']]
        self.assertEqual(len(sources), 5)
        for source in sources:
            self.assertRegex(source['url'], r'^https://(www\.)?(pajak\.go\.id|jdih\.kemenkeu\.go\.id)/')

    def test_presets_offer_no_tax_ppn_pph_and_both(self):
        presets = taxes.options()['presets']
        self.assertEqual([(p['id'], p['pph'], p['ppn']) for p in presets],
                         [('TANPA_PAJAK', 'TANPA', False), ('PPN', 'TANPA', True),
                          ('PPH', 'PPH23', False), ('PPN_PPH', 'PPH23', True)])
        self.assertTrue(all(p['pph'] in taxes.PPH for p in presets))

    def test_normalize_selection(self):
        self.assertIsNone(taxes.normalize_selection(None))
        with self.assertRaises(ValueError):
            taxes.normalize_selection({'pph': 'PPH99', 'ppn': False})
        self.assertEqual(taxes.normalize_selection({'pph': 'PPH23', 'ppn': False, 'recipient_has_npwp': True}),
                         pick('PPH23'))
        self.assertEqual(taxes.normalize_selection(pick('PPH23', faktur='123'))['faktur_number'], None)
        self.assertEqual(taxes.normalize_selection(pick('PPH23', ppn=True, faktur=' 0400 '))['faktur_number'], '0400')

    def test_selection_changes_lists_only_changed_fields(self):
        self.assertEqual(taxes.selection_changes(pick('TANPA'), pick('PPH23')),
                         {'tax_selection.pph': {'before': 'TANPA', 'after': 'PPH23'}})
        self.assertEqual(set(taxes.selection_changes(None, pick('TANPA'))),
                         {'tax_selection.pph', 'tax_selection.ppn', 'tax_selection.recipient_has_npwp'})


if __name__ == '__main__':
    unittest.main()
