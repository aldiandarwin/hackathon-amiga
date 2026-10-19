---
sop_id: EXC-LINE_TOTAL_MISMATCH
kategori: exception
kode: LINE_TOTAL_MISMATCH
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:114-122; prototype/amiga_ocr/contracts.py:79-84; app/static/app.js renderChecks dan renderFields; app/review.py assess; invoice-data-contract keputusan terbuka; app/static/review-guide.js amigaCheckHint
---

# LINE_TOTAL_MISMATCH: qty kali harga satuan tidak sama dengan jumlah baris

**Ringkasnya.** Pada satu baris barang, qty dikali harga satuan berbeda dari jumlah baris yang tertulis. Request masuk EXCEPTION dan tampil "Perlu perhatian". Kotak kendala menulis hasil kali yang benar, dan "Pakai saran" bisa mengisinya.

**Pesan di layar.** "Pemeriksaan quantity x unit price terhadap total baris." diikuti nomor baris, misalnya Baris 1. Baris 1 sama dengan kartu ITEM 1 di tab "Data invoice".

**Istilah lain.** jumlah baris salah, harga satuan beda, qty salah, hitungan per item tidak cocok.

**Langkah penanganan**
1. Buka kartu ITEM yang ditunjuk di tab "Data invoice".
2. Cocokkan "Kuantitas", "Harga satuan", dan "Total baris" dengan baris yang sama di PDF.
3. Kalau AI salah baca, koreksi sesuai PDF lalu simpan dengan alasan.
4. Kalau harga satuan tertulis sudah termasuk PPN, misalnya di invoice SIPLah, isi harga satuan dari kolom harga sebelum PPN di dokumen. Total baris dan subtotal tetap.
5. Kalau PDF sendiri tidak konsisten, misalnya ada potongan harga per baris, biarkan angkanya. Finance memutuskan: setujui dengan catatan review, atau kembalikan ke PIC.

**Dilarang.** Mengganti qty atau harga satuan dengan hasil hitung sendiri supaya cocok. Menyamakan total baris dengan harga yang sudah termasuk PPN, karena PPN jadi terhitung dua kali.

**Selesai kalau.** Ketiga angka sesuai PDF dan hasil kalinya cocok.

**Bedanya dengan.** SUBTOTAL_MISMATCH memeriksa jumlah semua baris terhadap subtotal tertulis.

**Pertanyaan umum.** Harga satuan di PDF tertulis 75.000, saya isi apa? Isi 75.000 seperti di PDF. Isian memakai titik pemisah ribuan dan koma desimal.

Aturan: demo-rules.v1. Aturan penyesuaian per baris dan total belum diputuskan, pemilik: Finance dan Product Owner.
