"""PIC Intake corrects a draft during intake, then submits it to Finance on purpose (no live API)."""

from copy import deepcopy
import hashlib
import unittest

from app.signing import INTAKE_CONSENT, canonical_json
from app.tests import test_app as fixtures


NOTE = 'Data sudah dicocokkan dengan dokumen asli'


class IntakeSubmissionTests(unittest.TestCase):
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    sample = fixtures.DatabaseAcceptanceTests.sample
    detail = fixtures.DatabaseAcceptanceTests.detail
    edit = fixtures.DatabaseAcceptanceTests.edit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)

    def pic_sample(self, name='normal'):
        self.login('pic@amiga.local')
        return self.sample(name)

    def submit(self, identifier, version=1, **overrides):
        payload = dict(expected_version=version, consent=True, note=NOTE)
        payload.update(overrides)
        return self.client.post(f'/api/v1/requests/{identifier}/submit', json=payload)

    def approve(self, identifier, version=1):
        return self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': version, 'source_reviewed': True, 'reason': 'Dokumen sintetis diperiksa seluruh halaman',
            'password': 'test-password-only', 'consent': True})

    def audit(self, identifier, action):
        return [a for a in self.detail(identifier)['audit'] if a['action'] == action]

    def queue_row(self, identifier, client='client_a'):
        items = self.client.get(f'/api/v1/requests?client_id={client}').json()['items']
        return next(item for item in items if str(item['id']) == identifier)

    def test_pic_edits_during_intake_then_is_locked_after_submit(self):
        identifier = self.pic_sample()
        detail = self.detail(identifier)
        self.assertEqual((detail['stage'], detail['can_edit'], detail['can_submit']), ('INTAKE', True, True))
        invoice = deepcopy(detail['draft']['invoice'])
        invoice['due_date'] = '2026-11-30'
        response = self.edit(identifier, invoice, reason='Jatuh tempo sesuai halaman 1')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['audit'][0]['actor'], 'Dian Pratama')
        response = self.submit(identifier, version=2)
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['stage'], detail['can_edit'], detail['can_submit']), ('FINANCE', False, False))
        self.assertEqual((detail['submission']['by'], detail['submission']['version'], detail['submission']['note']),
                         ('Dian Pratama', 2, NOTE))
        invoice['due_date'] = '2026-12-31'
        response = self.edit(identifier, invoice, version=2)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'INTAKE_LOCKED'))
        self.assertEqual(self.detail(identifier)['current_version'], 2)

    def test_submit_needs_the_six_fields_but_not_npwp_or_faktur(self):
        identifier = self.pic_sample()
        original = self.detail(identifier)['draft']['invoice']
        # The sample prints no NPWP and no faktur, like many small vendors.
        self.assertFalse(original.get('vendor_npwp') or original.get('faktur_number'))
        invoice = deepcopy(original)
        for field in ('vendor_name', 'invoice_number', 'invoice_date', 'currency', 'stated_total'):
            invoice[field] = None
        invoice['payment']['account_number'] = None
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        self.assertEqual(self.detail(identifier)['missing_required'],
                         ['vendor_name', 'invoice_number', 'invoice_date', 'currency', 'stated_total', 'payment.account_number'])
        response = self.submit(identifier, version=2)
        self.assertEqual((response.status_code, response.json()['code']), (422, 'MISSING_EVIDENCE'))
        self.assertIn('Nomor rekening', response.json()['message'])
        self.assertEqual(self.edit(identifier, original, version=2).status_code, 200)
        self.assertEqual(self.detail(identifier)['missing_required'], [])
        response = self.submit(identifier, version=3)
        self.assertEqual(response.status_code, 200, response.text)

    def test_form_learns_the_required_fields_and_which_field_has_a_bad_format(self):
        # 15 Okt 2026: a PIC typed 23022026 as the date and only read "Periksa format tanggal, angka, ...".
        identifier = self.pic_sample()
        detail = self.detail(identifier)
        self.assertEqual(detail['required_fields'],
                         ['vendor_name', 'invoice_number', 'invoice_date', 'currency', 'stated_total', 'payment.account_number'])
        for field, value in (('invoice_date', '23022026'), ('currency', 'Rp')):
            with self.subTest(field=field):
                invoice = deepcopy(detail['draft']['invoice'])
                invoice[field] = value
                response = self.edit(identifier, invoice)
                self.assertEqual((response.status_code, response.json()['code'], response.json().get('field')),
                                 (422, 'INVALID_PAYLOAD', field))
        invoice = deepcopy(detail['draft']['invoice'])
        invoice['stated_total'] = '66.600.000'
        response = self.edit(identifier, invoice)
        self.assertEqual((response.status_code, response.json().get('field')), (422, None))
        self.assertEqual(self.detail(identifier)['current_version'], 1)

    def test_brief_scenario_3_missing_bank_stays_exception_until_the_pic_fills_it(self):
        identifier = self.pic_sample('missing_bank')
        detail = self.detail(identifier)
        self.assertEqual(detail['status'], 'EXCEPTION')
        self.assertIn(('MISSING_EVIDENCE', 'payment.account_number'),
                      [(c['code'], c.get('field')) for c in detail['draft']['validation']['checks']])
        self.assertEqual(detail['missing_required'], ['payment.account_number'])
        response = self.submit(identifier)
        self.assertEqual((response.status_code, response.json()['code']), (422, 'MISSING_EVIDENCE'))
        self.assertEqual(self.detail(identifier)['stage'], 'INTAKE')
        invoice = deepcopy(detail['draft']['invoice'])
        invoice['payment']['account_number'] = '00123456'
        self.assertEqual(self.edit(identifier, invoice, reason='Rekening disalin dari halaman 1').status_code, 200)
        self.assertEqual(self.submit(identifier, version=2).status_code, 200)
        self.login('finance@amiga.local')
        response = self.approve(identifier, version=2)
        self.assertEqual(response.status_code, 200, response.text)

    def test_submit_needs_consent_and_a_note_when_kendala_remain(self):
        identifier = self.pic_sample('wrong_total')
        self.assertEqual(self.detail(identifier)['status'], 'EXCEPTION')
        for overrides, code in (({'consent': False}, 'CONSENT_REQUIRED'), ({'note': None}, 'REASON_REQUIRED'),
                                ({'note': ' ok '}, 'REASON_REQUIRED')):
            with self.subTest(overrides=overrides):
                response = self.submit(identifier, **overrides)
                self.assertEqual((response.status_code, response.json()['code']), (422, code))
        self.assertEqual(self.audit(identifier, 'INTAKE_SUBMITTED'), [])
        note = 'Selisih total dibiarkan, vendor sedang mengirim revisi'
        response = self.submit(identifier, note=note)
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()['draft']
        [event] = self.audit(identifier, 'INTAKE_SUBMITTED')
        self.assertEqual((event['reason'], event['changes']['note']), (note, note))
        self.assertEqual(event['changes']['consent_text'], INTAKE_CONSENT)
        self.assertIn('TOTAL_MISMATCH', event['changes']['open_checks'])
        self.assertEqual(event['changes']['content_sha256'], hashlib.sha256(canonical_json(
            {'invoice': draft['invoice'], 'tax_selection': draft['tax_selection']})).hexdigest())

    def test_a_clean_draft_needs_no_note_and_keeps_its_version(self):
        identifier = self.pic_sample()
        response = self.submit(identifier, note=None)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()['current_version'], response.json()['submitted_version']), (1, 1))
        [event] = self.audit(identifier, 'INTAKE_SUBMITTED')
        self.assertEqual((event['changes']['open_checks'], event['changes']['note']), ([], None))
        self.assertNotIn('revalidated_from', event['changes'])

    def test_finance_cannot_sign_before_the_pic_submits(self):
        identifier = self.pic_sample()
        self.login('finance@amiga.local')
        approval = self.detail(identifier)['approval']
        self.assertEqual((approval['can_approve'], approval['reason_code']), (False, 'NOT_SUBMITTED'))
        response = self.approve(identifier)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'NOT_SUBMITTED'))
        self.login('pic@amiga.local')
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.login('finance@amiga.local')
        self.assertIsNone(self.detail(identifier)['approval']['reason_code'])
        self.assertEqual(self.approve(identifier).status_code, 200)

    def test_only_an_assigned_pic_submits_and_a_double_click_is_safe(self):
        identifier = self.pic_sample()
        for email, status in (('finance@amiga.local', 403), ('manajer.keuangan@amiga.local', 403), ('pic.b@amiga.local', 404)):
            with self.subTest(email=email):
                self.login(email)
                self.assertEqual(self.submit(identifier).status_code, status)
        self.login('pic@amiga.local')
        self.assertEqual(self.submit(identifier, version=2).json()['code'], 'VERSION_CONFLICT')
        first, second = self.submit(identifier), self.submit(identifier)
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(len(self.audit(identifier, 'INTAKE_SUBMITTED')), 1)

    def test_finance_edit_after_submit_keeps_the_submission(self):
        # Brief scenario 7: the reviewer still changes a nominal, and the change is recorded with name and time.
        identifier = self.pic_sample()
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.login('finance@amiga.local')
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['stated_total'] = '510000.00'
        response = self.edit(identifier, invoice, reason='Nominal disesuaikan dengan dokumen')
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['stage'], detail['submitted_version'], detail['submission']['by']),
                         ('FINANCE', 1, 'Dian Pratama'))
        edited = detail['audit'][0]
        self.assertEqual((edited['action'], edited['actor']), ('DRAFT_EDITED', 'Nadia Putri'))
        self.assertEqual(edited['changes']['stated_total']['after'], '510000.00')

    def test_submit_writes_a_version_only_when_the_checks_changed(self):
        first = self.pic_sample('normal')
        self.sample('wrong_total')  # the same invoice number and vendor, uploaded after the first was read
        response = self.submit(first)
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['current_version'], detail['submitted_version'], detail['status']), (2, 2, 'EXCEPTION'))
        self.assertIn('POSSIBLE_DUPLICATE', [c['code'] for c in detail['draft']['validation']['checks']])
        [event] = self.audit(first, 'INTAKE_SUBMITTED')
        self.assertEqual((event['version'], event['changes']['revalidated_from']), (2, 1))
        self.assertIn('POSSIBLE_DUPLICATE', event['changes']['open_checks'])

    def test_stage_in_detail_and_queue(self):
        identifier = self.pic_sample()
        row = self.queue_row(identifier)
        self.assertEqual((row['stage'], row['submitted_at']), ('INTAKE', None))
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.assertEqual(self.queue_row(identifier)['stage'], 'FINANCE')
        self.login('finance@amiga.local')
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertEqual(self.queue_row(identifier)['stage'], 'DIRECTOR')

    def test_restart_backfills_signed_requests_once(self):
        # The demo database of 15 Oct holds requests Finance signed before the PIC's submission step existed.
        signed = self.pic_sample()
        self.assertEqual(self.submit(signed).status_code, 200)
        self.login('finance@amiga.local')
        self.assertEqual(self.approve(signed).status_code, 200)
        self.login('pic.b@amiga.local')
        waiting = self.sample('normal', client='client_b')
        db = self.api.state.db
        with db.transaction() as conn:
            conn.execute('ALTER TABLE requests DROP COLUMN submitted_at, DROP COLUMN submitted_by, '
                         'DROP COLUMN submitted_version')
        db.initialize()
        db.initialize()
        with db.transaction() as conn:
            rows = {str(r['id']): r for r in conn.execute(
                'SELECT id,submitted_at,submitted_by,submitted_version FROM requests').fetchall()}
            migrated = conn.execute("SELECT request_id FROM audit_events WHERE action='INTAKE_SUBMITTED' "
                                    "AND changes->>'migrated'='true'").fetchall()
        self.assertEqual((rows[signed]['submitted_by'], rows[signed]['submitted_version']), ('pic_a', 1))
        self.assertIsNotNone(rows[signed]['submitted_at'])
        self.assertIsNone(rows[waiting]['submitted_at'])
        self.assertEqual([str(r['request_id']) for r in migrated], [signed])

    def finance_return(self, identifier, version=1, reason='Total tagihan tidak sesuai dokumen asli'):
        return self.client.post(f'/api/v1/requests/{identifier}/finance-return',
                                json={'expected_version': version, 'reason': reason})

    def test_finance_signs_with_open_checks_and_the_audit_keeps_them(self):
        # 15 Okt 2026, Aldian: the system advises and Finance decides. The review note says why it was signed anyway.
        identifier = self.pic_sample('wrong_total')
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.login('finance@amiga.local')
        detail = self.detail(identifier)
        self.assertIn('TOTAL_MISMATCH', [c['code'] for c in detail['approval']['blocking_checks']])
        self.assertEqual((detail['approval']['can_approve'], detail['approval']['reason']), (True, None))
        version = detail['current_version']
        response = self.client.post(f'/api/v1/requests/{identifier}/review', json={
            'expected_version': version, 'source_reviewed': True, 'reason': 'ok', 'password': 'test-password-only',
            'consent': True})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.approve(identifier, version=version).status_code, 200)
        [event] = self.audit(identifier, 'REVIEW_APPROVED')
        self.assertIn({'code': 'TOTAL_MISMATCH', 'field': None}, event['changes']['open_checks'])
        self.assertEqual(self.detail(identifier)['status'], 'AMIGA_REVIEWED')

    def test_an_empty_required_field_still_holds_approval(self):
        # Not a judgement but missing data: a voucher without an invoice number or account cannot be printed.
        identifier = self.pic_sample()
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.login('finance@amiga.local')
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['payment']['account_number'] = None
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        approval = self.detail(identifier)['approval']
        self.assertEqual((approval['can_approve'], approval['reason_code']), (False, 'MISSING_EVIDENCE'))
        self.assertIn('Nomor rekening', approval['reason'])
        self.assertEqual(self.approve(identifier, version=2).status_code, 422)

    def test_finance_returns_to_the_pic_who_corrects_and_submits_again(self):
        # Finance decides with two buttons: sign, or send it back. The PIC answers for the correction.
        identifier = self.pic_sample('wrong_total')
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.login('finance@amiga.local')
        detail = self.detail(identifier)
        self.assertEqual((detail['approval']['can_approve'], detail['can_return_to_pic']), (True, True))
        response = self.finance_return(identifier, version=detail['current_version'])
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['stage'], detail['submitted_at'], detail['can_return_to_pic']), ('INTAKE', None, False))
        self.assertEqual(self.queue_row(identifier)['returned_to_pic'], True)
        [event] = self.audit(identifier, 'FINANCE_RETURNED')
        self.assertEqual((event['actor'], event['reason'], event['changes']['submitted_by']),
                         ('Nadia Putri', 'Total tagihan tidak sesuai dokumen asli', 'pic_a'))
        self.login('pic@amiga.local')
        detail = self.detail(identifier)
        self.assertEqual((detail['can_edit'], detail['can_submit'], detail['submission']), (True, True, None))
        self.assertEqual((detail['returned_to_pic']['by'], detail['returned_to_pic']['reason']),
                         ('Nadia Putri', 'Total tagihan tidak sesuai dokumen asli'))
        invoice = deepcopy(detail['draft']['invoice'])
        invoice['stated_total'] = detail['draft']['validation']['calculated_total']
        response = self.edit(identifier, invoice, version=detail['current_version'], reason='Total sesuai dokumen')
        self.assertEqual(response.status_code, 200, response.text)
        response = self.submit(identifier, version=response.json()['current_version'])
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['stage'], detail['returned_to_pic'], detail['submission']['by']), ('FINANCE', None, 'Dian Pratama'))
        self.assertEqual(self.queue_row(identifier)['returned_to_pic'], False)
        self.login('finance@amiga.local')
        self.assertTrue(self.detail(identifier)['approval']['can_approve'])
        self.assertEqual(self.approve(identifier, version=detail['current_version']).status_code, 200)

    def test_other_charges_settle_a_total_and_an_empty_one_is_no_change(self):
        # wrong_total prints 510.000 against 500.000 of rows: a 10.000 charge below the subtotal explains it.
        identifier = self.pic_sample('wrong_total')
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        self.assertNotIn('stated_other_charges_total', invoice)  # saved before schema v3
        response = self.edit(identifier, dict(invoice, stated_other_charges_total=None))
        self.assertEqual((response.status_code, response.json()['code']), (422, 'NO_CHANGES'))
        response = self.edit(identifier, dict(invoice, stated_other_charges_total='10000.00'), reason='Biaya admin di bawah subtotal')
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        codes = {c['code'] for c in detail['draft']['validation']['checks']}
        self.assertEqual(('TOTAL_MATCH' in codes, 'TOTAL_MISMATCH' in codes), (True, False))
        self.assertEqual(detail['audit'][0]['changes']['stated_other_charges_total'], {'before': None, 'after': '10000.00'})

    def test_only_finance_returns_a_submitted_unsigned_invoice(self):
        identifier = self.pic_sample()
        self.login('finance@amiga.local')
        response = self.finance_return(identifier)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'INVALID_TRANSITION'))
        self.login('pic@amiga.local')
        self.assertEqual(self.submit(identifier).status_code, 200)
        self.assertEqual(self.finance_return(identifier).status_code, 403)
        self.login('finance@amiga.local')
        self.assertEqual(self.finance_return(identifier, reason='ok').status_code, 422)
        response = self.finance_return(identifier, version=2)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VERSION_CONFLICT'))
        self.assertEqual(self.approve(identifier).status_code, 200)
        self.assertFalse(self.detail(identifier)['can_return_to_pic'])
        response = self.finance_return(identifier)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'INVALID_TRANSITION'))
        self.assertEqual(self.audit(identifier, 'FINANCE_RETURNED'), [])


