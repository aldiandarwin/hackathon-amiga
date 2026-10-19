---
sop_id: TOLAK-AKSES-SESI
kategori: penolakan
tahap: antrean, review
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/main.py login, session, origin, document, dan preview; app/database.py sesi 8 jam dan seed penugasan; app/service.py document_path, preview, dan detail; app/static/app.js api, showLogin, dan loadDetail; output/preparation/api-contract-draft.md state dan error
---

# Akses dan sesi ditolak: arti pesan dan tindakannya

**Ringkasnya.** Pesan ini muncul saat masuk, saat sesi habis, atau saat membuka data yang tidak boleh diakses.

- LOGIN_FAILED, "Email atau kata sandi tidak cocok." Periksa lagi email dan kata sandi.
- LOGIN_RATE_LIMIT, "Terlalu banyak percobaan. Coba lagi sebentar." Muncul sesudah 10 percobaan dalam 60 detik dari komputer yang sama. Login yang berhasil mengosongkan hitungannya.
- UNAUTHENTICATED. Sesi berlaku paling lama 8 jam sejak masuk. Aplikasi baru kembali ke layar masuk pada permintaan berikutnya ke server, misalnya saat menekan "Simpan koreksi". Koreksi yang belum tersimpan hilang tanpa konfirmasi, dan kadang muncul "Silakan masuk terlebih dahulu." Simpan atau salin koreksi sebelum sesi habis.
- CSRF_REJECTED, "Sesi tidak valid. Muat ulang halaman." Muat ulang halamannya.
- ORIGIN_REJECTED, "Sumber permintaan tidak diizinkan." Buka aplikasi dari alamat resminya.
- NOT_FOUND, misalnya "Request tidak ditemukan." atau "Dokumen tidak tersedia." Datanya tidak ada, atau milik klien yang tidak ditugaskan ke akunmu.
- INVALID_DOCUMENT_PATH. Pesannya sama dengan NOT_FOUND untuk PDF, tapi penyebabnya lokasi file yang tidak sah. Laporkan ke Tech Lead kalau PDF yang seharusnya ada tidak bisa dibuka.
- PREVIEW_FAILED. Di layar, gambar halaman tampil rusak. Pakai tautan "Buka PDF".

**Pertanyaan umum.** Rekan bisa membuka invoice itu, kenapa saya dapat NOT_FOUND? Akunmu tidak ditugaskan ke klien tersebut. Di PoC, penugasan klien adalah data demo yang tetap. Meminta penugasan lewat Service Lead atau System Admin masih prosedur target.
