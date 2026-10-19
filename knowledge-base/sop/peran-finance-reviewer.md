---
sop_id: PERAN-FINANCE-REVIEWER
kategori: peran
tahap: review, persetujuan, voucher
peran: finance-reviewer
status_aturan: brief-v2.0
sumber: brief hal. 7; app/review.py assess, verify_signer, approve, dan retry; app/service.py intake, detail, dan edit; app/static/app.js renderDecision dan openSign; app/static/review-guide.js; app/voucher_clean.py render_clean v7; web/components/shell.tsx menu Persetujuan; prototype/amiga_ocr/validation.py:172-173; app/schema.sql:6; app/database.py seed akun
---

# Peran Finance Reviewer di AMIGA Robot Admin

**Tanggung jawab.** Memeriksa, mengoreksi, lalu menyetujui atau mengembalikan invoice yang sudah diajukan PIC untuk klien timnya. Peran ini kontrol mutu independen atas kerja AI dan PIC, juga penyetuju pertama voucher.

**Boleh**
- Membaca dan mengoreksi data invoice klien timnya, selama manajer keuangan belum menyetujui.
- Menyetujui invoice yang diajukan PIC. Sistem lalu membuat draf voucher.
- Menyetujui invoice berkendala dengan alasan di "Catatan review", atau "Kembalikan ke PIC".
- Menindaklanjuti invoice "Dikembalikan manajer keuangan" dengan koreksi, persetujuan ulang, atau "Kembalikan ke PIC".
- Mengulang pembuatan PDF draf atau voucher final yang gagal.

**Tidak boleh**
- Mengunggah invoice. Itu tugas PIC, jadi menu Finance berisi "Persetujuan".
- Menyetujui sebelum PIC mengajukan. Server menolak dengan NOT_SUBMITTED, dan layar menulis "Menunggu pengajuan PIC".
- Menyetujui invoice lama unggahannya sendiri.
- Menyetujui selama isian wajib kosong, pajak belum dipilih, atau mata uang bukan IDR.
- Menyetujui bila akunnya juga SYSTEM_ADMIN, peran yang belum ada di PoC.
- Mengoreksi sesudah "Disetujui manajer keuangan". Server menolak dengan AMIGA_APPROVED_LOCKED.
- Membuka data klien di luar timnya.

**Layar dan status.** Bekerja di menu "Persetujuan" dan layar review. Tab "Voucher & persetujuan" memuat pengajuan dan catatan PIC. Menangani "Siap diperiksa", "Perlu perhatian", dan "Dikembalikan manajer keuangan". Persetujuannya menghasilkan AMIGA_REVIEWED, di layar "Menunggu manajer keuangan". Namanya tercetak di kotak "Diperiksa Oleh".

**Pertanyaan umum.** Apakah persetujuan Finance berarti invoice sudah dibayar? Tidak. Voucher final butuh persetujuan Manajer Keuangan AMIGA, dan pembayaran tetap di luar aplikasi.
