---
sop_id: EXC-INSUFFICIENT_CALCULATION_EVIDENCE
kategori: exception
kode: INSUFFICIENT_CALCULATION_EVIDENCE
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:57-71 dan 114-134; prototype/amiga_ocr/contracts.py:79-84; app/service.py snapshot dan edit; app/review.py assess; invoice-data-contract tabel field dan validation checks; acceptance AC-11
---

# INSUFFICIENT_CALCULATION_EVIDENCE: angka belum lengkap untuk dihitung

**Ringkasnya.** Sistem belum bisa menghitung karena ada angka yang kosong. Statusnya NOT_CHECKED, dan di demo-rules.v1 status itu tetap menahan request di "Perlu perhatian". Persetujuan tidak tertahan, kecuali Total tagihan kosong.

**Pesan di layar.** Ada tiga jenis pesan: "Angka baris belum lengkap.", "Subtotal tidak dapat diperiksa.", dan "Penyesuaian/total belum lengkap; null tidak diasumsikan nol." Pesan pertama muncul sekali untuk tiap baris yang belum lengkap.

**Istilah lain.** angka kosong, diskon kosong, pajak kosong, perhitungan belum bisa dicek.

**Langkah penanganan**
1. Temukan isian yang kosong: "Kuantitas", "Harga satuan", "Total baris", "Subtotal", "Diskon", "PPN tertulis", atau "Total tagihan sebelum PPh".
2. Kalau angkanya tertulis di PDF tapi terlewat, isi angkanya, misalnya 150.000, lalu simpan dengan alasan.
3. Kalau PDF memang tidak mencantumkan diskon atau pajak, biarkan kosong. Diskon kosong tidak ditandai kalau totalnya cocok tanpa diskon.

**Dilarang.** Mengisi 0 untuk diskon atau pajak yang tidak tertulis. Kosong tidak sama dengan nol.

**Selesai kalau.** Semua angka yang tertulis di PDF sudah terisi. Pajak kosong dihitung 0 hanya kalau pilihan pajak tanpa PPN, dan tercatat DECLARED_ZERO. Angka yang diisi lewat koreksi juga memunculkan tanda kutipan sumber.

**Bedanya dengan.** LINE_TOTAL_MISMATCH, SUBTOTAL_MISMATCH, dan TOTAL_MISMATCH berarti angkanya lengkap tapi hasilnya beda. Kode ini berarti angkanya belum lengkap.

**Pertanyaan umum.** Invoice tanpa baris diskon selalu ditandai? Tidak. Kode ini hanya muncul kalau totalnya tidak cocok tanpa diskon, karena diskon yang terlewat bisa jadi penyebabnya.

Aturan: demo-rules.v1.
