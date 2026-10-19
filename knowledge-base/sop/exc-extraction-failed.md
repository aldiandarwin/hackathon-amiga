---
sop_id: EXC-EXTRACTION_FAILED
kategori: exception
kode: EXTRACTION_FAILED
tahap: ekstraksi
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/service.py process_next; app/static/app.js loadDetail dan renderHistory; app/static/batches.js refreshBatch; prototype/amiga_ocr/openai_live.py:21-22 dan 177-203; prototype/amiga_ocr/live_budget.py reserve; BRD dependensi layanan AI/OCR; arsitektur §6 endpoint retry
---

# EXTRACTION_FAILED: AI gagal membaca invoice

**Ringkasnya.** Pembacaan AI berhenti sebelum menghasilkan data. Penyebabnya bisa Bedrock dan cadangan OpenAI sama-sama gagal, hasil AI tidak sesuai kontrak data, atau pembacaan live sedang dimatikan. Request masuk EXCEPTION, tampil "Perlu perhatian", dan belum punya data invoice. Setiap percobaan tetap tercatat, termasuk yang gagal.

**Pesan di layar.** Antrean menulis "AI belum berhasil membaca invoice". Layar review menampilkan "Proses sudah berhenti" dengan keterangan "File asli tetap tersedia. Periksa riwayat atau teruskan ID request ke admin untuk penanganan." Di tab "Riwayat perubahan" tercatat "Ekstraksi dihentikan". Di hasil batch, filenya tetap "Diterima" dengan catatan "AI belum selesai membaca file ini. Buka invoice untuk melihat penyebabnya."

**Istilah lain.** ekstraksi gagal, AI gagal baca, proses error, data invoice tidak muncul.

**Langkah penanganan**
1. Catat nama file dari subjudul layar review, lalu tanggal kejadian dari tab "Riwayat perubahan".
2. Tekan "Salin ID untuk admin", lalu teruskan ID itu ke Tech Lead.
3. Sambil menunggu, PDF asli tetap bisa dibuka untuk pengecekan manual.

**Dilarang.** Mengunggah file yang sama berulang kali. Sistem hanya membuka request lama yang gagal, tanpa memproses ulang.

**Selesai kalau.** Dokumen diproses ulang lewat run baru. Ini prosedur target, di aplikasi PoC belum ada tombol proses ulang.

**Bedanya dengan.** BUDGET_BLOCKED berarti dihentikan batas biaya. PROCESS_INTERRUPTED berarti server berhenti saat proses berjalan.

**Pertanyaan umum.** Kenapa cadangan OpenAI tidak jalan sesudah 19 Oktober 2026? Verifikasi harga OpenAI kedaluwarsa pada tanggal itu. Bedrock tetap membaca seperti biasa.

Aturan: batasan teknis PoC.
