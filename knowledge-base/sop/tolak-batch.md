---
sop_id: TOLAK-BATCH
kategori: penolakan
tahap: intake
peran: pic-klien, intake-support, finance-reviewer
status_aturan: poc-teknis
sumber: app/batches.py create, detail, authorize_upload, dan receive; app/main.py BatchManifest, create_batch, batch_upload, dan idempotency; web/app/unggah/page.tsx submit, sendPending, dan retryPending; web/lib/upload.ts; app/settings.py:26-28; output/arsip/app/EXECUTION_BATCH.md; output/app-stage4/VERIFICATION.md
---

# Unggahan batch ditolak: arti pesan dan tindakannya

**Ringkasnya.** Pesan ini menyangkut batch secara keseluruhan atau pengiriman ulang file. Alasan penolakan per file seperti ukuran dan jumlah halaman punya kartu sendiri.

- BATCH_LIMIT, "Pilih satu hingga lima file." Satu batch berisi 1 sampai 5 file. Halaman unggah menahannya lebih dulu. Kalau lebih dari lima file, halaman meminta kelebihannya dihapus. Kalau belum ada file, halaman meminta minimal satu file invoice.
- MANIFEST_MISMATCH, "File berbeda dari pilihan awal; pilih ulang sebagai batch baru." Isi atau ukuran file yang terkirim tidak sama dengan saat dipilih. Unggah lagi lewat batch baru.
- IDEMPOTENCY_CONFLICT, misalnya "Kunci batch sudah dipakai untuk pilihan file yang berbeda." Tekan "Unggah invoice" sekali lagi untuk memulai unggahan baru.
- IDEMPOTENCY_REQUIRED, "Kunci unggahan tidak valid." Muat ulang halaman, lalu ulangi. Kalau berulang, laporkan ke Tech Lead.
- FORBIDDEN, "Hanya pengunggah batch dapat mengirim file ini." Hanya akun pembuat batch yang bisa melanjutkan file yang belum terkirim.
- Tanpa kode, layar menyebut file pilihan tidak cocok dengan unggahan ini. Artinya file yang dikirim ulang tidak sama dengan file awal. Tekan Unggah invoice lain, lalu mulai unggahan baru.
- Tanpa kode, layar menyebut sebagian file belum terkirim. Koneksi atau server sempat gagal. Tekan Kirim ulang yang belum terkirim. File yang sudah diterima tetap tersimpan.

**Pertanyaan umum.** Ada file berstatus "Belum terkirim", apa yang harus saya lakukan? Selama halaman unggah masih terbuka, pengunggah menekan Kirim ulang yang belum terkirim. Kalau halaman sudah ditutup, unggah lagi file itu sebagai unggahan baru.
