---
sop_id: PERAN-SYSTEM-ADMIN
kategori: peran
tahap: audit
peran: system-admin
status_aturan: brief-v2.0
sumber: brief hal. 7 tabel peran; prototype/amiga_ocr/validation.py:172-173; app/review.py approve; arsitektur §3 dan §8; acceptance AC-20; app/schema.sql:6; app/database.py seed akun; app/service.py edit
---

# Peran System Admin

Peran ini masih prosedur target. Aplikasi PoC baru mengenal peran PIC, Finance Reviewer, dan Manajer Keuangan AMIGA.

**Tanggung jawab.** Mengelola akun, hak akses, dan pengaturan data klien.

**Boleh**
- Membuat dan menonaktifkan akun pengguna.
- Mengatur peran dan penugasan klien.
- Mengelola konfigurasi data klien. Di PoC, PIC sudah bisa membuat klien baru untuk timnya lewat "+ Klien baru", dan klien itu langsung ditugaskan ke tim tersebut serta Manajer Keuangan AMIGA.

**Tidak boleh**
- Menyetujui transaksi atau voucher, walau juga memegang peran FINANCE_REVIEWER. Aturan ini baru ada di kontrak prototipe. Di aplikasi PoC, persetujuan hanya untuk Finance Reviewer dan Manajer Keuangan AMIGA, dan peran SYSTEM_ADMIN belum ada.
- Mengubah atau menghapus riwayat audit lewat aplikasi.

**Layar dan status.** Bekerja di panel pengelolaan akun dan peran, yang belum ada di aplikasi PoC.

**Pertanyaan umum.** Akun saya tidak bisa mengunggah atau mengoreksi, ke siapa saya minta? Pada prosedur target, ke System Admin. Di PoC, akun dan tim adalah data demo tetap. PIC mengoreksi data selama invoice belum diajukan. Sesudah diajukan, koreksi menjadi tugas Finance Reviewer.
