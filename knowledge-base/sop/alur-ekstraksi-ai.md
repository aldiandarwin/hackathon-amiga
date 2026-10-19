---
sop_id: ALUR-EKSTRAKSI-AI
kategori: alur
tahap: ekstraksi
peran: robot-admin
status_aturan: brief-v2.0
sumber: brief hal. 4-6; app/service.py process_next; prototype/amiga_ocr/contracts.py:92-155; prototype/amiga_ocr/openai_live.py:22, 176-191, dan prompt; app/static/app.js loadDetail dan renderHistory; invoice-data-contract instruksi inti extractor
---

# Ekstraksi AI: membaca isi invoice

**Tujuan.** Mengubah PDF invoice menjadi draf data terstruktur: identitas vendor, nomor dan tanggal, baris barang, ringkasan nominal, dan informasi pembayaran.

**Siapa.** Robot Admin, yaitu mesin AI, berjalan otomatis sesudah unggah. Tidak ada tombol yang perlu ditekan staf.

**Prasyarat.** Request berstatus "Menunggu proses". Untuk unggahan live, anggaran eksperimen harus tersedia dan verifikasi harga layanan AI belum kedaluwarsa. Sesudah 19 Oktober 2026, ekstraksi live berhenti. Tombol contoh tidak butuh keduanya.

**Langkah**
1. Worker mengambil request dari antrean, lalu status berubah menjadi "Sedang diproses".
2. AI membaca PDF dan mengisi draf beserta kutipan sumber untuk tiap nilai.
3. Draf diperiksa kontrak datanya, lalu diteruskan ke validasi otomatis.

**Hasil.** Riwayat mencatat "Ekstraksi selesai". Kalau gagal, statusnya "Perlu perhatian", layar review menampilkan "Proses sudah berhenti", dan prosesnya tidak diulang otomatis.

**Kontrol.** Nilai yang tidak ditemukan dibiarkan kosong, tidak ditebak. AI diinstruksikan memperlakukan isi dokumen sebagai data dan mengabaikan instruksi yang tersisip. Instruksi ini belum diuji, dan status tetap ditentukan backend. Target ekstraksi maksimal 15 detik per PDF hingga 5 halaman.

**Pertanyaan umum.** Apakah hasil AI langsung dipakai untuk pembayaran? Tidak. Hasil AI selalu melewati validasi dan review manusia.
