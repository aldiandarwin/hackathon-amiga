---
sop_id: EXC-AMBIGUOUS_VALUE
kategori: exception
kode: AMBIGUOUS_VALUE
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:42-54 dan 72-82; app/service.py edit; app/review.py SOURCE_CHECKS; invoice-data-contract konvensi nominal dan keputusan terbuka
---

# AMBIGUOUS_VALUE: angka atau tanggal di dokumen tidak bisa dipastikan

**Ringkasnya.** Kutipan sumber berisi angka yang bisa dibaca lebih dari satu cara, atau tanggal yang tidak tertulis persis sebagai YYYY-MM-DD di kutipan. Sistem tidak menebak, jadi request masuk EXCEPTION dan tampil "Perlu perhatian". Tanggal yang dikoreksi biasanya ikut kena tanda ini, karena kutipan lamanya tetap dipakai.

**Pesan di layar.** "Angka dalam bukti sumber belum dapat dinormalisasi secara pasti." atau "Prototype memerlukan bukti tanggal ISO yang tidak ambigu."

**Istilah lain.** angka ambigu, format angka membingungkan, pemisah ribuan, tanggal tidak jelas.

**Langkah penanganan**
1. Baca kutipan sumber di bawah isian yang ditandai, lalu cocokkan dengan PDF.
2. Pastikan nilainya benar. Angka ditulis desimal polos dengan titik sebagai pemisah desimal. Tanggal ditulis YYYY-MM-DD.
3. Kalau nilai hasil AI salah, koreksi dan tulis alasannya.

**Dilarang.** Menebak maksud angka seperti 1.234 tanpa melihat konteks dokumen.

**Selesai kalau.** Nilainya sudah dipastikan manusia. Untuk angka, dan untuk tanggal yang kutipannya tidak berformat YYYY-MM-DD, tanda ini tidak hilang lewat koreksi, karena kutipan sumber aslinya tetap dipakai. Tanda ini tidak menghalangi persetujuan, tapi wajib dikonfirmasi reviewer saat menyetujui.

**Pertanyaan umum.** Kenapa invoice biasa sering kena tanda ini? Prototype hanya yakin pada angka seperti 150000 atau 150.000,00, dan tanggal yang tertulis YYYY-MM-DD. Angka 1.500.000 tanpa sen, kutipan berisi dua angka, atau tanggal 13 Oktober 2026 selalu ditandai.

Aturan: demo-rules.v1. Kontrak data menormalkan angka lokal hanya kalau konteksnya jelas. Aturan tanggal ambigu belum diputuskan, pemilik: Finance dan Product Owner.
