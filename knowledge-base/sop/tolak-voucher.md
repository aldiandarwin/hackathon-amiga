---
sop_id: TOLAK-VOUCHER
kategori: penolakan
tahap: voucher, serah_terima
peran: finance-reviewer, pic-klien, amiga-director
status_aturan: poc-teknis
sumber: app/review.py retry, download, download_signed, dan read_pdf; app/main.py ReviewAction, validation_error, retry_voucher, voucher, dan signed_voucher; app/static/app.js renderDecision dan submit render ulang; app/README.md ketahanan voucher
---

# Unduh atau ulang voucher ditolak: arti pesan dan tindakannya

**Ringkasnya.** Pesan ini muncul saat mengunduh draf atau voucher final, atau saat mengulang pembuatan PDF. Persetujuan yang sudah tersimpan tidak berubah. Kalau unduhan ditolak, tab itu berganti menjadi teks berisi kode dan pesannya. Tekan tombol kembali di browser, lalu buka ulang invoice.

Saat mengunduh:
- VOUCHER_SUPERSEDED, "Versi ini belum disetujui atau voucher lama sudah tidak aktif." Invoice sudah dikoreksi atau dikembalikan. Voucher baru ada sesudah versi terbaru disetujui.
- VOUCHER_NOT_READY, "Voucher belum selesai dibuat." atau "Salinan final belum selesai dibuat." Tunggu sampai tombol unduhnya muncul.
- VOUCHER_NOT_SIGNED, "Voucher ini belum disetujui manajer keuangan." Voucher final belum ada. Unduh drafnya.
- VOUCHER_UNAVAILABLE, "File voucher tidak tersedia; hubungi pengelola." File PDF tidak ditemukan di penyimpanan. Laporkan ke Tech Lead.
- VOUCHER_CHANGED, "Integritas file voucher tidak sesuai." File berubah sejak dibuat. Laporkan ke Tech Lead sebagai masalah integritas.

Saat mengulang pembuatan PDF:
- INVALID_TRANSITION, "Hanya render yang gagal dapat diulang." PDF sudah jadi atau sedang dibuat. Buka ulang invoice.
- VOUCHER_SUPERSEDED, "Voucher tidak lagi aktif." atau VERSION_CONFLICT, "Voucher tidak lagi aktif untuk versi ini." Invoice sudah dikoreksi atau dikembalikan.
- INVALID_PAYLOAD, "Data permintaan tidak valid." Alasan render ulang kurang dari 5 karakter sesudah spasi dibuang.
- FORBIDDEN jarang terlihat, karena formulirnya hanya tampil untuk Finance Reviewer.

**Pertanyaan umum.** Link voucher lama yang saya simpan tidak bisa dibuka lagi? Benar. Sesudah koreksi atau pengembalian, voucher lama tidak aktif dan unduhannya ditolak, walau arsipnya tetap tersimpan.
