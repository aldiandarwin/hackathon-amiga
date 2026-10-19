---
sop_id: EXC-TAX_PPN_DIFFERENT
kategori: exception
kode: TAX_PPN_DIFFERENT
tahap: validasi, review, persetujuan
peran: finance-reviewer
status_aturan: poc-teknis
sumber: app/taxes.py compute, PPN, dan ROUNDING_SOURCE; app/static/tax.js taxSummaryHTML dan taxSourcesHTML
---

# TAX_PPN_DIFFERENT: PPN tertulis beda dari hitungan faktur

**Ringkasnya.** Sistem menghitung PPN pembanding: 12% x DPP nilai lain 11/12, dibulatkan per langkah ke rupiah. Hasilnya beda dengan PPN tertulis. Ini peringatan, bukan penghalang approval. Potongan PPh tetap dihitung dari PPN tertulis.

**Pesan di layar.** "PPN tertulis berbeda dari hitungan faktur", disertai ajakan mencocokkan dengan faktur pajak.

**Istilah lain.** selisih PPN, PPN tidak cocok, PPN beda hitungan.

**Langkah penanganan**
1. Bandingkan isian "PPN tertulis" dengan PDF. Scan buram bisa salah baca.
2. Kalau salah baca, koreksi Subtotal, Pajak, dan Total sesuai PDF dengan alasan.
3. Kalau PDF terbaca benar, cocokkan dengan faktur pajak dari vendor.
4. Tulis keputusan Finance di isian "Catatan review" saat menyetujui.

**Dilarang.** Mengganti PPN di draf dengan hitungan sistem kalau invoice mencetak angka lain.

**Selesai kalau.** Angka draf sama dengan PDF, dan selisih yang tersisa sudah dijelaskan di catatan review.

**Bedanya dengan.** TAX_PPN_MISSING berarti nominal PPN kosong atau nol, jadi pajak belum bisa dihitung.

**Pertanyaan umum.** Kenapa invoice tahun 2020 selalu memunculkan peringatan ini? PoC hanya mengenal PPN 12% x DPP nilai lain 11/12. Tarif lama 10% belum didukung, jadi Finance yang menilai.

Aturan: pajak-poc.v2. Panel menautkan "Dasar hukum:" ke sumber resmi.
