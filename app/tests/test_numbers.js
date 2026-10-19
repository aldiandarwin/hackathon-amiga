'use strict';
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const context = { window: {} };
vm.runInNewContext(readFileSync(join(__dirname, '../static/numbers.js'), 'utf8'), context);
const numbers = context.window.amigaNumbers;

test('Indonesian display keeps meaningful decimals and exact large amounts', () => {
  for (const [value, expected] of [
    ['25000.00', '25.000'], ['75000.00', '75.000'], ['0.00', '0'],
    ['25000.50', '25.000,5'], ['1.125', '1,125'], ['-1500.25', '-1.500,25'],
    ['900719925474099300000000.05', '900.719.925.474.099.300.000.000,05'],
  ]) assert.equal(numbers.format(value), expected);
  assert.equal(numbers.format('25000.50', true), '25.000,50');
  assert.equal(numbers.format('25000.00', true), '25.000');
});

test('editing keeps the same canonical value without a false correction', () => {
  for (const original of ['25000.00', '0.00', '1.500', '-1500.25', '900719925474099300000000.05']) {
    const parsed = numbers.parse(numbers.format(original), original);
    assert.equal(parsed.valid, true);
    assert.equal(parsed.value, original);
  }
  assert.equal(numbers.parse('25.000,50', '25000.00').value, '25000.5');
  assert.equal(numbers.parse('1,5', '1').value, '1.5');
});

test('empty amounts remain missing while zero remains a number', () => {
  assert.equal(numbers.format(null), '');
  assert.equal(numbers.parse('', '0.00').value, null);
  assert.equal(numbers.parse('0', null).value, '0');
});

test('currency summaries retain exact digits, fractions, zero and missing amounts', () => {
  assert.equal(numbers.currency('9007199254740993.01'), 'Rp 9.007.199.254.740.993,01');
  assert.equal(numbers.currency('25000.50'), 'Rp 25.000,50');
  assert.equal(numbers.currency('0.00'), 'Rp 0');
  assert.equal(numbers.currency(null), '—');
  assert.equal(numbers.currency('-1500.25'), '-Rp 1.500,25');
});

test('ambiguous separators and invalid amounts cannot silently change magnitude', () => {
  for (const invalid of ['25.00', '25000.00', '25,000.50', '1e3', 'NaN', '12.34.567', 'Rp 25.000', '1'.repeat(41)]) {
    assert.equal(numbers.parse(invalid, '25000.00').valid, false, invalid);
  }
});

test('only quantities and amounts are numeric fields; account and invoice IDs retain zeros', () => {
  for (const field of ['stated_total', 'stated_tax_total', 'line_items[2].quantity', 'line_items[2].unit_price', 'line_items[2].stated_line_total']) {
    assert.equal(numbers.isField(field), true, field);
  }
  for (const field of ['payment.account_number', 'invoice_number', 'vendor_npwp', 'faktur_number', 'line_items[2].description']) {
    assert.equal(numbers.isField(field), false, field);
  }
});
