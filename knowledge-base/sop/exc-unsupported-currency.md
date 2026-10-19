---
sop_id: EXC-UNSUPPORTED_CURRENCY
kategori: exception
kode: UNSUPPORTED_CURRENCY
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:103-104; app/review.py assess; prototype/amiga_ocr/contracts.py:48 dan 118-119; BRD out-of-scope multi-mata uang; arsitektur §2
---

# UNSUPPORTED_CURRENCY: mata uang invoice di luar cakupan

**Ringkasnya.** Mata uang invoice bukan IDR. Di demo-rules.v1 hanya IDR yang didukung. Request masuk EXCEPTION dan tampil "Perlu perhatian".

**Pesan di layar.** "Mata uang di luar cakupan konfigurasi demo." pada isian "Mata uang".

**Istilah lain.** mata uang asing, valas, USD, dolar, kurs.

**Langkah penanganan**
1. Cek mata uang yang tertulis di PDF.
2. Kalau invoice memakai rupiah tapi AI salah baca, ubah isian "Mata uang" menjadi IDR, lalu simpan dengan alasan. Tanda koreksi manusia dan tanda kutipan sumber yang muncul sesudahnya tidak menghalangi persetujuan.
3. Kalau invoice memang memakai mata uang asing, jangan dikonversi. Teruskan ke PIC Klien dan Finance di luar aplikasi, karena multi-mata uang di luar cakupan MVP.

**Dilarang.** Mengganti mata uang asing yang tertulis di PDF menjadi IDR, atau mengisi nominal hasil konversi kurs sendiri.

**Selesai kalau.** Mata uang sesuai PDF dan termasuk cakupan. Invoice mata uang asing tetap "Perlu perhatian" dan tidak bisa disetujui, karena penanganannya belum diputuskan, pemilik: Finance dan Product Owner.

**Pertanyaan umum.** Bisa saya tulis Rp di isian mata uang? Tidak. Isian ini butuh kode tiga huruf kapital seperti IDR. Tulisan Rp ditolak saat menyimpan.

Aturan: demo-rules.v1.
