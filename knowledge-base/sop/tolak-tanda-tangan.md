---
sop_id: TOLAK-TANDA-TANGAN
kategori: penolakan
tahap: persetujuan, voucher
peran: finance-reviewer, amiga-director
status_aturan: poc-teknis
sumber: app/review.py verify_signer, signature_state, director_approve, dan download_signed; app/signing.py SignatureGuard; app/service.py edit; app/static/app.js renderDecision, openSign, toast, dan submit persetujuan; app/static/index.html dialog persetujuan; app/tests/test_signoff.py
---

# Persetujuan ditolak: arti pesan dan tindakannya

**Ringkasnya.** Persetujuan tidak tersimpan, jadi status dan voucher tidak berubah. Pesannya tampil di dialog persetujuan, kecuali disebut lain. Kalau ada konflik, dialog tertutup sendiri. Pesannya muncul di bawah layar, lalu layar dimuat ulang.

- CONSENT_REQUIRED, "Centang pernyataan sebelum menyetujui." Jarang terlihat, karena "Setujui" nonaktif sebelum pernyataan dicentang.
- SIGNATURE_PASSWORD_INVALID, "Password tidak cocok. Persetujuan dibatalkan." Ketik ulang password akunmu sendiri. Riwayat mencatat "Persetujuan ditolak: password salah" tanpa passwordnya.
- SIGNATURE_RATE_LIMIT, "Terlalu banyak percobaan persetujuan. Coba lagi 10 menit lagi." Muncul sesudah 5 password salah dalam 10 menit. Tunggu, jangan menebak.
- VOUCHER_TEMPLATE_UNSUPPORTED, "Voucher lama ini belum punya kotak Manajer Keuangan." Tombol "Setujui" manajer keuangan nonaktif. Manajer keuangan menekan "Kembalikan ke Finance", lalu Finance menyetujui ulang dengan nomor baru.
- CONTENT_MISMATCH, "Isi voucher tidak cocok dengan persetujuan Finance." Jangan dipaksa. Laporkan ke Tech Lead sebagai masalah integritas.
- REVIEWER_SIGNATURE_MISSING, "Persetujuan Finance belum ada." Data persetujuan tidak lengkap. Laporkan ke Tech Lead.
- AMIGA_APPROVED_LOCKED, "Voucher sudah disetujui manajer keuangan, jadi datanya tidak bisa dikoreksi lagi." Muncul saat koreksi disimpan dari layar lama, padahal manajer keuangan sudah menyetujui. Isinya terkunci. Muat ulang invoice.
- VOUCHER_NOT_SIGNED, "Voucher ini belum disetujui manajer keuangan." Voucher final belum ada. Pakai "Unduh draf ↓".

**Pertanyaan umum.** Password persetujuan sama dengan password masuk? Ya. Password diminta ulang supaya persetujuan hanya bisa dibuat pemilik akun, saat itu juga.
