---
sop_id: FON-TENTANG-AMIGA
kategori: fondasi
tahap: intake, review, persetujuan, voucher
peran: pic-klien, finance-reviewer, service-lead, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 2-4 dan 6; BRD 1.2, 3, dan 5; app/README.md alur dan batas tahap; output/arsip/app/EXECUTION.md; output/arsip/app/EXECUTION_APPROVAL.md; output/arsip/app/EXECUTION_BATCH.md; app/review.py approve dan director_approve; app/voucher_pdf.py batas otorisasi; acceptance PERF-01 sampai PERF-03; output/app-stage8/VERIFICATION.md KPI
---

# Tentang AMIGA Robot Admin

**Ringkasnya.** AMIGA Robot Admin adalah platform internal AMIGA untuk mengubah invoice vendor menjadi voucher pembayaran standar. AI membaca PDF invoice, aturan otomatis memeriksa datanya, lalu tim Keuangan AMIGA meninjau secara independen sebelum voucher dibuat.

**Masalah yang diselesaikan.** Selama ini data invoice diketik ulang ke spreadsheet, voucher disusun manual, dan status pekerjaan tersebar di WhatsApp dan email. Akibatnya kerja lambat, rawan salah ketik nominal dan rekening, rawan bayar ganda, dan jejak persetujuannya sulit diaudit.

**Cakupan MVP.** Ekstraksi data invoice, validasi kelengkapan, perhitungan, dan duplikasi, review independen, unggah beberapa file, serta draf voucher PDF. Di luar cakupan: pembayaran, aplikasi iOS native, multi-bahasa, multi-mata uang, dan program loyalitas.

**Target kinerja.** Ekstraksi maksimal 15 detik per PDF hingga 5 halaman. Layar antrean dan review terbuka maksimal 2 detik. Voucher PDF jadi maksimal 3 detik sesudah persetujuan. Uji tahap 8 memenuhi ketiganya pada data uji, kecuali satu dari 34 dokumen sintetis yang butuh 15,3 detik. Ini ukuran satu laptop, bukan SLA produksi.

**Kondisi aplikasi PoC.** Unggah 1 sampai 5 file per batch, ekstraksi, validasi, koreksi, persetujuan Finance lalu Manajer Keuangan AMIGA, serta draf dan voucher final untuk tanda tangan basah sudah jalan. Persetujuan dan pembayaran klien tetap di luar aplikasi. Serah terima ke klien masih prosedur target.

**Pertanyaan umum.** Apakah AI yang menyetujui pembayaran? Tidak. AI hanya membaca invoice, dan aturan otomatis yang menandai temuan. Finance Reviewer menyetujui hasil review data, lalu Manajer Keuangan AMIGA menyetujui voucher final di aplikasi. Persetujuan dan pembayaran klien tetap di luar sistem.
