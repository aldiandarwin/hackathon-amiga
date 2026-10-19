'use strict';
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
// No document in this context, so the widget registers its helpers and stops before touching the page.
const context = { window: {} };
vm.runInNewContext(readFileSync(join(__dirname, '../static/chat-dock.js'), 'utf8'), context);
const view = context.window.amigaChatView;
const ID = '3f2a9c1e-8b7d-4e6f-9a0b-1c2d3e4f5a6b';

test('the open invoice comes from the review hash only when it is a uuid', () => {
  assert.equal(view.requestFromHash('#request=' + ID), ID);
  assert.equal(view.requestFromHash('#tab=data&request=' + ID), ID);
  assert.equal(view.requestFromHash('#request=../../api'), null);
  assert.equal(view.requestFromHash(''), null);
});

test('invoice links only ever point at the review page', () => {
  assert.equal(view.reviewHref(ID), '/review#request=' + ID);
  assert.equal(view.reviewHref('javascript:alert(1)'), null);
  assert.equal(view.reviewHref(undefined), null);
});

test('answers split into paragraphs and lists, with SOP citations kept apart from the text', () => {
  const blocks = view.parseAnswer('Ada 2 invoice desain.\n1. **INV-DSN-01** sudah disetujui.\n2. Cocokkan rekening. [EXC-BANK_MISMATCH]\n- catatan');
  // Arrays built inside the vm context carry its prototypes, so compare plain JSON copies.
  assert.deepEqual(JSON.parse(JSON.stringify(blocks.map(block => [block.kind, block.items.length]))), [['p', 1], ['ol', 2], ['ul', 1]]);
  assert.deepEqual(JSON.parse(JSON.stringify(blocks[1].items[0])), [{ text: 'INV-DSN-01 sudah disetujui.' }]);
  assert.deepEqual(JSON.parse(JSON.stringify(blocks[1].items[1])), [{ text: 'Cocokkan rekening. ' }, { cite: 'EXC-BANK_MISMATCH' }]);
});

test('every status a card can carry gets a chip tone, in the dashboard colours', () => {
  const labels = /STATUS_LABELS = \{(.*?)\n\}/s.exec(readFileSync(join(__dirname, '../chat_search.py'), 'utf8'))[1];
  const codes = [...labels.matchAll(/'([A-Z_]+)':/g)].map(match => match[1]);
  assert.ok(codes.length >= 9);
  for (const code of codes) assert.ok(code in view.tones, code);
  assert.equal(view.tone('AMIGA_APPROVED'), 'done');
  assert.equal(view.tone('EXCEPTION'), 'exception');
  assert.equal(view.tone('RETURNED_TO_PIC'), 'rejected');
  assert.equal(view.tone('SOMETHING_NEW'), 'processing');
});

test('card dates read the Indonesian way, anything else as it came', () => {
  assert.equal(view.shortDate('2026-09-21'), '21 Sep 2026');
  assert.equal(view.shortDate('21/09/2026'), '21/09/2026');
  assert.equal(view.shortDate(null), null);
});

test('only kendala are counted as kendala, the same number as the bar under the review form', () => {
  const summary = groups => JSON.parse(JSON.stringify(view.checksSummary(groups)));
  assert.deepEqual(summary({ kendala: ['TAX_FAKTUR_NOT_FOUND'], cocokkan: ['A', 'B', 'C'], catatan: ['D', 'E'] }), {
    lead: 'Invoice ini punya 1 kendala.',
    more: 'Ada juga 3 hal untuk dicocokkan dengan dokumen dan 2 catatan.',
    bar: 'Lihat 1 kendala dan 5 hal lain' });
  assert.deepEqual(summary({ kendala: ['A', 'B'], cocokkan: [], catatan: [] }),
    { lead: 'Invoice ini punya 2 kendala.', more: '', bar: 'Lihat 2 kendala invoice ini' });
  assert.deepEqual(summary({ kendala: [], cocokkan: ['A'], catatan: [] }),
    { lead: 'Tidak ada kendala yang menahan keputusan.', more: 'Ada 1 hal untuk dicocokkan dengan dokumen.', bar: 'Lihat 1 hal untuk dicek' });
  assert.deepEqual(summary({ kendala: [], cocokkan: [], catatan: [] }), { lead: '', more: '', bar: '' });
});

test('every role gets example questions', () => {
  for (const role of ['PIC', 'FINANCE_REVIEWER', 'AMIGA_DIRECTOR', 'UNKNOWN']) assert.ok(view.examples(role).length >= 3);
});
