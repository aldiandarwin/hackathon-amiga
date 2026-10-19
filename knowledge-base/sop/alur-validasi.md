---
sop_id: ALUR-VALIDASI
kategori: alur
tahap: validasi
peran: robot-admin, finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:92-164; prototype/amiga_ocr/contracts.py:44-52; app/service.py snapshot; app/review.py assess; app/static/app.js renderChecks; arsitektur §5 dan §7; output/app-stage3/VERIFICATION.md
---

# Validasi otomatis: aturan yang memeriksa draf invoice

**Tujuan.** Memeriksa kelengkapan, perhitungan, duplikasi, dan rekening sebelum manusia meninjau.

**Siapa.** Sistem menjalankan aturan demo-rules.v1. Aturannya ditetapkan backend, bukan oleh AI.

**Prasyarat.** Ekstraksi menghasilkan draf yang lolos kontrak data.

**Langkah**
1. Kelengkapan halaman: lolos sebagai OCR_COMPLETE.
2. Data wajib: kekurangan ditandai MISSING_EVIDENCE.
3. Kutipan sumber: lolos sebagai SOURCE_EVIDENCE_MATCH kalau semua nilai didukung kutipan.
4. Perhitungan: lolos sebagai LINE_TOTAL_MATCH, SUBTOTAL_MATCH, dan TOTAL_MATCH kalau angkanya cocok.
5. Duplikasi dan rekening: lolos sebagai DUPLICATE_CHECK dan BANK_VERIFIED.

**Hasil.** Semua lolos berarti READY_FOR_REVIEW, tampil "Siap diperiksa". Satu saja gagal atau NOT_CHECKED berarti EXCEPTION, tampil "Perlu perhatian". Selama PIC belum mengajukannya lewat "Ajukan ke Finance", antrean dan layar review menampilkan "Belum diajukan", apa pun hasil validasinya.

**Kontrol.** Hanya IDR yang didukung. Toleransi selisih nol. Aturan ini tidak membuktikan hasil baca AI sempurna, jadi review manusia tetap wajib. Saat persetujuan, aturan ini dijalankan ulang, jadi kandidat duplikat yang masuk belakangan tetap ditandai. Hasil validasi adalah saran. Yang menahan persetujuan hanya isian wajib yang kosong dan pajak yang belum terhitung.

**Pertanyaan umum.** Kalau semua lolos, apakah invoice sudah disetujui? Belum. Layar menulis "Tidak ada kendala pada pemeriksaan data otomatis". Di bawahnya tertulis "Finance tetap perlu memeriksa dokumen, pilihan pajak, dan kewenangan reviewer sebelum menyetujui."
