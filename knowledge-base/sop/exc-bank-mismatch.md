---
sop_id: EXC-BANK_MISMATCH
kategori: exception
kode: BANK_MISMATCH
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:57-89 dan 151-157; app/service.py edit; app/review.py assess; app/database.py seed vendor; arsitektur §7 dan §12; database-design-draft vendor_bank_accounts; app/README.md batas tahap
---

# BANK_MISMATCH: nomor rekening di invoice berbeda dari master vendor

**Ringkasnya.** Nomor rekening yang terbaca dari invoice tidak ada di daftar rekening terverifikasi milik vendor itu. Request masuk EXCEPTION. Persetujuan tidak ditahan, tapi ini risiko salah bayar.

**Pesan di layar.** "Pencocokan dengan master demo yang sudah diverifikasi."

**Istilah lain.** rekening beda, rekening tidak cocok, nomor rekening salah, rekening vendor ganti.

**Langkah penanganan**
1. Buka tab "Data invoice". Bandingkan isian "Nomor rekening" dengan PDF asli di halaman yang ditunjuk kutipan sumber.
2. Kalau AI salah baca, PIC selama "Belum diajukan" atau Finance sesudahnya menyalin angka persis dari PDF, mengisi "Alasan koreksi", lalu menekan "Simpan koreksi". Tanda koreksi manusia dan kutipan sumber yang muncul sesudahnya tidak menghalangi persetujuan.
3. Kalau PDF memang memuat rekening lain, biarkan apa adanya. PIC tidak bisa mendaftarkan rekening baru untuk vendor yang sudah ada di master.

**Dilarang.** Mengganti nomor rekening supaya cocok dengan master. Menganggap hasil baca AI sebagai bukti bahwa rekening sah.

**Selesai kalau.** Nomor rekening sesuai PDF dan cocok dengan master. Kalau tetap beda, Finance memutuskan: kembalikan ke PIC, atau setujui dengan bukti konfirmasi vendor. Mengubah rekening vendor lama di master masih prosedur target.

**Bedanya dengan.** BANK_UNVERIFIED berarti pencocokan belum bisa dijalankan. BANK_MISMATCH berarti pencocokan sudah jalan dan hasilnya beda.

**Pertanyaan umum.** Vendor bilang rekeningnya ganti, boleh langsung diproses? Jangan. Minta konfirmasi tertulis vendor, lalu tulis buktinya di "Catatan review".

Aturan: demo-rules.v1. Sumber verifikasi rekening belum diputuskan, pemilik: Finance.
