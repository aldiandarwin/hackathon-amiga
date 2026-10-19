'use strict';
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const context = { window: {} };
vm.runInNewContext(readFileSync(join(__dirname, '../static/review-guide.js'), 'utf8'), context);
const guide = context.window.amigaReviewGuide;
const reviewer = { role: 'FINANCE_REVIEWER' };
function invoice(overrides = {}) {
  return { status: 'READY_FOR_REVIEW', draft: { tax: { status: 'COMPUTED' } },
    approval: { can_approve: true, source_checks: [], blocking_checks: [] }, ...overrides };
}

test('uploader is sent to another reviewer even with duplicate and tax problems', () => {
  const next = guide(invoice({ approval: { can_approve: false, reason_code: 'UPLOADER_CANNOT_REVIEW',
    blocking_checks: [{ code: 'POSSIBLE_DUPLICATE' }] } }), reviewer);
  assert.match(next.title, /reviewer Finance lain/);
  assert.equal(next.action, 'copy');
});
test('manual source checks remain separate from hard blockers and information', () => {
  const duplicate = { code: 'POSSIBLE_DUPLICATE', blocking: true, status: 'FAILED' };
  const manual = { code: 'SOURCE_VALUE_MISMATCH', blocking: true, status: 'FAILED' };
  const note = { code: 'NPWP_CHECK', blocking: false, status: 'WARNING' };
  const result = context.window.amigaReviewChecks({
    draft: { validation: { checks: [duplicate, manual, note] } },
    approval: { blocking_checks: [duplicate], source_checks: [manual] },
  });
  assert.equal(result.blockers.length, 1);
  assert.equal(result.blockers[0].code, duplicate.code);
  assert.equal(result.sources[0].code, manual.code);
  assert.equal(result.notes[0].code, note.code);
});
test('tax selection offers a navigation action rather than changing the tax automatically', () => {
  const next = guide(invoice({ draft: { tax: { status: 'NOT_SELECTED' } } }), reviewer);
  assert.equal(next.action, 'tax');
  assert.match(next.message, /Simpan pilihan/);
});
test('a tax conflict sends the reviewer to tax controls rather than inviting a nominal change', () => {
  const next = guide(invoice({ approval: { can_approve: false,
    blocking_checks: [{ code: 'TAX_PPN_CONFLICT', field: 'stated_tax_total' }] } }), reviewer);
  assert.equal(next.action, 'tax');
  assert.match(next.title, /pilihan dan data pajak/);
});
test('Finance still checks the document when automatic blockers are absent', () => {
  const next = guide(invoice({ approval: { can_approve: true,
    source_checks: [{ code: 'VISUAL_REVIEW_REQUIRED' }], blocking_checks: [] } }), reviewer);
  assert.equal(next.action, 'checks');
  assert.match(next.message, /konfirmasi langsung/);
});
test('pending draft does not tell the director that the PDF can already be signed', () => {
  const next = guide(invoice({ status: 'AMIGA_REVIEWED', voucher: { render_status: 'RENDERING' } }), { role: 'AMIGA_DIRECTOR' });
  assert.match(next.message, /setelah PDF tersedia/);
  assert.equal(next.action, null);
});
test('director follows actual server permission for an unsupported voucher', () => {
  const next = guide(invoice({ status: 'AMIGA_REVIEWED', voucher: { render_status: 'READY' },
    signature: { can_director_act: false, director_block_reason: 'Format lama perlu dikembalikan ke Finance.' } }), { role: 'AMIGA_DIRECTOR' });
  assert.match(next.message, /Format lama/);
  assert.equal(next.tone, 'attention');
});
test('ready draft tells Finance to hand off and director to inspect', () => {
  const detail = invoice({ status: 'AMIGA_REVIEWED', voucher: { render_status: 'READY' }, signature: { can_director_act: true } });
  assert.equal(guide(detail, reviewer).action, 'director_login');
  assert.equal(guide(detail, { role: 'AMIGA_DIRECTOR' }).action, 'voucher');
});
test('failed final PDF explains recovery despite the successful director signature', () => {
  const next = guide(invoice({ status: 'AMIGA_APPROVED', signature: { signed_voucher: { render_status: 'FAILED' } } }), reviewer);
  assert.equal(next.tone, 'attention');
  assert.match(next.message, /Persetujuan sudah tersimpan/);
});
test('finished voucher retains the boundary for external client payment', () => {
  const next = guide(invoice({ status: 'AMIGA_APPROVED', signature: { signed_voucher: { render_status: 'READY' } } }), reviewer);
  assert.equal(next.phase, 5);
  assert.match(next.title, /Selesai/);
  assert.match(next.message, /di luar aplikasi/);
});
test('returned invoice shows the director reason', () => {
  const next = guide(invoice({ status: 'RETURNED', signature: { returned: { reason: 'Cek nominal pajak.' } } }), reviewer);
  assert.equal(next.message, 'Cek nominal pajak.');
});
test('PIC in intake is guided to submit, and open checks ask for a note', () => {
  const pic = { role: 'PIC' };
  const approval = blocking_checks => ({ can_approve: false, reason_code: 'FINANCE_REQUIRED', blocking_checks, source_checks: [] });
  const clean = guide(invoice({ stage: 'INTAKE', missing_required: [], approval: approval([]) }), pic);
  assert.equal(clean.phase, 2);
  assert.equal(clean.action, 'submit');
  const open = guide(invoice({ stage: 'INTAKE', missing_required: [], approval: approval([{ code: 'TOTAL_MISMATCH' }]) }), pic);
  assert.equal(open.tone, 'attention');
  assert.match(open.message, /catatan alasannya/);
});
test('PIC fills the required fields first; the form names the empty ones, so the guide keeps to the count', () => {
  const next = guide(invoice({ stage: 'INTAKE', missing_required: ['payment.account_number'] }), { role: 'PIC' });
  assert.equal(next.action, 'checks');
  assert.equal(next.title, 'Lengkapi 1 isian wajib sebelum mengajukan');
  assert.equal(next.message, '');
});
test('a submitted PIC hands over, and Finance waits for the submission', () => {
  assert.equal(guide(invoice({ stage: 'FINANCE' }), { role: 'PIC' }).title, 'Sudah diajukan ke Finance');
  const waiting = guide(invoice({ stage: 'INTAKE',
    approval: { can_approve: false, reason_code: 'NOT_SUBMITTED', blocking_checks: [] } }), reviewer);
  assert.equal(waiting.title, 'Menunggu pengajuan PIC');
  assert.equal(waiting.phase, 2);
});
test('unsaved edits lead to saving and failed extraction stays at the AI stage', () => {
  assert.equal(guide(invoice(), reviewer, true).action, 'reason');
  // 15 Okt 2026: the PIC no longer types a correction reason; submitting saves the draft first.
  const pic = guide(invoice({ stage: 'INTAKE', can_submit: true }), { role: 'PIC' }, true);
  assert.equal(pic.action, 'submit');
  assert.match(pic.message, /Simpan draf/);
  const failed = guide(invoice({ status: 'EXCEPTION', draft: null }), reviewer);
  assert.equal(failed.phase, 1);
  assert.equal(failed.action, 'copy');
  assert.match(failed.message, /Proses sudah berhenti/);
});
test('Finance decides on open checks, and the PIC reads the reason of a return first', () => {
  // 15 Okt 2026, Aldian: the checks advise; approval stays open and the guide names the three choices.
  const flagged = invoice({ status: 'EXCEPTION', stage: 'FINANCE', can_return_to_pic: true,
    approval: { can_approve: true, blocking_checks: [{ code: 'TOTAL_MISMATCH' }], source_checks: [] } });
  const finance = guide(flagged, reviewer);
  assert.equal(finance.title, '1 kendala untuk dicek');
  assert.equal(finance.action, 'checks');
  assert.match(finance.message, /setujui dengan catatan review, koreksi dulu, atau kembalikan ke PIC/);
  assert.doesNotMatch(finance.message, /ditahan/);
  const duplicate = guide(invoice({ approval: { can_approve: true, blocking_checks: [{ code: 'POSSIBLE_DUPLICATE' }],
    source_checks: [] } }), reviewer);
  assert.match(duplicate.message, /dibayar dua kali/);
  const returned = guide(invoice({ status: 'EXCEPTION', stage: 'INTAKE', missing_required: [],
    returned_to_pic: { by: 'Nadia Putri', reason: 'Rekening salah baca' },
    approval: { can_approve: false, reason_code: 'FINANCE_REQUIRED', blocking_checks: [], source_checks: [] } }), { role: 'PIC' });
  assert.equal(returned.title, 'Dikembalikan Finance');
  assert.equal(returned.action, 'submit');
  assert.match(returned.message, /Rekening salah baca/);
});

