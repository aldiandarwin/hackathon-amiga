---
sop_id: EXC-OCR_INCOMPLETE
kategori: exception
kode: OCR_INCOMPLETE
tahap: ekstraksi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:57-71 dan 94-95; app/service.py inspect_pdf, intake, context, dan snapshot; app/review.py SOURCE_CHECKS; app/README.md batas tahap; acceptance AC-13
---

# OCR_INCOMPLETE: ada halaman atau foto yang teksnya tidak terbaca

**Ringkasnya.** Minimal satu halaman PDF tidak punya lapisan teks, biasanya karena hasil scan. Sistem tidak bisa memastikan semua halaman terbaca. Request masuk EXCEPTION dan tampil "Perlu perhatian".

**Pesan di layar.** "Pemeriksaan kelengkapan halaman OCR."

**Istilah lain.** PDF hasil scan, hasil pindai, halaman tidak terbaca, teks PDF kosong.

**Langkah penanganan**
1. Buka setiap halaman di panel "Invoice asli" dan pastikan semua halaman ada.
2. Periksa tiap isian secara visual, karena kutipan sumber dari halaman scan tidak bisa dicek otomatis.
3. Koreksi nilai yang salah dengan alasan yang menyebut halaman PDF.

**Dilarang.** Menganggap data dari halaman scan sudah benar karena tidak ada tanda lain.

**Selesai kalau.** Semua halaman sudah diperiksa manusia. Di PoC saat ini, tanda ini tetap ada selama PDF-nya hasil scan. Tanda ini tidak menghalangi persetujuan, dan reviewer mengonfirmasinya saat menyetujui.

**Sering muncul bersama.** VISUAL_REVIEW_REQUIRED, yang muncul dari kondisi yang sama, dan SOURCE_EVIDENCE_INVALID untuk isian dari halaman scan.

**Pertanyaan umum.** Perlu minta PDF digital dari vendor? Alur pengajuan ulang dokumen belum ada di PoC dan belum punya pemilik tercatat. Mengunggah file yang sama tidak memproses ulang. PDF lain untuk invoice yang sama menjadi request baru, dan kedua request bisa kena POSSIBLE_DUPLICATE.

Aturan: demo-rules.v1.