class VendorRegistrationTests(unittest.TestCase):
    """A vendor the client's master does not know yet is registered by the PIC who submits its invoice."""
    setUp = fixtures.DatabaseAcceptanceTests.setUp
    login = fixtures.DatabaseAcceptanceTests.login
    sample = fixtures.DatabaseAcceptanceTests.sample
    detail = fixtures.DatabaseAcceptanceTests.detail
    edit = fixtures.DatabaseAcceptanceTests.edit
    forbid_live = staticmethod(fixtures.DatabaseAcceptanceTests.forbid_live)
    submit = IntakeSubmissionTests.submit
    approve = IntakeSubmissionTests.approve
    audit = IntakeSubmissionTests.audit
    finance_return = IntakeSubmissionTests.finance_return

    def new_vendor_draft(self, name='normal', vendor='CV Anugerah Servis AC', account='00999888'):
        """A sample whose vendor and account the PIC corrected to a vendor the client's master does not know."""
        self.login('pic@amiga.local')
        identifier = self.sample(name)
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['vendor_name'], invoice['payment']['account_number'] = vendor, account
        invoice['payment']['account_holder'] = vendor
        self.assertEqual(self.edit(identifier, invoice, reason='Vendor dan rekening sesuai dokumen').status_code, 200)
        return identifier

    def vendors(self):
        with self.api.state.db.transaction() as conn:
            return conn.execute("SELECT id,name,verified_accounts,registered_by,registered_request_id FROM vendors "
                                "WHERE client_id='client_a' ORDER BY id").fetchall()

    def test_pic_registers_a_new_vendor_at_submit_and_finance_can_sign(self):
        identifier = self.new_vendor_draft()
        detail = self.detail(identifier)
        self.assertFalse(detail['approval']['vendor_known'])
        self.assertIn('BANK_UNVERIFIED', [c['code'] for c in detail['draft']['validation']['checks']])
        response = self.submit(identifier, version=2, note='Vendor servis AC baru, rekening sesuai invoice')
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual((detail['current_version'], detail['submitted_version']), (3, 3))
        checks = {c['code']: c for c in detail['draft']['validation']['checks']}
        self.assertEqual((checks['BANK_VERIFIED']['status'], checks['DUPLICATE_CHECK']['status']), ('PASSED', 'PASSED'))
        # Shown to Finance and the director, never holding approval.
        self.assertEqual((checks['VENDOR_NEW']['status'], checks['VENDOR_NEW']['blocking']), ('NOT_CHECKED', False))
        [vendor] = [v for v in self.vendors() if v['registered_by']]
        self.assertEqual((vendor['name'], vendor['verified_accounts'], vendor['registered_by'], str(vendor['registered_request_id'])),
                         ('CV Anugerah Servis AC', ['00999888'], 'pic_a', identifier))
        [event] = self.audit(identifier, 'VENDOR_REGISTERED')
        self.assertEqual(event['changes']['id'], vendor['id'])
        self.assertEqual(self.audit(identifier, 'INTAKE_SUBMITTED')[0]['changes']['registered_vendor'], vendor['id'])
        self.login('finance@amiga.local')
        self.assertTrue(self.detail(identifier)['approval']['can_approve'])
        self.assertEqual(self.approve(identifier, version=3).status_code, 200)

    def test_a_known_vendor_keeps_its_account_and_a_different_one_stays_flagged(self):
        # A swapped payee account on a known vendor is the classic fraud route: the PIC never registers over it.
        self.login('pic@amiga.local')
        identifier = self.sample('normal')
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['payment']['account_number'] = '00999888'
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        before = self.vendors()
        self.assertTrue(self.detail(identifier)['approval']['vendor_known'])
        self.assertEqual(self.submit(identifier, version=2).status_code, 200)
        self.assertEqual(self.vendors(), before)
        self.assertEqual(self.audit(identifier, 'VENDOR_REGISTERED'), [])
        self.login('finance@amiga.local')
        self.assertIn('BANK_MISMATCH', [c['code'] for c in self.detail(identifier)['approval']['blocking_checks']])
        # Finance decides: the mismatch stays flagged and is kept in the audit of the signature.
        self.assertTrue(self.detail(identifier)['approval']['can_approve'])
        self.assertEqual(self.approve(identifier, version=2).status_code, 200)
        [approved] = self.audit(identifier, 'REVIEW_APPROVED')
        self.assertIn('BANK_MISMATCH', [c['code'] for c in approved['changes']['open_checks']])

    def test_an_account_of_another_vendor_is_refused(self):
        self.login('pic@amiga.local')
        identifier = self.sample('normal')
        invoice = deepcopy(self.detail(identifier)['draft']['invoice'])
        invoice['vendor_name'] = 'PT Contoh Demo Baru'  # its account 00123456 belongs to PT Contoh Demo
        self.assertEqual(self.edit(identifier, invoice).status_code, 200)
        response = self.submit(identifier, version=2)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'VENDOR_EXISTS'))
        self.assertIn('PT Contoh Demo', response.json()['message'])
        self.assertEqual(len(self.vendors()), 1)
        self.assertEqual(self.detail(identifier)['stage'], 'INTAKE')

    def test_a_failed_submit_registers_nothing(self):
        identifier = self.new_vendor_draft()
        response = self.submit(identifier, version=2, note=None)
        self.assertEqual((response.status_code, response.json()['code']), (422, 'REASON_REQUIRED'))
        self.assertEqual(len(self.vendors()), 1)
        self.assertEqual(self.audit(identifier, 'VENDOR_REGISTERED'), [])
        self.assertEqual((self.detail(identifier)['current_version'], self.detail(identifier)['stage']), (2, 'INTAKE'))

    def test_a_returned_invoice_corrects_the_account_of_the_vendor_it_registered(self):
        # The AI misread the account, the PIC registered the vendor with it, and Finance sent it back.
        identifier = self.new_vendor_draft()
        response = self.submit(identifier, version=2, note='Vendor servis AC baru, rekening sesuai invoice')
        self.assertEqual(response.status_code, 200, response.text)
        self.login('finance@amiga.local')
        self.assertEqual(self.finance_return(identifier, version=response.json()['current_version'],
                                             reason='Nomor rekening salah baca').status_code, 200)
        self.login('pic@amiga.local')
        detail = self.detail(identifier)
        invoice = deepcopy(detail['draft']['invoice'])
        invoice['payment']['account_number'] = '00999777'
        response = self.edit(identifier, invoice, version=detail['current_version'], reason='Rekening sesuai dokumen')
        self.assertEqual(response.status_code, 200, response.text)
        response = self.submit(identifier, version=response.json()['current_version'], note='Rekening dibetulkan')
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        codes = {c['code']: c['status'] for c in detail['draft']['validation']['checks']}
        self.assertEqual((codes.get('BANK_VERIFIED'), 'BANK_MISMATCH' in codes), ('PASSED', False))
        [vendor] = [v for v in self.vendors() if v['registered_by']]
        self.assertEqual(vendor['verified_accounts'], ['00999777'])
        [event] = self.audit(identifier, 'VENDOR_UPDATED')
        self.assertEqual((event['changes']['account_number'], event['changes']['before']['account_number']),
                         ('00999777', '00999888'))
        self.login('finance@amiga.local')
        self.assertTrue(self.detail(identifier)['approval']['can_approve'])

    def test_duplicate_check_finds_an_earlier_invoice_of_a_vendor_registered_later(self):
        # The first invoice was saved while its vendor was unknown, so it stored no vendor id.
        self.new_vendor_draft('normal')
        second = self.new_vendor_draft('wrong_total')
        response = self.submit(second, version=2, note='Vendor servis AC baru, rekening sesuai invoice')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('POSSIBLE_DUPLICATE', [c['code'] for c in response.json()['draft']['validation']['checks']])


if __name__ == '__main__':
    unittest.main()