const hint = context.window.amigaCheckHint;
// INV/2026/03/01 as the AI read it: Rp600.000 of marketplace tools printed below the subtotal, read as a discount.
const misread = () => ({ line_items: [
  { quantity: '1', unit_price: '6000000.00', stated_line_total: '6000000.00' },
  { quantity: '1', unit_price: '2500000.00', stated_line_total: '2500000.00' },
  { quantity: '4', unit_price: '400000.00', stated_line_total: '1600000.00' }],
  stated_subtotal: '10100000.00', stated_discount_total: '600000.00', stated_tax_total: '1177000.00',
  stated_total: '11877000.00', payment: { account_number: '118890944' } });
test('a total off by twice the discount suggests moving the discount to other charges', () => {
  const advice = hint({ code: 'TOTAL_MISMATCH' }, { draft: {} }, misread());
  assert.match(advice.text, /= Rp 10\.677\.000\. Total tertulis Rp 11\.877\.000, selisih Rp 1\.200\.000\./);
  assert.match(advice.advice, /Rp 600\.000 kemungkinan biaya tambahan, bukan diskon/);
  assert.deepEqual({ ...advice.fill }, { stated_discount_total: '0', stated_other_charges_total: '600000' });
  // Applied, the same arithmetic balances: no gap, so nothing left to suggest.
  const fixed = { ...misread(), ...advice.fill };
  assert.equal(hint({ code: 'TOTAL_MISMATCH' }, { draft: {} }, fixed).fill, undefined);
});
test('other gaps suggest other charges or a discount, and a missing PPN only advises', () => {
  const larger = { ...misread(), stated_discount_total: null, stated_total: '11777000.00' };
  assert.deepEqual({ ...hint({ code: 'TOTAL_MISMATCH' }, { draft: {} }, larger).fill }, { stated_other_charges_total: '500000' });
  const smaller = { ...misread(), stated_discount_total: '0', stated_total: '11077000.50' };
  assert.deepEqual({ ...hint({ code: 'TOTAL_MISMATCH' }, { draft: {} }, smaller).fill }, { stated_discount_total: '199999.50' });
  const untaxed = { ...misread(), stated_discount_total: '0', stated_total: '10100000.00' };
  const advice = hint({ code: 'TOTAL_MISMATCH' }, { draft: {} }, untaxed);
  assert.match(advice.advice, /belum termasuk PPN/);
  assert.equal(advice.fill, undefined);
  assert.equal(hint({ code: 'TOTAL_MISMATCH' }, { draft: {} }, { ...misread(), stated_total: null }), null);
});
test('line and subtotal hints compute from the lines, the PPN conflict offers the PPN choice', () => {
  const invoice = misread(); invoice.line_items[2].stated_line_total = '1200000.00';
  const line = hint({ code: 'LINE_TOTAL_MISMATCH', fields: ['line_items[2]'] }, { draft: {} }, invoice);
  assert.match(line.text, /Item 3: 4 × Rp 400\.000 = Rp 1\.600\.000, tertulis Rp 1\.200\.000\./);
  assert.deepEqual({ ...line.fill }, { 'line_items[2].stated_line_total': '1600000' });
  assert.deepEqual({ ...hint({ code: 'SUBTOTAL_MISMATCH' }, { draft: {} }, invoice).fill }, { stated_subtotal: '9700000' });
  const ppn = hint({ code: 'TAX_PPN_CONFLICT' }, { draft: {} }, misread());
  assert.match(ppn.text, /PPN Rp 1\.177\.000/);
  assert.deepEqual({ ...ppn.tax }, { ppn: true });
});
// SIPLah laptop, 16 Okt 2026: the price in the description holds the PPN, the columns hold the value before PPN.
const siplah = lineTotal => ({ line_items: [{ quantity: '1.00', unit_price: '7950000.00', stated_line_total: lineTotal }],
  stated_subtotal: '7162162.00', stated_discount_total: null, stated_other_charges_total: '0.00',
  stated_tax_total: '787838.00', stated_total: '7950000.00' });
