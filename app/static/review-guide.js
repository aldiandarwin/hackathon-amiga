'use strict';
window.amigaReadFailure = code => ({
  BUDGET_BLOCKED: { title: 'Batas anggaran AI tercapai', message: 'Pemrosesan berhenti karena batas anggaran atau catatan request sebelumnya. Teruskan ID request ke admin.' },
  PROCESS_INTERRUPTED: { title: 'Proses pembacaan terputus', message: 'Proses berhenti sebelum selesai. File asli tetap tersimpan; teruskan ID request ke admin.' },
  DOCUMENT_CHANGED: { title: 'Dokumen perlu diperiksa admin', message: 'Pemeriksaan keutuhan dokumen belum lolos. Teruskan ID request ke admin sebelum melanjutkan.' },
}[code] || { title: 'AI belum berhasil membaca invoice', message: 'Proses sudah berhenti. File asli tetap tersimpan; teruskan ID request ke admin. Tidak ada pengulangan otomatis.' });
// Describe the next step from server permissions; this helper never grants approval.
window.amigaReviewGuide = (detail, user, dirty = false) => {
  const status = detail.status, role = user?.role, approval = detail.approval || {};
  const signature = detail.signature || {}, final = signature.signed_voucher;
  const phase = status === 'AMIGA_APPROVED' ? 5 : status === 'AMIGA_REVIEWED' ? 4
    : !detail.draft || ['QUEUED', 'PROCESSING'].includes(status) ? 1 : detail.stage === 'INTAKE' ? 2 : 3;
  const guide = (title, message, action = null, actionLabel = null, tone = 'neutral') =>
    ({ phase, title, message, action, actionLabel, tone });
  const unique = checks => new Set((checks || []).map(check => check.code)).size;
  // A PIC in intake submits straight from unsaved edits: submitting saves the draft first.
  if (dirty && role === 'PIC' && detail.can_submit) return guide('Ada perubahan yang belum disimpan',
    'Ajukan ke Finance untuk menyimpan sekaligus mengajukan, atau Simpan draf untuk lanjut nanti.',
    'submit', 'Ajukan ke Finance', 'attention');
  if (dirty) return guide('Simpan koreksi sebelum melanjutkan',
    'Lengkapi alasan koreksi, lalu simpan. Pengajuan PIC dan persetujuan Finance selalu memakai versi data yang sudah tersimpan.',
    'reason', 'Isi alasan koreksi', 'attention');
  if (['QUEUED', 'PROCESSING'].includes(status)) return guide('AI sedang menyiapkan data invoice',
    'Hasil baca dan pemeriksaan muncul otomatis. Persetujuan Finance dilakukan sesudah proses ini selesai.');
  if (detail.voucher?.render_status === 'FAILED' || final?.render_status === 'FAILED') return guide(
    final?.render_status === 'FAILED' ? 'Voucher final perlu dibuat ulang' : 'Draf voucher perlu dibuat ulang',
    'Persetujuan sudah tersimpan. Finance dapat mengulang pembuatan PDF dari tab Voucher & persetujuan.',
    'voucher', 'Lihat status voucher', 'attention');
  if (status === 'AMIGA_APPROVED') return guide(final?.render_status === 'READY'
    ? 'Selesai: voucher final tersedia' : 'Manajer Keuangan sudah menyetujui; PDF final sedang dibuat',
    'Finance dan Manajer Keuangan AMIGA sudah menyetujui. Cetak voucher final untuk tanda tangan basah. Persetujuan pembayaran dan pembayaran klien dilakukan di luar aplikasi.',
    'voucher', 'Lihat voucher final', 'good');
  if (status === 'AMIGA_REVIEWED') {
    if (detail.voucher?.render_status !== 'READY') return guide('Persetujuan Finance tersimpan',
      'Draf voucher sedang disiapkan. Manajer Keuangan AMIGA dapat memeriksa dan menyetujui setelah PDF tersedia.');
    if (role === 'AMIGA_DIRECTOR' && !signature.can_director_act) return guide('Periksa status voucher sebelum melanjutkan',
      signature.director_block_reason || 'Voucher ini belum tersedia untuk persetujuan Manajer Keuangan.',
      'voucher', 'Lihat status voucher', 'attention');
    return role === 'AMIGA_DIRECTOR' ? guide('Periksa hasil Finance sebelum menyetujui',
      'Cocokkan invoice, nominal dibayar, rekening dan koreksi Finance. Setujui bila sesuai, atau kembalikan dengan alasan.',
      'voucher', 'Periksa draf voucher') : guide('Langkah berikutnya: persetujuan Manajer Keuangan AMIGA',
      'Finance sudah menyetujui. Manajer Keuangan membuka Persetujuan, memeriksa draf voucher, lalu menyetujui atau mengembalikan. Gunakan Ganti akun untuk masuk sebagai Manajer Keuangan.',
      'director_login', 'Masuk sebagai Manajer Keuangan');
  }
  if (!detail.draft) { const failure = window.amigaReadFailure(detail.error_code);
    return guide(failure.title, failure.message, 'copy', 'Salin ID untuk admin', 'attention'); }
  if (role === 'PIC') {
    // The PIC corrects and submits; whatever stays open goes to Finance with the PIC's note.
    if (detail.stage !== 'INTAKE') return guide('Sudah diajukan ke Finance',
      'Finance AMIGA memeriksa versi yang Anda ajukan, lalu Manajer Keuangan AMIGA menyetujui. Koreksi berikutnya dilakukan Finance.',
      'copy', 'Salin ID request');
    // Finance sent it back: its reason comes before anything else the PIC reads.
    if (detail.returned_to_pic) return guide('Dikembalikan Finance',
      `Alasan Finance: "${detail.returned_to_pic.reason}". Perbaiki isiannya, lalu ajukan ulang ke Finance.`,
      'submit', 'Ajukan ulang ke Finance', 'attention');
    const missing = (detail.missing_required || []).length;
    if (missing) return guide(`Lengkapi ${missing} isian wajib sebelum mengajukan`, '',
      'checks', 'Lihat yang perlu dilengkapi', 'attention');
    const open = unique([...(approval.blocking_checks || []), ...(approval.source_checks || [])])
      + (detail.draft.tax?.status !== 'COMPUTED' ? 1 : 0);
    return guide('Periksa data, lalu ajukan ke Finance', open
      ? `Masih ada ${open} kendala. Perbaiki yang bisa diperbaiki, atau ajukan dengan catatan alasannya. Anda bertanggung jawab atas isi yang diajukan.`
      : 'Cocokkan data dengan dokumen asli. Bila sudah benar, ajukan ke Finance untuk diperiksa.',
      'submit', 'Ajukan ke Finance', open ? 'attention' : 'neutral');
  }
  if (role === 'AMIGA_DIRECTOR') return guide('Menunggu pemeriksaan dan persetujuan Finance',
    'Manajer Keuangan AMIGA memutuskan setelah Finance selesai memeriksa dan draf voucher tersedia.');
  if (approval.reason_code === 'UPLOADER_CANNOT_REVIEW') return guide('Invoice ini perlu reviewer Finance lain',
    'Invoice diunggah oleh akun Anda, sehingga persetujuannya harus dilakukan Finance lain pada klien yang sama. Kendala data di bawah juga tetap perlu diperiksa.',
    'copy', 'Salin ID untuk reviewer lain', 'attention');
  if (approval.reason_code === 'NOT_SUBMITTED') return guide('Menunggu pengajuan PIC',
    'PIC Intake belum mengajukan invoice ini. Finance memeriksa dan menyetujui sesudah PIC mencocokkan data lalu mengajukannya.',
    'copy', 'Salin ID untuk PIC');
  if (status === 'RETURNED') return guide('Manajer Keuangan meminta pemeriksaan ulang',
    signature.returned?.reason || 'Baca alasan pengembalian, lalu koreksi bila perlu dan setujui ulang versi yang berlaku.',
    'voucher', 'Baca alasan Manajer Keuangan', 'attention');
  // Only the tax holds the signature: the voucher needs Finance's own choice and an amount to pay.
  if (detail.draft.tax?.status === 'NOT_SELECTED') return guide('Lengkapi pilihan pajak sebelum persetujuan',
    'Pilih pajak sesuai dokumen, termasuk Tanpa pajak bila sesuai. Simpan pilihan beserta alasan agar nominal dihitung ulang.',
    'tax', 'Buka pilihan pajak', 'attention');
  if (detail.draft.tax?.status !== 'COMPUTED') return guide('Nominal bayar belum bisa dihitung',
    approval.reason || 'Periksa Total tagihan dan mata uang, lalu simpan koreksi.', 'tax', 'Buka bagian pajak', 'attention');
  // 15 Okt 2026, Aldian: the checks advise and Finance decides. Sign with a review note, correct first, or send back.
  const blockers = approval.blocking_checks || [], count = unique(blockers);
  const decide = 'Keputusan di tangan Anda: setujui dengan catatan review, koreksi dulu, atau kembalikan ke PIC.';
  if (count && blockers.every(check => check.code.startsWith('TAX_'))) return guide('Cocokkan pilihan dan data pajak',
    `Data pajak belum sesuai dengan pilihan yang tersimpan. Baca sarannya di bagian pajak. ${decide}`,
    'tax', 'Buka bagian pajak', 'attention');
  if (count && approval.can_approve) return guide(`${count} kendala untuk dicek`,
    (blockers.some(check => check.code === 'POSSIBLE_DUPLICATE')
      ? 'Ada kandidat duplikat. Bandingkan dengan invoice di antrean supaya tidak dibayar dua kali. '
      : 'Baca saran di tiap kendala. ') + decide,
    'checks', 'Lihat kendala dan saran', 'attention');
  if (approval.can_approve) {
    const sources = unique(approval.source_checks);
    return guide('Siap untuk pemeriksaan akhir Finance', sources
      ? `${sources} pemeriksaan sumber memerlukan konfirmasi langsung terhadap dokumen. Setelah seluruh data benar, pilih Setujui.`
      : 'Cocokkan seluruh halaman, rekening dan nominal dengan dokumen. Setelah benar, pilih Setujui.',
    'checks', 'Lihat pemeriksaan sumber');
  }
  return guide('Persetujuan belum tersedia', approval.reason || 'Periksa status dan kewenangan akun sebelum melanjutkan.',
    'checks', 'Lihat pemeriksaan', 'attention');
};

