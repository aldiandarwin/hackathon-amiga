---
sop_id: ALUR-JEJAK-AUDIT
kategori: alur
tahap: audit
peran: pic-klien, finance-reviewer, service-lead, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 8 layar 05 dan hal. 9 skenario 7; BRD epic 2; app/schema.sql triggers dan approval_steps; app/static/app.js dateTime dan renderHistory; app/service.py intake, detail, edit, process_next, dan Worker.run; app/review.py verify_signer, approve, retry, render_draft, render_signoff, director_approve, director_return, dan recover; app/batches.py receive; acceptance AC-07, AC-22, dan AC-23
---

# Jejak audit dan riwayat perubahan invoice

**Tujuan.** Menyimpan catatan permanen tentang siapa melakukan apa, kapan, dan kenapa, sehingga setiap koreksi, persetujuan, dan pengembalian bisa ditelusuri.

**Siapa.** Sistem mencatat otomatis. Semua akun yang ditugaskan ke klien itu bisa membaca riwayatnya.

**Prasyarat.** Tidak ada. Pencatatan berjalan sejak invoice diunggah.

**Langkah**
1. Buka invoice, lalu pilih tab "Riwayat perubahan".
2. Baca kejadiannya, misalnya "Invoice diunggah", "Invoice masuk melalui batch", "Ekstraksi selesai", "Data invoice dikoreksi", "Ekstraksi dihentikan", "Review Finance disetujui", "Draf voucher tersedia", "Persetujuan ditolak: password salah", "Disetujui manajer keuangan", "Dikembalikan manajer keuangan ke Finance", "Approval perlu diperbarui", "Voucher final tersedia", atau "Pembuatan draf voucher gagal".
3. Pada koreksi, lihat nama pengubah, tanggal dan jam, versi, alasan, serta nilai sebelum dan sesudah.

**Hasil.** Tujuannya riwayat yang siap untuk pemeriksaan internal maupun eksternal. Di PoC, layar memuat 100 kejadian terbaru dan belum ada ekspor.

**Kontrol.** Riwayat, versi data, keputusan persetujuan, dan langkah persetujuan tidak bisa diubah atau dihapus lewat aplikasi. Tiap persetujuan menyimpan kode verifikasi dan hash isi voucher. Password yang salah tidak ikut tercatat. Nilai kosong ditampilkan sebagai Kosong. Penolakan final belum ada di PoC.

**Pertanyaan umum.** Bisakah saya menghapus koreksi yang salah? Tidak. Finance Reviewer membuat koreksi baru dengan alasan yang menjelaskan perbaikannya. Kalau Finance sudah menyetujui, koreksi itu membatalkan approval aktif. Sesudah "Disetujui manajer keuangan", koreksi ditolak. Riwayat lama tetap tersimpan.
