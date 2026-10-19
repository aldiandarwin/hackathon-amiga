---
sop_id: EXC-VOUCHER_RENDER_FAILED
kategori: exception
kode: VOUCHER_RENDER_FAILED
tahap: voucher
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/review.py render_draft, render_signoff, signature_state, dan retry; app/static/app.js renderDecision dan renderHistory; app/static/index.html formulir render ulang; app/README.md ketahanan voucher; acceptance AC-18
---

# VOUCHER_RENDER_FAILED: PDF voucher gagal dibuat

**Ringkasnya.** Persetujuan sudah tersimpan, tapi pembuat PDF gagal membuat draf atau voucher final. Persetujuan, nomor voucher, dan status tetap tersimpan. Hanya file PDF-nya yang belum ada. Selama draf belum jadi, manajer keuangan belum bisa menyetujui.

**Pesan di layar.** Kartu draf menulis "Draf belum berhasil dibuat. Persetujuan Finance tetap tersimpan." Kartu final menulis "Voucher final belum berhasil dibuat. Persetujuan tetap tersimpan." Tab "Riwayat perubahan" mencatat "Pembuatan draf voucher gagal" atau "Pembuatan voucher final gagal". Kodenya tidak tampil di layar.

**Istilah lain.** voucher gagal dibuat, PDF voucher tidak jadi, render gagal, tombol unduh voucher tidak muncul.

**Langkah penanganan**
1. Di tab "Voucher & persetujuan", Finance Reviewer mengisi "Alasan pembuatan ulang PDF" minimal 5 karakter.
2. Tekan "Ulangi pembuatan PDF". PDF dibuat ulang dari data dan persetujuan yang sama, dengan nomor yang sama.
3. Kalau tetap gagal, laporkan ke Tech Lead beserta nomor voucher.

**Dilarang.** Mengubah data invoice hanya supaya voucher dibuat ulang. Koreksi membatalkan approval Finance, jadi invoice harus disetujui lagi dengan nomor voucher baru.

**Selesai kalau.** Label menjadi "Draf resmi, disetujui Finance" atau "Disetujui Finance dan manajer keuangan", dan tombol unduhnya muncul.

**Bedanya dengan.** VOUCHER_RENDER_INTERRUPTED berarti server berhenti saat PDF dibuat. VOUCHER_FILE_CONFLICT tampil sama di layar, tapi penyebabnya file lama yang bentrok.

**Pertanyaan umum.** Kenapa PIC dan manajer keuangan tidak melihat formulir ulang? Mengulang pembuatan PDF hanya untuk Finance Reviewer.

Aturan: batasan teknis PoC.
