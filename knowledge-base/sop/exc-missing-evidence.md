---
sop_id: EXC-MISSING_EVIDENCE
kategori: exception
kode: MISSING_EVIDENCE
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:57-71, 96-113, dan 140-157; prototype/amiga_ocr/contracts.py:49-52 dan 79-122; app/service.py edit; app/review.py SOURCE_CHECKS dan assess; app/tests/test_review.py; brief hal. 7 dan 9 skenario 3; acceptance AC-03 dan AC-13; invoice-data-contract; app/README.md batas tahap
---

# MISSING_EVIDENCE: data wajib invoice belum terisi

**Ringkasnya.** Satu atau lebih data wajib kosong, atau invoice tidak punya baris barang sama sekali. Isian wajib yang kosong menahan pengajuan PIC dan persetujuan Finance, karena voucher butuh isian itu.

**Pesan di layar.** "Field wajib belum tersedia." diikuti nama isian, misalnya "Nomor rekening". Kalau baris barang kosong, pesannya "Line items belum tersedia."

**Istilah lain.** data wajib kosong, rekening kosong, field kosong, data invoice belum lengkap.

**Langkah penanganan**
1. Cek PDF asli. Data wajib ada enam: nama vendor, nomor invoice, tanggal invoice, mata uang, total invoice, dan nomor rekening. NPWP dan faktur tidak termasuk.
2. Kalau nilainya ada di PDF tapi terlewat AI, PIC mengisinya sebelum mengajukan, atau Finance sesudahnya, sesuai PDF dalam format sistem. Isi "Alasan koreksi", lalu tekan "Simpan koreksi".
3. Kalau nilainya memang tidak ada di PDF, biarkan kosong. Request tetap tertahan, dan PIC Klien menindaklanjutinya bersama klien di luar aplikasi.

**Dilarang.** Mengisi tebakan, nilai dari invoice lain, atau angka nol untuk data yang tidak tertulis.

**Selesai kalau.** Semua data wajib terisi sesuai PDF. Tanda koreksi manusia dan kutipan sumber yang muncul sesudahnya tidak menghalangi persetujuan.

**Pertanyaan umum.** Rekening sudah saya isi dari PDF, kenapa masih ada kendala? Kalau vendor dikenali master, rekening yang tidak terdaftar memunculkan BANK_MISMATCH, dan invoice kembar memunculkan POSSIBLE_DUPLICATE. Kalau vendor belum ada di master, BANK_UNVERIFIED dan DUPLICATE_CHECK muncul sampai PIC mendaftarkan vendornya saat mengajukan. Tanda ini tidak menahan persetujuan.

Aturan: demo-rules.v1. Daftar data dan lampiran wajib final belum diputuskan, pemilik: Finance.
