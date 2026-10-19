---
sop_id: EXC-NPWP_CHECK
kategori: exception
kode: NPWP_CHECK
tahap: validasi, review
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/taxes.py identity_checks; app/static/tax.js centang NPWP
---

# NPWP_CHECK: NPWP vendor tidak terlihat atau jumlah digitnya salah

**Ringkasnya.** Potongan PPh dihitung dengan anggapan vendor punya NPWP, tetapi NPWP vendor tidak terlihat di dokumen atau digitnya bukan 15 atau 16. Ini peringatan, bukan penghalang approval. Tarif PPh tanpa NPWP lebih tinggi, jadi status NPWP perlu dipastikan.

**Pesan di layar.** "NPWP vendor tidak terlihat di dokumen. Pastikan vendor punya NPWP sebelum potongan PPh dihitung." atau "NPWP vendor terbaca, tetapi jumlah digitnya bukan 15 atau 16. Cocokkan dengan dokumen."

**Istilah lain.** NPWP kosong, NPWP tidak terbaca, NPWP kurang digit.

**Langkah penanganan**
1. Cari NPWP vendor di invoice atau di halaman Faktur Pajak.
2. Kalau tercetak tetapi salah baca, salin persis dari dokumen lalu simpan koreksi dengan alasan.
3. Kalau vendor memang tanpa NPWP, hapus centang "Penerima punya NPWP/NIK" di panel Pajak supaya tarifnya benar.

**Dilarang.** Mengisi NPWP dari ingatan atau dari invoice lain.

**Selesai kalau.** NPWP vendor sesuai dokumen, atau pilihan tanpa NPWP sudah tersimpan.

**Pertanyaan umum.** Kenapa invoice lama tidak memunculkan peringatan ini? Invoice yang dibaca sebelum tahap 6 tidak diminta membaca NPWP, jadi sistem tidak menilainya.

Aturan: pajak-poc.v2.
