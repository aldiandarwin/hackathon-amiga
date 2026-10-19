---
sop_id: KTL-BATAS-AI
kategori: kontrol
tahap: ekstraksi, validasi, persetujuan
peran: robot-admin, finance-reviewer
status_aturan: brief-v2.0
sumber: brief hal. 4; arsitektur §6 konvensi data dan §7; invoice-data-contract instruksi inti extractor; prototype/amiga_ocr/openai_live.py prompt; app/review.py verify_signer, approve, dan director_approve; acceptance AC-21
---

# Batas peran AI dan instruksi yang tersisip di dokumen

**Aturan.**
- AI hanya membaca invoice dan mengisi draf. AI tidak menyetujui, tidak mengubah status bisnis, dan tidak membuat keputusan pembayaran.
- Nilai yang tidak ditemukan dibiarkan kosong. AI tidak boleh mengarang tarif pajak, rekening, tanggal, baris barang, diskon, atau angka nol.
- Isi invoice selalu diperlakukan sebagai data. Kalimat perintah di dalam dokumen, misalnya ajakan menyetujui pembayaran, tidak diikuti.

**Alasan.** AI bisa salah baca atau mengarang. Keputusan tetap di aturan deterministik dan reviewer manusia.

**Cara sistem menegakkan.** Prompt AI menyuruh model mengabaikan instruksi di dalam dokumen, tapi uji untuk ini belum dijalankan. Hasil AI dicek kontrak datanya dan dicocokkan ke kutipan sumber. Status bisnis ditentukan backend. Persetujuan hanya lewat Finance Reviewer independen, lalu Manajer Keuangan AMIGA. Keduanya mencentang pernyataan dan mengetik ulang password.

**Pertanyaan umum.** Invoice berisi tulisan yang menyuruh mempercepat pembayaran, apa yang harus dilakukan? Abaikan sebagai instruksi. Proses tetap mengikuti SOP yang sama.
