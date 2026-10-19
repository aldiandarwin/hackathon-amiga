---
sop_id: EXC-BANK_UNVERIFIED
kategori: exception
kode: BANK_UNVERIFIED
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:151-157; app/review.py assess; arsitektur §7 dan §12; database-design-draft vendor_bank_accounts
---

# BANK_UNVERIFIED: rekening belum bisa diverifikasi

**Ringkasnya.** Sistem belum bisa mencocokkan nomor rekening dengan master vendor. Penyebabnya vendor belum dikenali master atau nomor rekening kosong. Statusnya NOT_CHECKED, jadi request menjadi EXCEPTION. Persetujuan tidak tertahan. Untuk vendor baru, tanda ini selesai saat PIC mengajukan.

**Pesan di layar.** "Verifikasi rekening belum dapat dilakukan."

**Istilah lain.** rekening belum diverifikasi, rekening belum bisa dicek, verifikasi bank tertunda.

**Langkah penanganan**
1. Kalau "Nomor rekening" kosong, tangani dulu sebagai MISSING_EVIDENCE.
2. Kalau nomor rekening terisi, periksa "Nama vendor". Vendor yang tidak dikenali master juga memunculkan DUPLICATE_CHECK.
3. Cocokkan nomor rekening dengan PDF. Ingat, PDF bukan bukti bahwa rekening itu sah.
4. Kalau vendornya memang baru, PIC menekan "Ajukan ke Finance". Dialog menampilkan "Vendor baru akan didaftarkan" beserta rekeningnya. PIC menulis catatan, lalu vendor masuk master klien dan rekeningnya lolos pencocokan.

**Dilarang.** Menganggap rekening sah hanya karena terbaca jelas di invoice. Hasil baca AI tidak membuktikan rekening.

**Selesai kalau.** Vendor dikenali master dan nomor rekening terisi, lalu pencocokan menghasilkan BANK_VERIFIED atau BANK_MISMATCH. Vendor hasil daftar PIC ditandai VENDOR_NEW untuk Finance dan manajer keuangan.

**Bedanya dengan.** BANK_MISMATCH berarti pencocokan sudah jalan dan hasilnya beda.

**Pertanyaan umum.** Rekening vendor baru diverifikasi dari mana? Di PoC, PIC mendaftarkan rekening yang tertulis di invoice dan bertanggung jawab lewat pernyataannya. Finance dan manajer keuangan tetap memeriksanya. Sumber verifikasi rekening final belum diputuskan, pemilik: Finance.

Aturan: demo-rules.v1.
