'use strict';
// Keep decimal strings exact: converting invoice amounts to Number can lose digits.
window.amigaNumbers = (() => {
  const canonicalPattern = /^-?\d+(?:\.\d+)?$/;
  const localizedPattern = /^-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?$/;
  function normalized(value) {
    const text = String(value);
    if (!canonicalPattern.test(text)) return null;
    const negative = text.startsWith('-');
    const [integer, fraction = ''] = text.replace(/^-/, '').split('.');
    const whole = integer.replace(/^0+(?=\d)/, '');
    const decimals = fraction.replace(/0+$/, '');
    const result = whole + (decimals ? '.' + decimals : '');
    return negative && result !== '0' ? '-' + result : result;
  }
  function format(value, monetary = false) {
    if (value == null || value === '') return '';
    const text = normalized(value);
    if (text == null) return String(value);
    const [whole, decimals] = text.split('.');
    const fraction = monetary && decimals ? decimals.padEnd(2, '0') : decimals;
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (fraction ? ',' + fraction : '');
  }
  function parse(value, original) {
    const text = value.trim();
    if (text === '') return { valid: true, value: null };
    if (!localizedPattern.test(text)) return { valid: false };
    const canonical = text.replace(/\./g, '').replace(',', '.');
    if (canonical.replace(/[-.]/g, '').length > 40) return { valid: false };
    const result = normalized(canonical);
    // Merely focusing or retyping the same amount must not create a correction/version.
    return { valid: true, value: original != null && normalized(original) === result ? original : result };
  }
  const isField = path => /^stated_(?:subtotal|discount_total|other_charges_total|tax_total|total)$/.test(path)
    || /^line_items\[\d+\]\.(?:quantity|unit_price|stated_line_total)$/.test(path);
  function currency(value) {
    if (value == null || value === '') return '—';
    const text = normalized(value);
    if (text == null) return String(value);
    return (text.startsWith('-') ? '-Rp ' : 'Rp ') + format(text.replace(/^-/, ''), true);
  }
  return Object.freeze({ format, parse, isField, currency });
})();
