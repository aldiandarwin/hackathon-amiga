---
sop_id: EXC-TAX_PPN_MISSING
kategori: exception
kode: TAX_PPN_MISSING
tahap: validasi, review
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/taxes.py compute; app/static/tax.js taxSummaryHTML; app/static/app.js isian Pajak
---

# TAX_PPN_MISSING: PPN dipilih tapi nominal pajak kosong

**Ringkasnya.** Pilihan pajak memuat PPN, tetapi isian "PPN tertulis" kosong atau nol. PPN dihitung 0 dan approval tidak tertahan, tapi nominal bayarnya bisa salah.

**Pesan di layar.** "PPN dipilih, tetapi nominal pajak invoice kosong atau nol." Panel Pajak mencatat "PPN dipilih, tetapi PPN tertulis kosong. Dihitung 0 sampai Finance mengisinya."

**Istilah lain.** PPN kosong, nominal PPN nol, pajak tidak terbaca.

**Langkah penanganan**
1. Cari baris PPN di PDF asli.
2. Kalau PPN tercetak, isi "PPN tertulis" sesuai angka di PDF, lalu simpan koreksi dengan alasan.
3. Kalau invoice tidak mencetak PPN terpisah, ubah pilihan ke opsi tanpa PPN, misalnya "Tanpa pajak" atau "PPh 23 2% saja".
4. Pastikan panel Pajak menghitung ulang sesudah koreksi tersimpan.

**Dilarang.** Mengisi PPN hasil hitungan sendiri yang tidak tertulis di invoice.

**Selesai kalau.** Isian "PPN tertulis" sama dengan PDF, atau pilihan tanpa PPN sudah tersimpan.

**Bedanya dengan.** TAX_PPN_CONFLICT adalah kebalikannya: pajak tertulis, tetapi pilihannya tanpa PPN. TAX_ADJUSTMENT_INVALID muncul kalau "Tambahkan PPN di atas total invoice" dipakai pada invoice yang sudah mencetak PPN.

**Pertanyaan umum.** Invoice lama mencetak harga sudah termasuk PPN, bagaimana? Jangan isi angka karangan. Catat di alasan koreksi, lalu Finance memutuskan pilihannya.

Aturan: pajak-poc.v2.
