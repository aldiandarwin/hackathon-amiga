---
sop_id: EXC-DUPLICATE_CHECK
kategori: exception
kode: DUPLICATE_CHECK
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:10-15 dan 140-150; app/review.py assess; invoice-data-contract tabel field vendor; app/README.md batas tahap
---

# DUPLICATE_CHECK belum diperiksa: pencarian invoice kembar tidak bisa jalan

**Ringkasnya.** Sistem belum bisa mencari invoice kembar. Biasanya nama vendor tidak cocok dengan master vendor, atau nomor invoice kosong. Statusnya NOT_CHECKED, jadi request menjadi EXCEPTION. Persetujuan tidak tertahan. Kalau statusnya PASSED, pencarian sudah jalan dan tidak menemukan kembaran.

**Pesan di layar.** "Master vendor/riwayat/nomor invoice belum siap."

**Istilah lain.** vendor baru, vendor tidak dikenal, vendor belum terdaftar, cek duplikat tidak jalan.

**Langkah penanganan**
1. Cocokkan "Nama vendor" dan "Nomor invoice" dengan PDF. Koreksi kalau AI salah baca.
2. Ingat, nama vendor dicocokkan persis. Beda huruf besar kecil tidak masalah, tapi beda tanda baca seperti PT dan PT. sudah dianggap vendor lain.
3. Kalau vendor memang baru, PIC mendaftarkannya saat menekan "Ajukan ke Finance". Pemeriksaan duplikasi lalu jalan ulang, termasuk terhadap invoice lama vendor itu.

**Dilarang.** Mengganti nama vendor dengan ejaan master yang berbeda dari PDF. Nama vendor harus sesuai tulisan di invoice.

**Selesai kalau.** Vendor dikenali master dan nomor invoice terisi, sehingga pemeriksaan duplikasi bisa jalan.

**Bedanya dengan.** POSSIBLE_DUPLICATE berarti pemeriksaan sudah jalan dan menemukan kandidat kembar.

**Sering muncul bersama.** BANK_UNVERIFIED, karena verifikasi rekening juga butuh vendor yang dikenali master.

**Pertanyaan umum.** Vendor baru selalu kena tanda ini? Ya, sampai PIC mendaftarkan vendornya saat mengajukan. Sesudah itu pemeriksaan duplikasi jalan, dan Finance melihat tanda VENDOR_NEW.

Aturan: demo-rules.v1. Master vendor di PoC berisi data demo plus vendor yang didaftarkan PIC.
