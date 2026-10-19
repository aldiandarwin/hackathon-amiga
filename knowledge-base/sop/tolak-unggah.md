---
sop_id: TOLAK-UNGGAH
kategori: penolakan
tahap: intake
peran: pic-klien, intake-support, finance-reviewer
status_aturan: poc-teknis
sumber: app/batches.py create dan receive; app/service.py inspect_pdf dan intake; app/static/app.css role-director; app/settings.py:26-28; web/lib/upload.ts PROBLEM_NOTES dan progressOf; web/app/unggah/page.tsx; app/schema.sql:6; app/README.md multiple upload; output/app-stage4/VERIFICATION.md
---

# File invoice ditolak: arti pesan dan tindakannya

**Ringkasnya.** File ditolak sebelum diproses, jadi tidak ada request baru dan tidak ada biaya AI. Di Progres unggahan, file itu berlabel "Ditolak" beserta alasannya. File lain dalam batch yang sama tetap diproses.

- FILE_TOO_LARGE, "Ukuran file maksimal 5 MB." Daftar file sudah menandainya lebih dari 5 MB sebelum diunggah. Kecilkan ukuran PDF atau foto tanpa mengorbankan keterbacaan.
- PAGE_LIMIT, "Satu invoice maksimal 5 halaman." Penanganan invoice di atas 5 halaman belum diputuskan dan belum punya pemilik tercatat.
- ENCRYPTED_PDF, "Gunakan PDF tanpa kata sandi." Minta versi PDF tanpa kata sandi.
- INVALID_DOCUMENT, misalnya "File kosong tidak dapat diproses.", "Pilih invoice berupa PDF, JPG, atau PNG.", atau "PDF tidak dapat dibaca. Periksa atau ekspor ulang dokumennya." File kosong, rusak, atau bukan PDF maupun foto. Ekspor ulang sebagai PDF tanpa kata sandi, atau foto ulang.
- INVALID_FILENAME, "Nama file harus berakhiran .pdf, .jpg, .jpeg, atau .png dan maksimal 180 karakter." Biasanya nama file terlalu panjang atau akhirannya tidak cocok dengan isinya. Ganti nama filenya.
- FORBIDDEN, "Unggah invoice hanya untuk PIC Intake." Hanya PIC yang mengunggah. Akun Finance dan Manajer Keuangan AMIGA mendapat menu "Persetujuan", bukan menu unggah.
- "Pilih klien dulu." Kolom Klien di halaman unggah masih kosong. Pilih kliennya, lalu unggah lagi.
- CLIENT_EXISTS saat membuat klien lewat "+ Klien baru", misalnya "sudah dipakai klien lain. Pilih kode lain." Nama atau kode voucher itu sudah ada. Pilih klien lama dari daftar, atau pakai kode lain.

**Pertanyaan umum.** Bagaimana mengunggah ulang file yang sudah diperbaiki? Pakai batch baru. File yang sudah ditolak tidak bisa dikirim ulang ke batch yang sama.
