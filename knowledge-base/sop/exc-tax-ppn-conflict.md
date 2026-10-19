---
sop_id: EXC-TAX_PPN_CONFLICT
kategori: exception
kode: TAX_PPN_CONFLICT
tahap: validasi, review
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/taxes.py compute; app/static/tax.js taxError; app/static/app.js isian Pajak; app/static/review-guide.js amigaCheckHint
---

# TAX_PPN_CONFLICT: pajak tertulis tapi pilihan tanpa PPN

**Ringkasnya.** Isian "PPN tertulis" berisi angka, tetapi pilihan pajak menyatakan tanpa PPN. Sistem tetap menghitung memakai PPN tertulis, dan approval tidak tertahan. Finance yang memutuskan pilihannya.

**Pesan di layar.** "Invoice mencantumkan pajak, tetapi pilihan menyatakan tanpa PPN." Kotak kendala menyebut nominal PPN-nya. "Pakai saran" memilih pajak yang sama ditambah PPN.

**Istilah lain.** pilihan pajak bentrok, PPN tertulis tapi tidak dipilih, pajak tidak konsisten.

**Langkah penanganan**
1. Cocokkan isian "PPN tertulis" dengan PDF asli.
2. Kalau PDF memang mencetak PPN, ubah pilihan ke "PPN 11% saja" atau "PPN 11% + PPh 23 2%". Nomor faktur dibaca dari halaman Faktur Pajak.
3. Kalau angka di isian "PPN tertulis" tidak ada di PDF, koreksi isian itu sesuai dokumen.
4. Simpan koreksi dengan alasan, lalu periksa tabel hitungan pajak.

**Dilarang.** Menghapus angka pajak yang tercetak di PDF hanya supaya pemeriksaan lolos.

**Selesai kalau.** Pilihan pajak dan isian "PPN tertulis" sama-sama sesuai PDF. Kalau Finance tetap memilih tanpa PPN, alasannya ditulis di "Catatan review".

**Bedanya dengan.** TAX_PPN_MISSING berarti PPN dipilih tetapi nominalnya kosong atau nol.

**Pertanyaan umum.** Kenapa tidak cukup mengosongkan isian PPN tertulis? Angka di PDF adalah bukti. Isian mengikuti dokumen, lalu pilihan pajak yang disesuaikan.

Aturan: pajak-poc.v2.
