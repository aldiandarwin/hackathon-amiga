---
sop_id: ALUR-TINDAK-LANJUT-EKSTERNAL
kategori: alur
tahap: tindak_lanjut
peran: amiga-director, pic-klien
status_aturan: brief-v2.0
sumber: brief hal. 5 langkah 7 dan hal. 7 tabel peran, Client Approver di luar aplikasi; BRD 3 out-of-scope pembayaran; app/voucher_clean.py render_clean v7; app/signing.py DIRECTOR_CONSENT; app/verify_page.py; app/review.py verification; app/main.py verification_page; app/database.py seed akun; app/tests/test_signoff.py verifikasi publik
---

# Tindak lanjut eksternal: persetujuan dan pembayaran oleh klien

**Tujuan.** Menjelaskan apa yang terjadi sesudah Manajer Keuangan AMIGA menyetujui voucher final, dan batas tanggung jawab AMIGA.

**Siapa.** Pihak klien yang berwenang menyetujui pembayaran di luar aplikasi. Pembayarannya dilakukan perusahaan klien sendiri.

**Prasyarat.** Status "Disetujui manajer keuangan", dan voucher final berlabel "Disetujui Finance dan manajer keuangan".

**Langkah**
1. PIC Klien mengunduh voucher final lewat "Unduh voucher final ↓", mencetaknya untuk tiga tanda tangan basah, lalu menyerahkannya ke klien.
2. Bagian pembayaran klien bisa mengecek keasliannya lewat kode QR atau halaman verifikasi. Halaman itu terbuka tanpa akun. Voucher final yang berlaku tertulis "Sah. Disetujui Finance dan Manajer Keuangan AMIGA. Tanda tangan basah ada di voucher cetak."
3. Klien menyetujui pembayaran, lalu membayar vendor di luar sistem AMIGA.

**Hasil.** Persetujuan dan pembayaran klien tidak tercatat di AMIGA Robot Admin. Status tetap "Disetujui manajer keuangan".

**Kontrol.** AMIGA tidak mentransfer dana. Pernyataan Manajer Keuangan AMIGA saat menyetujui menegaskan "Persetujuan dan pembayaran oleh klien tetap dilakukan di luar aplikasi AMIGA." Halaman verifikasi sengaja tidak menampilkan nominal, rekening, atau vendor. Keaslian dicek dari jejak persetujuan di aplikasi, hash isi, dan QR.

**Pertanyaan umum.** Apakah klien ikut menyetujui di aplikasi? Tidak. Persetujuan akhir milik Manajer Keuangan AMIGA. Menurut brief, approver di pihak klien bekerja di luar aplikasi. Di data demo, klien tidak punya akun.
