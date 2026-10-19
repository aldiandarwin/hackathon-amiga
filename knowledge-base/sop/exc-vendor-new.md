---
sop_id: EXC-VENDOR_NEW
kategori: exception
kode: VENDOR_NEW
tahap: intake, review, persetujuan
peran: pic-klien, finance-reviewer, amiga-director
status_aturan: poc-teknis
sumber: app/service.py submit, register_vendor, dan snapshot; app/static/intake.js openSubmit; app/static/app.js signatureHTML dan openSign
---

# VENDOR_NEW: Vendor baru, didaftarkan PIC

**Ringkasnya.** Vendor ini belum ada di master vendor klien saat PIC mengajukan invoice, jadi PIC mendaftarkannya. Rekening dan NPWP diambil dari invoice. Tanda ini hanya informasi dan tidak menahan persetujuan.

**Pesan di layar.** "Vendor didaftarkan PIC saat pengajuan, bukan dari master yang sudah diverifikasi. Rekening dan NPWP berasal dari invoice." Di tab voucher dan dialog persetujuan tertulis "Vendor baru, didaftarkan PIC".

**Istilah lain.** vendor baru, pemasok baru, vendor belum terdaftar, rekening vendor baru.

**Langkah penanganan**
1. PIC: sebelum menekan "Ajukan ke Finance", pastikan nama vendor dan nomor rekening sama persis dengan dokumen. Dialog menulis "Vendor baru akan didaftarkan", dan catatan wajib diisi.
2. Finance: cocokkan nama, rekening, dan NPWP dengan dokumen asli. Baca catatan PIC di tab "Voucher & persetujuan". Kalau rekeningnya salah, kembalikan ke PIC. Rekening itu ikut dibetulkan saat PIC mengajukan ulang.
3. Manajer Keuangan AMIGA: perhatikan tanda vendor baru sebelum menyetujui.

**Dilarang.** Mendaftarkan ulang vendor lama dengan rekening lain. Rekening yang sudah milik vendor lain ditolak dengan VENDOR_EXISTS. Rekening berbeda untuk vendor lama tetap BANK_MISMATCH, kendala yang wajib dicocokkan Finance.

**Selesai kalau.** Finance menyetujui sesudah mencocokkan data vendor dengan dokumen. Pada invoice berikutnya, rekening vendor ini dikenali sebagai BANK_VERIFIED.

**Pertanyaan umum.** Kenapa tanda ini tidak hilang? Tanda ini melekat pada vendor, jadi setiap invoice dari vendor hasil daftar PIC tetap menampilkannya.

Aturan: poc-teknis.
