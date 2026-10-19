---
sop_id: TOLAK-KOREKSI
kategori: penolakan
tahap: review
peran: finance-reviewer, pic-klien
status_aturan: poc-teknis
sumber: app/service.py edit; app/main.py Edit, validation_error, dan edit; app/static/app.js updateSave, submit koreksi, dan loadDetail; prototype/amiga_ocr/contracts.py:79-155
---

# Koreksi ditolak: arti pesan dan tindakannya

**Ringkasnya.** Koreksi gagal disimpan, jadi versi data tidak berubah. Sebelum terkirim, tombol "Simpan koreksi" sudah nonaktif kalau akunmu hanya punya akses baca, belum ada perubahan, atau alasan kurang dari 5 karakter.

Pesan yang bisa muncul di bawah tombol:
- VERSION_CONFLICT, "Versi sudah berubah. Muat ulang sebelum menyimpan." Versi yang lebih baru sudah disimpan dari sesi lain, oleh orang lain atau oleh akunmu di tab lain. Salin koreksimu, muat ulang, lalu terapkan lagi.
- INVALID_PAYLOAD, "Periksa format tanggal, angka, rekening dan baris invoice." Tanggal harus YYYY-MM-DD, angka tanpa pemisah ribuan, dan mata uang tiga huruf kapital.

Kode berikut jarang terlihat, karena tombolnya sudah nonaktif lebih dulu:
- REASON_REQUIRED, "Tuliskan alasan koreksi minimal 5 karakter."
- NO_CHANGES, "Tidak ada perubahan untuk disimpan."
- FORBIDDEN, "Koreksi hanya tersedia untuk PIC Intake dan Finance Reviewer."
- INTAKE_LOCKED, "Invoice sudah diajukan ke Finance. Koreksi berikutnya oleh Finance." PIC mengoreksi selama invoice belum diajukan. Sesudah diajukan, koreksi menjadi tugas Finance.
- AMIGA_APPROVED_LOCKED, "Voucher sudah disetujui manajer keuangan, jadi datanya tidak bisa dikoreksi lagi." Sesudah "Disetujui manajer keuangan", isian terkunci karena isinya sudah disetujui Finance dan Manajer Keuangan AMIGA.

**Pertanyaan umum.** Koreksi saya hilang sesudah VERSION_CONFLICT? Koreksi yang belum tersimpan tidak masuk sistem. Salin dulu sebelum memuat ulang, sesuai pesan "Versi berubah di sesi lain. Salin koreksi sebelum memuat ulang."
