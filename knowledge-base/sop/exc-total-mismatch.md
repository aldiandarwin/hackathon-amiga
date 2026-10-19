---
sop_id: EXC-TOTAL_MISMATCH
kategori: exception
kode: TOTAL_MISMATCH
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:123-138; app/review.py assess; arsitektur §7 rules utama dan §12; acceptance AC-10 dan keputusan sebelum acceptance final; invoice-data-contract keputusan yang masih terbuka; app/service.py snapshot; brief hal. 3; app/static/review-guide.js amigaCheckHint
---

# TOTAL_MISMATCH: total invoice tidak sama dengan hitungan sistem

**Ringkasnya.** Sistem menjumlahkan semua baris, mengurangi diskon, menambah biaya lain, lalu menambah pajak. Hasilnya berbeda dari total yang tertulis di invoice. Request masuk EXCEPTION dan tampil "Perlu perhatian".

**Pesan di layar.** "Pemeriksaan total dengan aturan demo." Kotak kendala menulis hitungan, selisih, dan saran. Selisih dua kali diskon berarti diskon itu kemungkinan biaya tambahan.

**Istilah lain.** total beda, total tidak cocok, salah hitung total, selisih nominal.

**Langkah penanganan**
1. Di tab "Data invoice", cocokkan "Subtotal", "Diskon", "Biaya lain", "PPN tertulis", dan "Total tagihan sebelum PPh" dengan PDF.
2. Cocokkan juga isian "Total baris" di tiap item, karena hitungan sistem memakai angka itu.
3. Kalau AI salah baca, koreksi sesuai PDF. "Pakai saran" mengisi angka saran, lalu cocokkan dan simpan.
4. Kalau angka di PDF sendiri memang tidak konsisten, jangan diubah. PIC menjelaskannya di catatan pengajuan, lalu menindaklanjutinya bersama klien.

**Dilarang.** Memakai saran tanpa mencocokkannya dengan PDF. Menghitung pajak sendiri dengan tarif umum yang tidak tertulis di invoice.

**Selesai kalau.** Angka sesuai PDF dan hitungannya cocok. Kalau selisih memang ada di dokumen, Finance memutuskan: setujui dengan catatan review, atau kembalikan ke PIC.

**Bedanya dengan.** LINE_TOTAL_MISMATCH memeriksa satu baris. SUBTOTAL_MISMATCH memeriksa jumlah semua baris. TOTAL_MISMATCH memeriksa total akhir sesudah diskon, biaya lain, dan pajak.

**Pertanyaan umum.** Selisihnya cuma satu rupiah, tetap ditandai? Ya. Toleransi demo-rules.v1 adalah nol.

Aturan: demo-rules.v1. Aturan pembulatan, pajak, dan diskon final belum diputuskan, pemilik: Finance dan Product Owner.
