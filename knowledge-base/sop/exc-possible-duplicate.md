---
sop_id: EXC-POSSIBLE_DUPLICATE
kategori: exception
kode: POSSIBLE_DUPLICATE
tahap: validasi, review, persetujuan
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:140-150; app/service.py context dan process_next; app/review.py assess dan approve; app/static/app.js renderChecks dan renderDecision; app/tests/test_review.py; output/app-stage3/VERIFICATION.md; brief hal. 9 skenario 4; arsitektur §7; database-design-draft transaksi review; acceptance AC-04, AC-12, AC-16; app/README.md batas tahap
---

# POSSIBLE_DUPLICATE: invoice dengan vendor dan nomor sama sudah ada

**Ringkasnya.** Di klien yang sama sudah ada request lain dengan vendor dan nomor invoice yang sama. Ini kandidat pembayaran ganda. Request masuk EXCEPTION dan tampil "Perlu perhatian". Persetujuan tidak ditahan, jadi Finance wajib membandingkan dulu.

**Pesan di layar.** "Pemeriksaan kandidat duplikasi dalam scope klien." Pemeriksaan diulang saat persetujuan, jadi invoice pasangannya ikut ditandai walau statusnya bisa tetap "Siap diperiksa". Urutan ekstraksi bisa berbeda dari urutan unggah, jadi tanda ini tidak menunjukkan invoice mana yang asli.

**Istilah lain.** invoice dobel, tagihan ganda, pembayaran ganda, nomor invoice sama.

**Langkah penanganan**
1. Cari request lain lewat kolom "Cari vendor atau nomor invoice" di antrean.
2. Bandingkan kedua PDF. Tentukan apakah ini dokumen yang sama, invoice revisi, atau invoice berbeda dengan nomor kembar.
3. Tulis temuan dan alasannya di "Catatan review", atau "Kembalikan ke PIC" dengan alasan.

**Dilarang.** Memproses kedua request untuk dibayar. Mengubah nomor invoice supaya tanda ini hilang.

**Selesai kalau.** Finance memutuskan dengan alasan tercatat: setujui kalau memang bukan tagihan ganda, atau kembalikan ke PIC. Menautkan invoice revisi ke request asalnya belum ada di PoC.

**Bedanya dengan.** DUPLICATE_CHECK berstatus NOT_CHECKED berarti pemeriksaan duplikasi belum bisa dijalankan.

**Pertanyaan umum.** Kenapa contoh kedua dari tombol contoh kena tanda ini? Ketiga contoh memakai nomor invoice yang sama.

Aturan: demo-rules.v1. Alur penyelesaiannya belum diputuskan, pemilik: Product Owner dan Finance.
