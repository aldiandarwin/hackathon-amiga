---
sop_id: ALUR-VOUCHER-SERAH-TERIMA
kategori: alur
tahap: voucher, serah_terima
peran: pic-klien, finance-reviewer, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 5, 6, dan 8 layar 04; arsitektur §7, §9, dan §12; app/review.py voucher_number, approve, metadata, render_draft, render_signoff, download, dan download_signed; app/voucher_clean.py render_clean v7; app/static/app.js renderDecision dan showDoc; output/app-stage8/performa.json PERF-03; output/app-stage8/VERIFICATION.md; acceptance AC-17, AC-18, dan AC-23
---

# Voucher PDF: draf, voucher final, dan serah terima

Draf dan voucher final sudah ada di aplikasi PoC. PIC mengirim voucher final ke klien lewat "Hubungi klien". Status SENT_TO_CLIENT masih prosedur target.

**Tujuan.** Membuat voucher dari data yang disetujui, lalu menyerahkannya ke klien.

**Siapa.** Sistem membuat voucher otomatis. Semua akun yang ditugaskan ke klien itu bisa mengunduhnya. Hanya Finance Reviewer yang bisa mengulang PDF yang gagal.

**Prasyarat.** Finance sudah menyetujui, jadi status "Menunggu manajer keuangan" atau "Disetujui manajer keuangan".

**Langkah**
1. Buka tab "Voucher & persetujuan". Tunggu label "Draf resmi, disetujui Finance", lalu tekan "Unduh draf ↓".
2. Sesudah manajer keuangan menyetujui, tunggu label "Disetujui Finance dan manajer keuangan", lalu tekan "Unduh voucher final ↓".
3. Cek nomor, nominal, terbilang, dan rekening.
4. Cetak voucher final. PIC, Finance, dan manajer keuangan tanda tangan basah di tiga kotaknya.

**Hasil.** Nomor voucher berisi kode klien, nomor urut 5 digit, bulan, dan tahun, misalnya ARS-00001-10-2026. Draf berlabel "DRAF - MENUNGGU MANAJER KEUANGAN". Voucher final berlabel "FINAL - DISETUJUI", dengan tiga kotak tanda tangan basah dan QR verifikasi.

**Kontrol.** Voucher memakai data yang dibekukan saat Finance menyetujui. Gagal render tidak membatalkan persetujuan dan bisa diulang tanpa nomor baru. Koreksi atau pengembalian menonaktifkan voucher lama, yang tetap tersimpan sebagai riwayat. Persetujuan berikutnya memberi nomor baru. Uji tahap 8: draf jadi maksimal 0,86 detik, target 3 detik.

**Pertanyaan umum.** Apakah voucher final berarti tagihan sudah dibayar? Tidak. Klien menyetujui dan membayar di luar aplikasi. Template dan penomoran final belum diputuskan, pemilik: AMIGA dan Finance.
