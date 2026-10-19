---
sop_id: PERAN-PIC-KLIEN
kategori: peran
tahap: intake, antrean, review, voucher, serah_terima
peran: pic-klien
status_aturan: brief-v2.0
sumber: brief hal. 5 dan 7 tabel peran; app/service.py intake, edit, submit, register_vendor, dan detail can_edit; app/clients.py; app/batches.py; app/review.py assess, download, dan download_signed; app/static/app.js enter, updateApproval, dan renderDecision; app/static/intake.js; web/app/unggah/page.tsx
---

# Peran PIC Klien di AMIGA Robot Admin

**Tanggung jawab.** Pemilik pekerjaan untuk klien timnya. PIC mengunggah invoice, mencocokkan hasil baca AI dengan dokumen, lalu mengajukannya ke Finance. Hanya PIC yang mengunggah, dan ia bertanggung jawab atas isi yang diajukan. Finance lalu manajer keuangan memeriksa. Di data demo, tiap tim memegang 10 klien.

**Boleh**
- Mengunggah 1 sampai 5 invoice per batch. Klien dipilih dulu di kolom Klien.
- Mengoreksi data selama status "Belum diajukan", termasuk lewat "Pakai saran".
- Menekan "Ajukan ke Finance" sesudah enam isian wajib terisi: vendor, nomor invoice, tanggal, mata uang, total, dan nomor rekening. NPWP dan faktur boleh kosong.
- Mendaftarkan vendor baru saat mengajukan, kalau vendornya belum ada di master klien.
- Membuat klien baru lewat "+ Klien baru". Klien itu langsung terbuka untuk tim PIC dan manajer keuangan.
- Mengunduh draf dan voucher final, lalu mengirim ke klien di "Hubungi klien".

**Tidak boleh**
- Mengoreksi sesudah mengajukan. Server menolak dengan INTAKE_LOCKED, dan koreksi berikutnya oleh Finance.
- Mengganti rekening vendor di master klien, kecuali vendor yang didaftarkan pengajuan ini sendiri.
- Menyetujui review, voucher, atau pembayaran.

**Layar dan status.** Antrean PIC terbuka di filter "Belum diajukan". Dialog pengajuan meminta centang pernyataan tanggung jawab. Kalau masih ada kendala atau ada vendor baru, "Catatan untuk Finance" wajib diisi minimal 5 karakter. Riwayat lalu mencatat "Diajukan PIC ke Finance". Invoice yang "Dikembalikan Finance" memuat alasannya. Perbaiki, lalu ajukan ulang.

**Pertanyaan umum.** Data hasil AI salah, PIC harus bagaimana? Koreksi sendiri selama belum diajukan, lalu simpan. Kendala yang tidak bisa diperbaiki boleh diajukan dengan catatan alasannya.
