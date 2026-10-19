'use strict';
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const context = { window: {} };
vm.runInNewContext(readFileSync(join(__dirname, '../static/payment-summary.js'), 'utf8'), context);
const summary = context.window.amigaPaymentSummary;
const detail = () => ({ status: 'READY_FOR_REVIEW', draft: { invoice: { stated_total: '4440000.00' },
  validation: { checks: [] }, tax: { status: 'COMPUTED', net_payable: '4360000.00',
    dpp: '4000000.00', ppn_amount: '440000.00', gross_total: '4440000.00',
    withheld_total: '80000.00', pph_id: 'PPH23', pph_short: 'PPh 23' } } });

test('uncomputed tax never substitutes the invoice total for a payment amount', () => {
  for (const status of ['NOT_SELECTED', 'NOT_COMPUTED']) {
    const value = detail(); value.draft.tax.status = status;
    const shown = summary(value);
    assert.equal(shown.amount, null); assert.equal(shown.ready, false);
    assert.equal(shown.invoiceTotal, '4440000.00'); assert.equal(shown.rows.length, 0);
  }
  assert.equal(summary({ status: 'QUEUED' }).amount, null);
});
test('computed amounts retain their server values and describe a plan', () => {
  const shown = summary(detail());
  assert.equal(shown.amount, '4360000.00');
  assert.deepEqual(Array.from(shown.rows, row => row.value), ['4000000.00', '440000.00', '4440000.00', '80000.00']);
  assert.match(shown.label, /Rencana/); assert.equal(shown.note, '');
});
test('unsaved edits hide stale amounts, open checks show the amount Finance would sign for', () => {
  assert.equal(summary(detail(), true).amount, null);
  assert.equal(summary(detail(), true).pendingText, 'Menunggu koreksi disimpan');
  // Open checks remain in the checks panel; the computed amount stays visible without repeated prose.
  const value = detail(); value.draft.validation.checks = [{code: 'TOTAL_MISMATCH', blocking: true, status: 'FAILED'}];
  assert.equal(summary(value).amount, '4360000.00');
  assert.equal(summary(value).note, '');
  value.draft.validation.checks[0].code = 'SOURCE_VALUE_MISMATCH';
  assert.doesNotMatch(summary(value).note, /kendala/);
});
test('approved zero amounts retain the voucher-specific label', () => {
  const value = detail(); value.status = 'AMIGA_APPROVED'; value.draft.tax.net_payable = '0.00';
  assert.equal(summary(value).amount, '0.00');
  assert.match(summary(value).label, /disetujui/); assert.equal(summary(value).note, '');
});
