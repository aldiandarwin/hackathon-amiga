---
sop_id: FON-ALUR-TUJUH-LANGKAH
kategori: fondasi
tahap: intake, antrean, ekstraksi, validasi, review, persetujuan, voucher, serah_terima, tindak_lanjut
peran: pic-klien, intake-support, robot-admin, finance-reviewer, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 5 alur to-be dan hal. 7 tabel peran; app/static/app.js:6; app/review.py approve, director_approve, dan director_return; app/database.py seed akun manajer keuangan; app/voucher_clean.py render_clean v7; app/README.md alur dan batas tahap; output/app-stage8/VERIFICATION.md
---

# Alur kerja AMIGA dalam tujuh langkah

**Ringkasnya.** Satu invoice berjalan dari unggah sampai tindak lanjut klien lewat tujuh langkah. Status request berubah sepanjang langkah 2 sampai 7. Persetujuan dan pembayaran klien di langkah 7 tetap terjadi di luar sistem.

1. Intake. PIC Klien atau Backup mengunggah PDF invoice dan melengkapi informasi awal.
2. Antrean. Sistem menerbitkan Request ID dan memasukkan dokumen ke antrean dengan status QUEUED, di layar "Menunggu proses".
3. Ekstraksi AI. Mesin AI membaca isi invoice dan mengisi draf data. Statusnya PROCESSING, di layar "Sedang diproses".
4. Validasi. Aturan bisnis memeriksa angka, duplikasi, dan kelengkapan. Hasilnya READY_FOR_REVIEW atau EXCEPTION, yang tampil "Belum diajukan" sampai PIC mengajukan.
5. Review manusia. PIC mencocokkan data lalu mengajukannya ke Finance. Tim Keuangan AMIGA memeriksa, lalu persetujuannya menghasilkan AMIGA_REVIEWED, di layar "Menunggu manajer keuangan", dan draf voucher resmi.
6. Serah terima. PIC Klien mengunduh voucher PDF resmi, lalu status menjadi SENT_TO_CLIENT.
7. Tindak lanjut eksternal. Menurut brief, persetujuan dan pembayaran dilakukan klien di luar sistem.

**Pertanyaan umum.** Langkah mana yang sudah ada di aplikasi PoC? Langkah 1 sebatas memilih klien lalu unggah 1 sampai 5 file per batch, karena informasi awal lain dan peran Backup masih prosedur target. Langkah 2 sampai 5 sudah jalan, termasuk koreksi, pengajuan PIC, dan persetujuan Finance. Sesudah langkah 5, Manajer Keuangan AMIGA menyetujui voucher final menjadi AMIGA_APPROVED, atau mengembalikannya ke Finance. Tahap ini ekstensi PoC di luar brief. Di langkah 6, voucher final bisa diunduh dan dikirim PIC lewat Telegram, tapi status SENT_TO_CLIENT masih prosedur target. Langkah 7 tetap di luar sistem.
