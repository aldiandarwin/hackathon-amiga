'use strict';
// Presentation only: all amounts come from the server's tax block.
window.amigaPaymentSummary = (detail, dirty = false) => {
  const draft = detail.draft, tax = draft?.tax;
  const computed = tax?.status === 'COMPUTED' && tax.net_payable != null;
  // 15 Okt 2026: open checks no longer hold approval, so Finance sees the amount it would sign for.
  const ready = !dirty && computed;
  const approved = detail.status === 'AMIGA_APPROVED';
  const label = approved ? 'Nominal disetujui pada voucher' : 'Rencana pembayaran ke vendor';
  const note = dirty ? 'Ada koreksi belum disimpan. Simpan untuk memperbarui nominal.'
    : !ready ? 'Lengkapi pilihan pajak dan total tagihan sebelum nominal pembayaran dihitung.' : '';
  return { ready, label, amount: ready ? tax.net_payable : null, note,
    pendingText: dirty ? 'Menunggu koreksi disimpan' : 'Belum dihitung',
    invoiceTotal: draft?.invoice?.stated_total ?? null,
    rows: ready ? [
      { label: 'Nilai barang/jasa sebelum PPN', value: tax.dpp },
      { label: tax.ppn_origin === 'INTERNAL_ADJUSTMENT' ? 'Tambahan PPN di luar invoice' : 'PPN pada invoice', value: tax.ppn_amount, sign: '+' },
      { label: 'Total tagihan sebelum potongan PPh', value: tax.gross_total },
      { label: 'Potongan ' + (tax.pph_id === 'TANPA' ? 'PPh' : tax.pph_short || 'PPh'), value: tax.withheld_total, sign: '−' },
    ] : [] };
};
