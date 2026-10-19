---
sop_id: EXC-TAX_SELECTION_REQUIRED
kategori: exception
kode: TAX_SELECTION_REQUIRED
tahap: intake, review, persetujuan
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/taxes.py compute dan PRESETS; app/review.py assess; app/static/tax.js taxSummaryHTML dan resetTaxForm
---

# TAX_SELECTION_REQUIRED: jenis potongan pajak belum dipilih

**Ringkasnya.** Draf belum punya pilihan pajak, jadi sistem belum bisa menghitung potongan PPh dan jumlah dibayarkan. Statusnya NOT_CHECKED. Approval ditahan sampai Finance memilih.

**Pesan di layar.** "Jenis potongan pajak belum dipilih; approval ditahan sampai Finance memilih." Panel Pajak menulis "Jenis potongan pajak belum dipilih. Finance memilih di sini sebelum persetujuan."

**Istilah lain.** pajak belum dipilih, pilihan PPh kosong, potongan pajak belum ditentukan.

**Langkah penanganan**
1. Buka panel Pajak di layar review.
2. Pilih satu dari empat: "Tanpa pajak", "PPN 11% saja", "PPh 23 2% saja", atau "PPN 11% + PPh 23 2%".
3. Kalau pilihannya memuat PPN, pastikan halaman Faktur Pajak ikut diunggah. Nomor fakturnya dibaca otomatis.
4. Simpan koreksi dengan alasan. Perubahan pilihan tercatat di riwayat.

**Dilarang.** Menebak pilihan pajak tanpa membaca baris invoice dan faktur pajaknya.

**Selesai kalau.** Panel Pajak menampilkan tabel hitungan sampai jumlah dibayarkan.

**Pertanyaan umum.** Siapa yang memilih pajak? PIC memilih saat unggah lewat "Pilih perlakuan pajak sebelum unggah", dan boleh mengubahnya selama "Belum diajukan". Finance memeriksa dan boleh mengubahnya sebelum approval.

Aturan: pajak-poc.v2.
