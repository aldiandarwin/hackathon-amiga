---
sop_id: KTL-VERSI-DATA
kategori: kontrol
tahap: review, persetujuan, voucher, audit
peran: finance-reviewer
status_aturan: brief-v2.0
sumber: app/service.py snapshot dan edit; app/review.py approve, director_approve, director_return, dan download; app/schema.sql triggers; app/static/app.js dateTime, renderHistory, loadDetail, dan submit koreksi; arsitektur §7; acceptance AC-07, AC-15, dan AC-17
---

# Versi data: setiap koreksi membuat versi baru

**Aturan.**
- Hasil AI awal disimpan sebagai versi 1 dan tidak pernah ditimpa.
- Setiap koreksi yang disimpan membuat versi baru, lengkap dengan pengubah, waktu, alasan, serta nilai sebelum dan sesudah. Tab "Riwayat perubahan" menampilkan semua catatan itu, lengkap dengan tanggal dan jam.
- Persetujuan berlaku untuk satu versi. Voucher dibuat dari salinan data versi itu, bukan dari draf terbaru.
- Koreksi sesudah persetujuan Finance membatalkan approval dan menonaktifkan voucher lama, yang tetap tersimpan sebagai riwayat. Status biasanya menjadi "Perlu perhatian". Voucher baru bernomor baru dibuat sesudah versi baru disetujui.
- Pengembalian manajer keuangan menyalin versi yang disetujui menjadi versi baru. Sesudah "Disetujui manajer keuangan", koreksi ditolak dengan AMIGA_APPROVED_LOCKED.

**Alasan.** Auditor dan reviewer harus bisa melihat apa yang diubah manusia dari hasil AI, dan kenapa.

**Cara sistem menegakkan.** Saat menyimpan koreksi atau menyetujui, aplikasi mengirim nomor versi yang sedang dibuka. Kalau sudah ada versi lebih baru, permintaan ditolak dengan VERSION_CONFLICT. Database menolak perubahan dan penghapusan versi lama, riwayat, keputusan persetujuan, langkah persetujuan, dan isi voucher.

**Pertanyaan umum.** Dua orang mengedit invoice yang sama, siapa yang menang? Yang menyimpan duluan. Yang kedua ditolak dan melihat "Versi berubah di sesi lain. Salin koreksi sebelum memuat ulang."
