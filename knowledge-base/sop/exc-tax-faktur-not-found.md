---
sop_id: EXC-TAX_FAKTUR_NOT_FOUND
kategori: exception
kode: TAX_FAKTUR_NOT_FOUND
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: poc-teknis
sumber: app/taxes.py identity_checks; app/tax_api.py TaxSelection; prototype/amiga_ocr/openai_live.py PROMPT; app/static/tax.js
---

# TAX_FAKTUR_NOT_FOUND: nomor faktur pajak tidak ada atau formatnya tidak sah

**Ringkasnya.** Pilihan pajak memuat PPN, tetapi sistem tidak menemukan nomor faktur pajak yang sah. Nomor faktur dibaca otomatis dari halaman Faktur Pajak. Kode ini muncul kalau halaman itu tidak ikut diunggah, tidak terbaca, atau nomornya bukan 13 sampai 17 digit. Approval tidak tertahan, tapi faktur adalah bukti PPN.

**Pesan di layar.** "PPN dipilih, tetapi nomor faktur pajak tidak ada di dokumen." atau "Nomor faktur pajak tidak terbaca dengan format yang sah; isi dari faktur aslinya."

**Istilah lain.** faktur tidak ada, nomor seri faktur kosong, faktur belum dilampirkan, nomor faktur salah baca.

**Langkah penanganan**
1. Cek apakah dokumen memuat halaman Faktur Pajak. Kalau tidak, minta fakturnya di luar aplikasi, lalu isi nomornya di panel Pajak.
2. Kalau halaman faktur ada tetapi nomornya salah baca, Finance Reviewer mengisi nomor faktur persis dari faktur asli di panel Pajak, lalu menyimpan koreksi dengan alasan.
3. Kalau invoice memang tanpa PPN, ubah pilihan ke opsi tanpa PPN.

**Dilarang.** Mengarang nomor faktur. Menyalin nomor invoice ke kolom nomor faktur.

**Selesai kalau.** Panel Pajak menampilkan nomor faktur beserta sumbernya, dibaca dari dokumen atau diisi reviewer.

**Pertanyaan umum.** Apakah nomor faktur masih diketik saat unggah? Tidak. Sistem membacanya dari halaman Faktur Pajak. Ketik manual hanya kalau kode ini muncul.

Aturan: pajak-poc.v2.
