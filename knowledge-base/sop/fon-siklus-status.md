---
sop_id: FON-SIKLUS-STATUS
kategori: fondasi
tahap: antrean, ekstraksi, validasi, review, persetujuan, voucher, serah_terima
peran: pic-klien, finance-reviewer, service-lead, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 5; arsitektur §7 workflow dan §12; output/preparation/api-contract-draft.md state dan error; acceptance keputusan sebelum acceptance final; app/static/app.js statuses dan shownStatus; app/service.py stage, snapshot, edit, dan submit; app/review.py assess, approve, director_approve, dan director_return
---

# Siklus status request invoice

**Ringkasnya.** Status menunjukkan posisi invoice di alur kerja. Tujuh status punya label di layar. SENT_TO_CLIENT masih prosedur target. Sebelum PIC mengajukan, invoice yang terbaca AI tampil "Belum diajukan", apa pun statusnya.

- QUEUED, di layar "Menunggu proses". Invoice sudah masuk antrean.
- PROCESSING, di layar "Sedang diproses". AI sedang membaca invoice.
- READY_FOR_REVIEW, di layar "Siap diperiksa". Semua pemeriksaan otomatis lolos. Ini belum persetujuan pembayaran.
- EXCEPTION, di layar "Perlu perhatian". Ada pemeriksaan yang gagal atau belum bisa dijalankan, ada isian yang dikoreksi manusia, atau prosesnya berhenti.
- AMIGA_REVIEWED, di layar "Menunggu manajer keuangan". Finance menyetujui satu versi data, lalu draf voucher menunggu Manajer Keuangan AMIGA.
- AMIGA_APPROVED, di layar "Disetujui manajer keuangan". Manajer Keuangan AMIGA ikut menyetujui, dan voucher final dibuat. Datanya terkunci.
- RETURNED, di layar "Dikembalikan manajer keuangan". Manajer keuangan mengembalikan voucher ke Finance dengan alasan. Datanya disalin ke versi baru.
- SENT_TO_CLIENT. Menurut brief, terpasang saat PIC mengunduh voucher. Di PoC belum dipakai, pemilik keputusan: Product Owner.

**Aturan perpindahan.** Aturan otomatis paling jauh menghasilkan READY_FOR_REVIEW. Koreksi manusia memindahkan request dari READY_FOR_REVIEW ke EXCEPTION. Persetujuan Finance butuh pengajuan PIC, dari READY_FOR_REVIEW, EXCEPTION, atau RETURNED. Koreksi sesudah persetujuan Finance mengembalikan status ke READY_FOR_REVIEW atau EXCEPTION.

**Pertanyaan umum.** Ada status ditolak? REJECTED baru usulan tim, belum diputuskan, pemilik: Finance dan Product Owner. AMIGA_APPROVED juga belum berarti dibayar. Klien membayar di luar aplikasi.
