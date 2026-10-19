---
sop_id: EXC-VOUCHER_RENDER_INTERRUPTED
kategori: exception
kode: VOUCHER_RENDER_INTERRUPTED
tahap: voucher
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/review.py recover dan retry; app/service.py Worker.run; app/static/app.js renderDecision dan renderHistory; app/README.md ketahanan voucher; acceptance AC-18
---

# VOUCHER_RENDER_INTERRUPTED: pembuatan PDF voucher terputus

**Ringkasnya.** Server atau worker berhenti saat PDF draf atau voucher final sedang dibuat. Saat worker hidup lagi, PDF itu ditandai gagal dan tidak diulang otomatis. Persetujuan dan nomor voucher tetap tersimpan.

**Pesan di layar.** Sebelum server hidup lagi, label tetap "Membuat draf voucher…" atau "Membuat voucher final…". Sesudahnya kartu menulis "Draf belum berhasil dibuat. Persetujuan Finance tetap tersimpan." atau "Voucher final belum berhasil dibuat. Persetujuan tetap tersimpan." Riwayat mencatat "Pembuatan draf voucher gagal" atau "Pembuatan voucher final gagal", dengan alasan bahwa render terputus dan dapat diulang.

**Istilah lain.** pembuatan voucher terputus, server restart saat membuat voucher, voucher berhenti di tengah, PDF voucher tidak selesai.

**Langkah penanganan**
1. Finance Reviewer mengisi "Alasan pembuatan ulang PDF", misalnya bahwa server sempat dimulai ulang.
2. Tekan "Ulangi pembuatan PDF". Data, persetujuan, template, dan nomornya sama dengan sebelum terputus.
3. Kalau tetap gagal, penyebabnya bisa file yang bentrok, yaitu VOUCHER_FILE_CONFLICT. Laporkan ke Tech Lead beserta nomor voucher.

**Dilarang.** Mengoreksi data invoice supaya voucher dibuat ulang. Mengulang pembuatan PDF sudah cukup dan tetap memakai nomor yang sama.

**Selesai kalau.** Label menjadi "Draf resmi, disetujui Finance" atau "Disetujui Finance dan manajer keuangan", dan voucher bisa diunduh.

**Bedanya dengan.** PROCESS_INTERRUPTED terjadi saat ekstraksi invoice. Kode ini terjadi saat membuat PDF voucher sesudah persetujuan.

**Pertanyaan umum.** Apakah nomor voucher berubah sesudah diulang? Tidak. Nomor, data, dan template dibekukan saat Finance menyetujui.

Aturan: batasan teknis PoC.
