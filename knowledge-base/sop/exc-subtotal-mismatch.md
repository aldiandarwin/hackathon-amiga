---
sop_id: EXC-SUBTOTAL_MISMATCH
kategori: exception
kode: SUBTOTAL_MISMATCH
tahap: validasi, review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py:26-39, 57-71, dan 123-130; app/static/app.js renderFields; app/service.py edit; app/review.py assess; acceptance AC-02 dan AC-09; app/static/review-guide.js amigaCheckHint
---

# SUBTOTAL_MISMATCH: jumlah semua baris tidak sama dengan subtotal tertulis

**Ringkasnya.** Sistem menjumlahkan isian "Total baris" di semua baris barang. Hasilnya berbeda dari subtotal yang tertulis di invoice. Request masuk EXCEPTION dan tampil "Perlu perhatian". Kotak kendala menulis sarannya.

**Pesan di layar.** "Pemeriksaan jumlah total baris."

**Istilah lain.** subtotal beda, jumlah baris tidak cocok, ada baris yang hilang, baris dobel.

**Langkah penanganan**
1. Hitung jumlah baris barang di PDF, lalu bandingkan dengan jumlah kartu ITEM di tab "Data invoice".
2. Cocokkan isian "Total baris" tiap item dan isian "Subtotal" dengan PDF. Koreksi angka yang salah baca.
3. Jumlah baris sama dengan subtotal ditambah PPN berarti harga item sudah termasuk PPN. Subtotal tetap supaya PPN tidak terhitung dua kali, dan total baris diisi nilai sebelum PPN.
4. Baris yang terlewat bisa ditambah lewat "+ Tambah item", tapi selalu masuk di urutan terakhir dan tanpa kutipan sumber.
5. Menghapus baris di tengah lewat "Hapus item" menggeser kutipan sumber baris sesudahnya. Lakukan hanya kalau baris itu memang tidak ada di PDF.

**Dilarang.** Menambah atau menghapus baris yang tidak sesuai PDF supaya angkanya cocok.

**Selesai kalau.** Semua baris dan subtotal sesuai PDF dan jumlahnya cocok. Koreksi memunculkan HUMAN_CORRECTION_PENDING, dan baris yang ditambah atau bergeser memunculkan tanda kutipan sumber. Tanda itu tidak menghalangi persetujuan.

**Bedanya dengan.** TOTAL_MISMATCH memeriksa total akhir sesudah diskon, biaya lain, dan pajak. Satu angka baris yang salah baca bisa memicu keduanya.

**Pertanyaan umum.** Invoice saya tiga halaman, apa yang perlu diperhatikan? Cek baris barang di tiap halaman, termasuk urutannya.

Aturan: demo-rules.v1. Toleransi selisih nol.
