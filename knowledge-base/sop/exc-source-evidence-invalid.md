---
sop_id: EXC-SOURCE_EVIDENCE_INVALID
kategori: exception
kode: SOURCE_EVIDENCE_INVALID
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:57-71; app/static/app.js inputField; app/review.py SOURCE_CHECKS dan approve; invoice-data-contract evidence dan pemrosesan; acceptance AC-03
---

# SOURCE_EVIDENCE_INVALID: isian tidak punya bukti di halaman yang ditunjuk

**Ringkasnya.** Sebuah isian terisi, tapi kutipan sumbernya tidak ada, menunjuk halaman yang tidak terbaca, atau teksnya tidak ditemukan di halaman itu. Request masuk EXCEPTION dan tampil "Perlu perhatian".

**Pesan di layar.** "Bukti sumber tidak tersedia pada halaman yang ditunjuk." Pada foto, tanda ini muncul di semua isian, jadi layar menggantinya dengan satu catatan "Dokumen foto".

**Istilah lain.** kutipan sumber tidak ada, bukti tidak ditemukan, nilai tanpa sumber, halaman salah.

**Langkah penanganan**
1. Cari nilai isian itu di semua halaman PDF.
2. Kalau nilainya ada di PDF tapi salah, koreksi lalu sebutkan halamannya di alasan koreksi. Kalau sudah benar, tidak ada yang perlu disimpan. Catat halamannya di "Catatan review" saat menyetujui.
3. Kalau nilainya sama sekali tidak ada di PDF, kosongkan isiannya dan tulis alasannya. Nilai tanpa sumber bisa jadi karangan AI.

**Dilarang.** Mempertahankan nilai yang tidak bisa ditemukan di dokumen.

**Selesai kalau.** Setiap isian yang terisi bisa ditunjukkan sumbernya di PDF. Di PoC, tanda ini tidak hilang lewat koreksi, karena kutipan sumber tidak ikut berubah. Tanda hanya hilang kalau isiannya dikosongkan. Tanda ini tidak menghalangi persetujuan. Reviewer mengonfirmasinya lewat centang konfirmasi sumber, dan tandanya tercatat di keputusan.

**Sering muncul bersama.** OCR_INCOMPLETE dan VISUAL_REVIEW_REQUIRED, karena kutipan dari halaman scan tidak bisa dicek otomatis.

**Pertanyaan umum.** Kalau isian wajib dikosongkan, apa yang terjadi? Muncul MISSING_EVIDENCE, dan persetujuan tertahan sampai isian itu diisi lagi. Mengosongkan angka memunculkan INSUFFICIENT_CALCULATION_EVIDENCE, yang hanya menjadi kendala.

Aturan: demo-rules.v1.