test('a price that already holds the PPN never pushes the PPN into the lines twice', () => {
  // As the AI read it: quantity x price is the price with PPN, while the line total is the value before PPN.
  const read = hint({ code: 'LINE_TOTAL_MISMATCH', fields: ['line_items[0]'] }, { draft: {} }, siplah('7162162.00'));
  assert.match(read.text, /sudah termasuk PPN: kuantitas × harga satuan berjumlah Rp 7\.950\.000, sama dengan subtotal Rp 7\.162\.162 ditambah PPN Rp 787\.838\./);
  assert.deepEqual({ ...read.fill }, { 'line_items[0].unit_price': '7162162' });
  // As the PIC saved it: the line total copied from that price. The subtotal stays; the line goes back before PPN.
  const saved = hint({ code: 'SUBTOTAL_MISMATCH' }, { draft: {} }, siplah('7950000'));
  assert.match(saved.advice, /Subtotal sudah benar, jangan diubah/);
  assert.deepEqual({ ...saved.fill }, { 'line_items[0].stated_line_total': '7162162', 'line_items[0].unit_price': '7162162' });
  // Applied, quantity x price equals the line total, and the lines add up to the subtotal.
  const fixed = { ...siplah('7162162'), line_items: [{ quantity: '1.00', unit_price: '7162162', stated_line_total: '7162162' }] };
  assert.match(hint({ code: 'LINE_TOTAL_MISMATCH', fields: ['line_items[0]'] }, { draft: {} }, fixed).text,
    /= Rp 7\.162\.162, tertulis Rp 7\.162\.162\./);
  // Several lines cannot be split back exactly, so the advice comes without a fill.
  const two = { ...siplah('3975000'), line_items: [
    { quantity: '1', unit_price: '3975000', stated_line_total: '3975000' },
    { quantity: '1', unit_price: '3975000', stated_line_total: '3975000' }] };
  const several = hint({ code: 'SUBTOTAL_MISMATCH' }, { draft: {} }, two);
  assert.match(several.text, /sudah termasuk PPN/);
  assert.equal(several.fill, undefined);
});
test('checks whose truth is on paper only advise, and a photo gets one note', () => {
  for (const code of ['BANK_MISMATCH', 'POSSIBLE_DUPLICATE', 'TAX_PPN_MISSING']) {
    const advice = hint({ code }, { draft: {} }, misread());
    assert.ok(advice.advice, code);
    assert.equal(advice.fill, undefined, code);
  }
  assert.match(hint({ code: 'BANK_MISMATCH' }, { draft: {} }, misread()).text, /118890944/);
  assert.match(hint({ code: 'OCR_INCOMPLETE' }, { media_type: 'image/jpeg', draft: {} }, misread()).text, /foto/);
  assert.equal(hint({ code: 'OCR_INCOMPLETE' }, { media_type: 'application/pdf', draft: {} }, misread()), null);
  assert.equal(hint({ code: 'NPWP_MISMATCH' }, { draft: {} }, misread()), null);
});
