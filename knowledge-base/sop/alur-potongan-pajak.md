---
sop_id: ALUR-POTONGAN-PAJAK
kategori: alur
tahap: intake, review, persetujuan, voucher
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/taxes.py PRESETS, compute, hints, declared_zero; app/review.py assess; app/static/tax.js; app/voucher_pdf.py; prototype/amiga_ocr/validation.py DECLARED_ZERO
---

# Potongan pajak: memilih, menghitung, dan mencetak di voucher

**Tujuan.** Menghitung potongan PPh dan memeriksa PPN sebelum approval, lalu mencetak jumlah dibayarkan di voucher.

**Siapa.** PIC memilih pajak saat unggah. Finance Reviewer memeriksa dan boleh mengubahnya. Angkanya dihitung tabel aturan pajak-poc.v2 di backend, bukan oleh AI.

**Prasyarat.** Total invoice terbaca dan mata uangnya IDR.

**Langkah**
1. Pilih "Tanpa pajak", "PPN 11% saja", "PPh 23 2% saja", atau "PPN 11% + PPh 23 2%".
2. Kalau ada PPN, nomor faktur dibaca otomatis dari halaman Faktur Pajak. Isi "Nomor faktur pajak" hanya kalau TAX_FAKTUR_NOT_FOUND muncul.
3. Hapus centang "Penerima punya NPWP/NIK" kalau vendor tidak punya. Tarif PPh 23 jadi 4%.
4. Sistem menghitung nilai sebelum PPN, yaitu Total dikurangi PPN tertulis. PPh 23 sebesar 2% dari nilai itu.
5. Baca peringatan per baris, misalnya "Sewa tanah/bangunan biasanya PPh 4(2) final 10%, bukan PPh 23."

**Hasil.** Panel Pajak menampilkan tabel hitungan. Voucher mencetak baris potongan PPh dan TOTAL yang dibayarkan.

**Kontrol.** Approval ditahan dengan pesan "Pilih jenis potongan pajak sebelum menyetujui." sampai pajak dipilih. PPN yang bentrok dengan pilihan hanya menjadi kendala, dan hitungannya memakai PPN tertulis. Tarif dan pembulatan masih asumsi PoC yang menunggu konfirmasi Finance. Kalau pilihan tanpa PPN dan isian Pajak kosong, sistem mencatat DECLARED_ZERO: "Nilai kosong dihitung 0 atas pernyataan pengguna, bukan hasil baca dokumen."

**Pertanyaan umum.** Kenapa PPh 21 dan PPh 4(2) tidak ada di pilihan? Dropdown demo hanya memuat PPh 23 sesuai contoh kasus AMIGA. Pilihan lain menunggu keputusan Finance. Kalau baris invoice menyebut sewa tanah/bangunan, panel memberi peringatan.
