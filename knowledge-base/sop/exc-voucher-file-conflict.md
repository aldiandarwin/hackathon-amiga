---
sop_id: EXC-VOUCHER_FILE_CONFLICT
kategori: exception
kode: VOUCHER_FILE_CONFLICT
tahap: voucher
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/review.py store_pdf, render_draft, dan render_signoff; app/static/app.js renderDecision dan renderHistory; app/README.md ketahanan voucher
---

# VOUCHER_FILE_CONFLICT: file voucher lama dengan isi berbeda menghalangi

**Ringkasnya.** Saat membuat PDF draf atau voucher final, sistem menemukan file voucher yang sudah ada dengan isi berbeda. File itu tidak ditimpa, jadi pembuatan PDF gagal. Persetujuan dan nomor voucher tetap tersimpan.

**Pesan di layar.** Sama dengan render gagal biasa: "Draf belum berhasil dibuat. Persetujuan Finance tetap tersimpan." atau "Voucher final belum berhasil dibuat. Persetujuan tetap tersimpan.", dan riwayat "Pembuatan draf voucher gagal" atau "Pembuatan voucher final gagal". Kode ini tersimpan di data voucher dan jejak audit, tapi tidak tampil di layar.

**Istilah lain.** file voucher bentrok, file voucher rusak, ulang render tetap gagal, konflik file PDF voucher.

**Langkah penanganan**
1. Coba "Ulangi pembuatan PDF" sekali, karena layar tidak membedakan kode ini dari render gagal biasa.
2. Kalau tetap gagal, berhenti mengulang dan laporkan ke Tech Lead beserta nomor voucher.
3. Tim teknis memeriksa file yang bentrok. File rusak atau berbeda ditangani operator, bukan ditimpa otomatis.

**Dilarang.** Mengulang pembuatan PDF terus-menerus. Selama file yang bentrok belum ditangani, hasilnya tetap gagal.

**Selesai kalau.** File yang bentrok sudah ditangani tim teknis, lalu pengulangan menghasilkan "Draf resmi, disetujui Finance" atau "Disetujui Finance dan manajer keuangan".

**Bedanya dengan.** VOUCHER_RENDER_FAILED berarti pembuat PDF sendiri yang gagal. Kode ini berarti file hasilnya bentrok dengan file yang sudah ada.

**Pertanyaan umum.** Kenapa sistem tidak menimpa saja file lamanya? File voucher dijaga supaya tidak berubah diam-diam. File yang sudah ada hanya diterima kalau isinya sama persis.

Aturan: batasan teknis PoC.
