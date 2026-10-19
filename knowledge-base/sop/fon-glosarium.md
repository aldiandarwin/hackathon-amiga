---
sop_id: FON-GLOSARIUM
kategori: fondasi
peran: pic-klien, finance-reviewer
status_aturan: brief-v2.0
sumber: brief hal. 4-8; invoice-data-contract; database-design-draft; prototype/amiga_ocr/validation.py; app/static/app.js renderFields; app/static/index.html dialog persetujuan; app/review.py approve dan director_approve; app/batches.py; app/voucher_clean.py render_clean v7
---

# Glosarium istilah AMIGA Robot Admin

**Ringkasnya.** Istilah yang sering muncul di layar dan SOP AMIGA.

- **Request.** Satu permintaan proses untuk satu invoice.
- **Request ID.** Nomor unik dari sistem saat invoice masuk antrean, tercetak di voucher PDF.
- **Batch.** Satu kali unggah berisi 1 sampai 5 PDF untuk satu klien. Penerimaan tiap file dicatat terpisah.
- **Draf invoice.** Data hasil baca AI yang masih bisa dikoreksi PIC atau Finance.
- **Pengajuan.** PIC menyerahkan data yang sudah dicocokkan ke Finance, disertai pernyataan.
- **Versi.** Setiap koreksi membuat versi baru. Versi lama tidak pernah ditimpa.
- **Kutipan sumber.** Potongan teks asli PDF dan nomor halamannya, sebagai bukti sebuah nilai.
- **Check.** Satu pemeriksaan otomatis. Hasilnya PASSED, FAILED, atau NOT_CHECKED.
- **Exception.** Kondisi yang butuh perhatian manusia, berstatus EXCEPTION.
- **Baris barang.** Rincian barang atau jasa di invoice. Di layar disebut ITEM.
- **Master vendor.** Daftar vendor dan rekening terverifikasi milik tiap klien.
- **Konfirmasi sumber.** Centang wajib di dialog persetujuan Finance bahwa data cocok dengan dokumen asli.
- **Voucher.** PDF dari data versi yang disetujui Finance. Versi final ikut disetujui Manajer Keuangan AMIGA.
- **Tanda tangan basah.** Tanda tangan pena di tiga kotak voucher cetak: PIC, Finance, dan manajer keuangan.
- **Riwayat perubahan.** Catatan aktivitas yang tidak bisa diubah atau dihapus.
- **demo-rules.v1.** Versi aturan validasi demo yang dipakai PoC.
- **Pemisahan tugas.** Pengunggah tidak boleh menyetujui dokumennya sendiri.

**Pertanyaan umum.** Apa beda PASSED dan NOT_CHECKED? PASSED berarti lolos. NOT_CHECKED berarti belum bisa diperiksa, dan request menjadi EXCEPTION. Persetujuan tidak tertahan, Finance yang memutuskan.
