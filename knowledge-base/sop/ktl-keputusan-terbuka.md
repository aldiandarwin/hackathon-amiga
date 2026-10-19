---
sop_id: KTL-KEPUTUSAN-TERBUKA
kategori: kontrol
peran: finance-reviewer, service-lead
status_aturan: belum-diputuskan
sumber: arsitektur §7 dan §12; invoice-data-contract konvensi nominal dan keputusan yang masih terbuka; acceptance AC-13 dan keputusan sebelum acceptance final; database-design-draft kesiapan implementasi; prototype/amiga_ocr/contracts.py:44-52; prototype/amiga_ocr/validation.py:112-113; app/review.py SOURCE_CHECKS, voucher_number, dan director_approve; app/signing.py; app/voucher_pdf.py TEMPLATE_VERSION; app/README.md batas tahap; output/app-stage8/VERIFICATION.md keterbatasan
---

# Keputusan yang belum ditetapkan dan status aturan PoC

**Aturan.** Nilai yang dipakai PoC berasal dari demo-rules.v1: enam data wajib, minimal satu baris barang, toleransi selisih nol, dan hanya IDR. Aturan ini belum disetujui Finance.

**Alasan.** SOP tidak boleh mengarang kebijakan. Hal yang belum diputuskan ditulis apa adanya beserta pemiliknya.

**Cara sistem menegakkan.** Setiap hasil validasi mencatat versi aturannya, jadi perubahan aturan nanti bisa ditelusuri.

**Belum diputuskan**
- Data dan lampiran wajib, serta sumber verifikasi rekening. Pemilik: Finance.
- Pengelolaan master vendor. Belum ada di PoC dan belum punya pemilik tercatat.
- Tarif dan pembulatan pajak, format tanggal, dan penyesuaian total selain diskon yang tidak tertulis. PoC memakai asumsi pajak-poc.v2. Pemilik: Finance dan Product Owner.
- Penyelesaian kandidat duplikasi, revisi invoice, dan invoice mata uang asing. Pemilik: Finance dan Product Owner.
- Pengajuan ulang dokumen, misalnya PDF pengganti atau proses ulang sesudah gagal. Belum ada di PoC dan belum punya pemilik tercatat.
- Tanda yang cukup dikonfirmasi reviewer saat persetujuan. PoC mengizinkan enam tanda pemeriksaan sumber. Pemilik: Finance dan Product Owner.
- Status REJECTED. Pemilik: Finance dan Product Owner.
- Arti SENT_TO_CLIENT. Pemilik: Product Owner.
- Template, penomoran, dan teks otorisasi voucher. Pemilik: AMIGA dan Finance. PoC memakai amiga-demo-v4 dengan nomor seperti ARS-00001-10-2026.
- Persetujuan Manajer Keuangan AMIGA di aplikasi, ekstensi di luar brief. Pemilik: AMIGA.
- Tanda tangan tersertifikasi lewat PSrE. Voucher PoC memakai tanda tangan basah. Pemilik belum tercatat.

**Pertanyaan umum.** Kalau jawabannya belum diputuskan, apa yang dilakukan? Ikuti aturan PoC, lalu tanyakan ke pemilik keputusannya.