window.amigaReviewChecks = detail => {
  const approval = detail.approval || {}, all = detail.draft?.validation?.checks || [];
  const sources = approval.source_checks || [];
  const sourceCodes = new Set(sources.map(check => check.code));
  const blockers = approval.blocking_checks || all.filter(check => check.blocking && !sourceCodes.has(check.code));
  const failed = list => list.filter(check => check.status !== 'PASSED');
  return { blockers: failed(blockers), sources: failed(sources),
    notes: all.filter(check => !check.blocking && check.status !== 'PASSED' && !check.code.startsWith('TAX_')) };
};

// Advice per check, from the invoice's own numbers and never from a model. A suggestion only fills the form: Finance
// still saves the correction and decides (15 Okt 2026, Aldian: "decision tetap di human"). Amounts stay exact as cents.
window.amigaCheckHint = (() => {
  const decimal = value => {
    const match = /^(-?)(\d+)(?:\.(\d*))?$/.exec(String(value ?? '').trim());
    if (!match) return null;
    const fraction = (match[3] || '').replace(/0+$/, '');
    const digits = BigInt(match[2] + fraction);
    return { value: match[1] ? -digits : digits, scale: fraction.length };
  };
  // Cents, or null when the amount is missing, malformed, or finer than a cent.
  const cents = value => {
    const parsed = decimal(value);
    if (!parsed || parsed.scale > 2) return null;
    return parsed.value * 10n ** BigInt(2 - parsed.scale);
  };
  const optional = value => value == null || value === '' ? 0n : cents(value);
  const rupiah = amount => {
    const negative = amount < 0n, absolute = negative ? -amount : amount, fraction = absolute % 100n;
    return (negative ? '-Rp ' : 'Rp ') + (absolute / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
      + (fraction ? ',' + fraction.toString().padStart(2, '0') : '');
  };
  // The form's own canonical spelling (numbers.js): no grouping, a dot only for real cents.
  const plain = amount => {
    const negative = amount < 0n, absolute = negative ? -amount : amount, fraction = absolute % 100n;
    return (negative ? '-' : '') + (absolute / 100n) + (fraction ? '.' + fraction.toString().padStart(2, '0') : '');
  };
  const lineSum = invoice => {
    const totals = (invoice.line_items || []).map(item => cents(item.stated_line_total));
    return totals.length && totals.every(total => total != null) ? totals.reduce((a, b) => a + b, 0n) : null;
  };
  // quantity x price at the combined scale, kept only when it lands on whole cents.
  const product = item => {
    const quantity = decimal(item?.quantity), price = decimal(item?.unit_price);
    if (!quantity || !price) return null;
    const scale = quantity.scale + price.scale, value = quantity.value * price.value;
    const unit = scale > 2 ? 10n ** BigInt(scale - 2) : 1n;
    if (scale > 2 && value % unit) return null;
    return scale > 2 ? value / unit : value * 10n ** BigInt(2 - scale);
  };
  // The unit price that makes quantity x price equal a line total, or null when it does not land on whole cents.
  const unitFor = (item, total) => {
    const quantity = decimal(item?.quantity);
    if (!quantity || quantity.value <= 0n) return null;
    const scaled = total * 10n ** BigInt(quantity.scale);
    return scaled % quantity.value ? null : scaled / quantity.value;
  };
  // A price that already holds the PPN (SIPLah, 16 Okt 2026): the products add up to subtotal plus PPN while the line
  // totals add up to the subtotal. Copying a product into its line total would count the PPN twice.
  const taxedPrices = invoice => {
    const tax = cents(invoice.stated_tax_total), stated = cents(invoice.stated_subtotal);
    const products = (invoice.line_items || []).map(product);
    if (!tax || tax <= 0n || stated == null || lineSum(invoice) !== stated || !products.length
      || products.some(value => value == null)) return null;
    const gross = products.reduce((a, b) => a + b, 0n);
    return gross === stated + tax ? { gross, stated, tax } : null;
  };
  const photo = detail => String(detail.media_type || '').startsWith('image/');

  function total(invoice) {
    const sum = lineSum(invoice), discount = optional(invoice.stated_discount_total);
    const other = optional(invoice.stated_other_charges_total), tax = optional(invoice.stated_tax_total);
    const stated = cents(invoice.stated_total);
    if ([sum, discount, other, tax, stated].some(value => value == null)) return null;
    const calculated = sum - discount + other + tax, gap = stated - calculated;
    const text = `Hitungan: jumlah item ${rupiah(sum)} − diskon ${rupiah(discount)} + biaya lain ${rupiah(other)}`
      + ` + PPN ${rupiah(tax)} = ${rupiah(calculated)}. Total tertulis ${rupiah(stated)}, selisih ${rupiah(gap < 0n ? -gap : gap)}.`;
    if (gap === 0n) return { text };
    if (discount > 0n && gap === 2n * discount) return { text,
      advice: `${rupiah(discount)} kemungkinan biaya tambahan, bukan diskon. Kalau benar, Diskon jadi Rp 0 dan Biaya lain jadi ${rupiah(other + discount)}.`,
      fill: { stated_discount_total: '0', stated_other_charges_total: plain(other + discount) },
      reason: `${rupiah(discount)} dipindah dari Diskon ke Biaya lain sesuai dokumen.` };
    if (gap > 0n) return { text,
      advice: `Total tertulis ${rupiah(gap)} lebih besar. Kalau dokumen mencantumkan biaya admin, ongkir, atau biaya lain sebesar itu, Biaya lain jadi ${rupiah(other + gap)}.`,
      fill: { stated_other_charges_total: plain(other + gap) },
      reason: `Biaya lain ${rupiah(other + gap)} diisi sesuai dokumen.` };
    if (tax > 0n && -gap === tax) return { text,
      advice: 'Total tertulis tampaknya belum termasuk PPN. Cocokkan Total dan PPN dengan dokumen.' };
    return { text,
      advice: `Total tertulis ${rupiah(-gap)} lebih kecil. Kalau dokumen mencantumkan diskon atau potongan sebesar itu, Diskon jadi ${rupiah(discount - gap)}.`,
      fill: { stated_discount_total: plain(discount - gap) },
      reason: `Diskon ${rupiah(discount - gap)} diisi sesuai dokumen.` };
  }

  function subtotal(invoice) {
    const sum = lineSum(invoice), stated = cents(invoice.stated_subtotal), tax = cents(invoice.stated_tax_total);
    if (sum == null || stated == null) return null;
    if (tax && tax > 0n && sum === stated + tax) {
      // Line totals that hold the PPN: the subtotal is right. One line can be filled; several cannot be split exactly.
      const items = invoice.line_items || [], only = items.length === 1 ? items[0] : null, fill = {};
      if (only) {
        fill['line_items[0].stated_line_total'] = plain(stated);
        const price = product(only) === sum ? unitFor(only, stated) : null;
        if (price != null) fill['line_items[0].unit_price'] = plain(price);
      }
      return { text: `Jumlah total baris item ${rupiah(sum)} sama dengan subtotal ${rupiah(stated)} ditambah PPN ${rupiah(tax)}, jadi total baris sudah termasuk PPN.`,
        advice: 'Subtotal sudah benar, jangan diubah supaya PPN tidak terhitung dua kali. Isi total baris dengan nilai sebelum PPN dari dokumen.',
        ...(only ? { fill, reason: 'Total baris diisi nilai sebelum PPN; subtotal tetap.' } : {}) };
    }
    return { text: `Jumlah total baris item ${rupiah(sum)}, subtotal tertulis ${rupiah(stated)}.`,
      advice: `Kalau semua item sudah benar, subtotal seharusnya ${rupiah(sum)}.`,
      fill: { stated_subtotal: plain(sum) }, reason: 'Subtotal disamakan dengan jumlah total baris item.' };
  }

  function lines(invoice, fields) {
    const found = fields.map(field => /^line_items\[(\d+)\]$/.exec(field || '')).filter(Boolean).map(match => {
      const index = Number(match[1]), item = invoice.line_items?.[index];
      const expected = product(item), stated = cents(item?.stated_line_total);
      if (expected == null || stated == null) return null;
      return { index, expected, stated, quantity: item.quantity, price: cents(item.unit_price), item };
    }).filter(Boolean);
    if (!found.length) return null;
    const taxed = taxedPrices(invoice);
    if (taxed) {
      const fill = Object.fromEntries(found.map(line => [`line_items[${line.index}].unit_price`, unitFor(line.item, line.stated)])
        .filter(([, price]) => price != null).map(([path, price]) => [path, plain(price)]));
      return { text: `Harga satuan tertulis sudah termasuk PPN: kuantitas × harga satuan berjumlah ${rupiah(taxed.gross)}, sama dengan subtotal ${rupiah(taxed.stated)} ditambah PPN ${rupiah(taxed.tax)}.`,
        advice: 'Total baris dan subtotal sudah benar. Isi harga satuan dengan nilai sebelum PPN dari dokumen, supaya PPN tidak terhitung dua kali.',
        ...(Object.keys(fill).length ? { fill, reason: 'Harga satuan diisi nilai sebelum PPN; harga tertulis sudah termasuk PPN.' } : {}) };
    }
    return { text: found.map(line => `Item ${line.index + 1}: ${line.quantity} × ${line.price == null ? '-' : rupiah(line.price)}`
        + ` = ${rupiah(line.expected)}, tertulis ${rupiah(line.stated)}.`).join(' '),
      advice: 'Kalau kuantitas dan harga satuan sudah benar, total baris disamakan dengan hasil kalinya.',
      fill: Object.fromEntries(found.map(line => [`line_items[${line.index}].stated_line_total`, plain(line.expected)])),
      reason: `Total baris item ${found.map(line => line.index + 1).join(', ')} disamakan dengan kuantitas × harga satuan.` };
  }

  return (group, detail, invoice) => {
    const tax = cents(invoice.stated_tax_total), block = detail.draft?.tax || {};
    switch (group.code) {
      case 'TOTAL_MISMATCH': return total(invoice);
      case 'SUBTOTAL_MISMATCH': return subtotal(invoice);
      case 'LINE_TOTAL_MISMATCH': return lines(invoice, group.fields || [group.field]);
      case 'TAX_PPN_CONFLICT': return { text: `Invoice mencantumkan PPN ${tax == null ? '' : rupiah(tax)}, tetapi pilihan pajak tanpa PPN.`,
        advice: 'Kalau PPN memang ditagihkan, pilih pajak dengan PPN. Kalau tetap tanpa PPN, tulis alasannya di catatan review.',
        tax: { ppn: true }, reason: 'Pilihan pajak ditambah PPN karena invoice mencantumkan PPN.' };
      case 'TAX_PPN_MISSING': return { text: 'PPN dipilih, tetapi PPN tertulis kosong atau 0.',
        advice: block.ppn_origin === 'INTERNAL_ADJUSTMENT'
          ? 'Tambahan PPN dicatat terpisah. Periksa alasan, status PKP, dan tindak lanjut invoice revisi serta faktur vendor.'
          : 'Periksa dokumen. Bila PPN perlu ditambahkan di atas total invoice, gunakan pilihan tambahan PPN dan tulis alasannya; jangan mengubah angka sumber.' };
      case 'TAX_PPN_DIFFERENT': return block.ppn_expected == null ? null : {
        text: `PPN menurut hitungan faktur ${rupiah(cents(block.ppn_expected))}, PPN tertulis ${tax == null ? 'kosong' : rupiah(tax)}.`,
        advice: 'Yang berlaku angka di faktur pajak. Cocokkan PPN tertulis dengan fakturnya.' };
      case 'BANK_MISMATCH': return { text: `Rekening ${invoice.payment?.account_number || '-'} belum ada di master vendor ini.`,
        advice: 'Cocokkan dengan dokumen. Kalau vendor memang berganti rekening, minta konfirmasi tertulis vendor sebelum menyetujui.' };
      case 'POSSIBLE_DUPLICATE': return { text: 'Ada invoice lain dengan vendor dan nomor invoice yang sama di klien ini.',
        advice: 'Bandingkan di antrean supaya tidak dibayar dua kali.' };
      case 'OCR_INCOMPLETE': case 'VISUAL_REVIEW_REQUIRED': case 'SOURCE_EVIDENCE_INVALID':
        return photo(detail) ? { text: 'Dokumen ini foto, jadi AI tidak punya teks untuk dicocokkan.',
          advice: 'Cocokkan tiap isian dengan gambar, terutama nomor invoice, nomor rekening, dan angka.' } : null;
      default: return null;
    }
  };
})();
