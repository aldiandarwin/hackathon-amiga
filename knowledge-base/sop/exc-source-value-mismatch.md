---
sop_id: EXC-SOURCE_VALUE_MISMATCH
kategori: exception
kode: SOURCE_VALUE_MISMATCH
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:57-89; app/service.py edit; app/review.py SOURCE_CHECKS dan approve; invoice-data-contract evidence dan pemrosesan
---

# SOURCE_VALUE_MISMATCH: nilai isian berbeda dari kutipan sumbernya

**Ringkasnya.** Nilai di isian tidak sama dengan teks yang dikutip dari PDF. Penyebabnya AI salah salin, atau nilai sudah dikoreksi manusia. Request masuk EXCEPTION dan tampil "Perlu perhatian".

**Pesan di layar.** Salah satu dari "Nilai ekstraksi berbeda dari bukti sumber.", "Identifier berbeda dari nilai sumber yang dikutip.", atau "Nilai ekstraksi tidak didukung kutipan sumber."

**Istilah lain.** nilai tidak sesuai kutipan, angka beda dengan sumber, nomor invoice beda, salah salin AI.

**Langkah penanganan**
1. Bandingkan tiga hal: nilai isian, kutipan sumber di bawahnya, dan teks di PDF.
2. Kalau nilai isian yang salah, koreksi sesuai PDF dan tulis alasannya.
3. Kalau nilainya sudah benar dan hanya kutipannya yang keliru, tidak ada yang bisa disimpan, karena kutipan tidak bisa diubah. Tulis temuannya di "Catatan review" saat menyetujui.

**Dilarang.** Menyamakan nilai dengan kutipan tanpa mengecek PDF. Kutipan bisa juga salah.

**Selesai kalau.** Nilai isian sesuai PDF dan alasannya tercatat. Tanda ini tidak menghalangi persetujuan. Reviewer mengonfirmasinya lewat centang konfirmasi sumber saat menyetujui.

**Pertanyaan umum.** Kenapa tanda ini muncul justru sesudah saya mengoreksi? Kutipan sumber asli tetap disimpan sebagai bukti. Nilai koreksi yang berbeda dari kutipan itu ikut ditandai, bersama tanda koreksi manusia HUMAN_CORRECTION_PENDING. Untuk tanggal, tandanya AMBIGUOUS_VALUE. Isian yang semula kosong mendapat SOURCE_EVIDENCE_INVALID.

Aturan: demo-rules.v1. Nomor invoice dan nomor rekening harus sama persis dengan kutipan, termasuk angka nol di depan.
