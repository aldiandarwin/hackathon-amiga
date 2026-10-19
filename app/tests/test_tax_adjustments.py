"""Unprinted PPN must be an explicit, auditable addition, never an OCR correction."""

from copy import deepcopy
import hashlib
import unittest

from app import taxes
from app.tax_api import TaxSelection
from app.tests import test_tax_flow as flow
from app.tests.test_tax_flow import v4_payload, SIGNOFF, pdf_text
from app.voucher_pdf import render_voucher


def addition(pph='PPH23'):
    return {'pph': pph, 'ppn': True, 'recipient_has_npwp': True, 'faktur_number': None,
            'ppn_adjustment': 'ADD_ON', 'ppn_adjustment_reason': 'Jasa vendor PKP; minta konfirmasi dan faktur revisi.'}


class TaxAdjustmentTests(unittest.TestCase):
    def invoice(self, tax=None):
        return v4_payload()['invoice'] | {'stated_subtotal': '500000.00', 'stated_total': '500000.00',
                                         'stated_tax_total': tax}

    def test_unprinted_ppn_and_pph_reconcile_without_changing_source(self):
        invoice = self.invoice()
        source = deepcopy(invoice)
        tax, checks = taxes.compute(invoice, addition())
        self.assertEqual(invoice, source)
        self.assertEqual((tax['invoice_total'], tax['dpp'], tax['ppn_amount'], tax['gross_total'],
                          tax['withheld_total'], tax['net_payable']),
                         ('500000.00', '500000.00', '55000.00', '555000.00', '10000.00', '545000.00'))
        self.assertEqual(tax['ppn_origin'], 'INTERNAL_ADJUSTMENT')
        self.assertEqual(tax['rules_version'], 'pajak-poc.v3')
        self.assertIn('status PKP', tax['vendor_reminder'])
        self.assertIn('TAX_FAKTUR_NOT_FOUND', [c['code'] for c in checks])

    def test_zero_printed_ppn_can_be_explicitly_added(self):
        tax, _ = taxes.compute(self.invoice('0.00'), addition('TANPA'))
        self.assertEqual((tax['withheld_total'], tax['net_payable']), ('0.00', '555000.00'))

    def test_existing_printed_ppn_is_never_added_twice(self):
        tax, checks = taxes.compute(self.invoice('55000.00'), addition())
        self.assertEqual(tax['status'], 'NOT_COMPUTED')
        self.assertIn('TAX_ADJUSTMENT_INVALID', [c['code'] for c in checks])

    def test_ppn_choice_alone_does_not_silently_add_tax(self):
        choice = addition()
        choice.pop('ppn_adjustment')
        choice.pop('ppn_adjustment_reason')
        tax, _ = taxes.compute(self.invoice(), choice)
        self.assertEqual((tax['ppn_amount'], tax['gross_total']), ('0.00', '500000.00'))

    def test_addition_requires_ppn_and_a_reason_at_the_api_boundary(self):
        for changes in ({'ppn': False}, {'ppn_adjustment_reason': ' '}, {'ppn_adjustment': 'GUESS'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                TaxSelection(**(addition() | changes))

    def test_adjustment_reason_is_in_the_tax_audit_diff(self):
        self.assertIn('tax_selection.ppn_adjustment_reason', taxes.selection_changes(None, addition()))

    def test_v4_signed_and_draft_bytes_remain_unchanged(self):
        self.assertEqual(hashlib.sha256(render_voucher(v4_payload())).hexdigest(),
                         '50c4b561d3b540bce88cbd3464e3a9551b33839d2780e7f2b2d8a691ea951d25')
        self.assertEqual(hashlib.sha256(render_voucher(v4_payload(), SIGNOFF)).hexdigest(),
                         '2de049b0d30aced4c6fe6505828e1291736646ee74074c0a25f660d160665987')

    def test_v5_prints_source_addition_withholding_and_vendor_note(self):
        invoice = self.invoice()
        tax, _ = taxes.compute(invoice, addition())
        payload = v4_payload() | {'template_version': 'amiga-demo-v5', 'invoice': invoice,
                                 'tax': tax, 'tax_selection': addition()}
        _, text = pdf_text(render_voucher(payload, SIGNOFF))
        for expected in ('500.000', '55.000', '10.000', '545.000', 'Total invoice sumber',
                         'CATATAN KONFIRMASI PAJAK KEPADA VENDOR', 'bukan faktur pajak', 'bukan bukti potong'):
            self.assertIn(expected, text)


class TaxAdjustmentFlowTests(unittest.TestCase):
    setUp = flow.TaxFlowTests.setUp
    login = flow.TaxFlowTests.login
    sample = flow.TaxFlowTests.sample
    detail = flow.TaxFlowTests.detail
    edit = flow.TaxFlowTests.edit
    pic_submit = flow.TaxFlowTests.pic_submit
    forbid_live = staticmethod(flow.TaxFlowTests.forbid_live)
    submitted_sample = flow.TaxFlowTests.submitted_sample
    change_tax = flow.TaxFlowTests.change_tax

    def test_adjusting_after_finance_signed_requires_a_new_signature(self):
        identifier = self.submitted_sample()
        response = self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': 1, 'source_reviewed': True, 'consent': True,
            'password': 'test-password-only', 'reason': 'QA sintetis: pemeriksaan awal tanpa tambahan PPN.'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.api.state.review.process_next())
        revised = self.change_tax(identifier, addition(), 1)
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()['current_version'], 2)
        self.assertNotEqual(revised.json()['status'], 'AMIGA_REVIEWED')
        self.login('manajer.keuangan@amiga.local')
        stale = self.client.post(f'/api/v1/requests/{identifier}/director-approval', json={
            'expected_version': 1, 'password': 'test-password-only', 'consent': True})
        self.assertEqual(stale.status_code, 409)
        self.login('finance@amiga.local')
        approved = self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': 2, 'source_reviewed': True, 'consent': True,
            'tax_adjustment_confirmed': True, 'password': 'test-password-only',
            'reason': 'QA sintetis: penyesuaian PPN diperiksa dan ditandatangani ulang.'})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()['status'], 'AMIGA_REVIEWED')

    def test_finance_acknowledges_addition_and_director_receives_frozen_voucher(self):
        identifier = self.submitted_sample()
        before = self.detail(identifier)['draft']['invoice']
        updated = self.change_tax(identifier, addition(), 1)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['draft']['invoice'], before)
        payload = {'expected_version': 2, 'source_reviewed': True, 'consent': True,
                   'password': 'test-password-only', 'reason': 'Perhitungan dan kebutuhan dokumen pajak diperiksa.'}
        blocked = self.client.post(f'/api/v1/requests/{identifier}/review', json=payload)
        self.assertEqual((blocked.status_code, blocked.json()['code']), (422, 'TAX_ADJUSTMENT_CONFIRMATION_REQUIRED'))
        approved = self.client.post(f'/api/v1/requests/{identifier}/review',
                                    json=payload | {'tax_adjustment_confirmed': True})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()['status'], 'AMIGA_REVIEWED')
        self.assertTrue(self.api.state.review.process_next())
        self.login('manajer.keuangan@amiga.local')
        detail = self.detail(identifier)
        self.assertTrue(detail['signature']['can_director_act'])
        draft_pdf = self.client.get(f'/api/v1/requests/{identifier}/voucher?version=2')
        self.assertEqual(draft_pdf.status_code, 200)
        self.assertIn('545.000', pdf_text(draft_pdf.content)[1])
        signed = self.client.post(f'/api/v1/requests/{identifier}/director-approval', json={
            'expected_version': 2, 'password': 'test-password-only', 'consent': True})
        self.assertEqual(signed.status_code, 200, signed.text)
        self.assertEqual(signed.json()['status'], 'AMIGA_APPROVED')
        with self.api.state.db.transaction() as conn:
            frozen = conn.execute('SELECT payload FROM vouchers WHERE request_id=%s', (identifier,)).fetchone()['payload']
        self.assertEqual(frozen['invoice'], before)
        self.assertTrue(frozen['source_review']['tax_adjustment_confirmed'])
        self.assertEqual(frozen['tax']['net_payable'], '545000.00')
