---
sop_id: EXC-PROCESS_INTERRUPTED
kategori: exception
kode: PROCESS_INTERRUPTED
tahap: ekstraksi
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/service.py Worker.run; app/static/app.js loadDetail dan renderHistory; app/README.md menjalankan; prototype/amiga_ocr/openai_live.py:173 dan 193; prototype/amiga_ocr/live_budget.py reserve; brief hal. 6 target 15 detik
---

# PROCESS_INTERRUPTED: proses berhenti karena server dimulai ulang

**Ringkasnya.** Server atau worker berhenti saat invoice sedang diproses. Saat worker hidup lagi, request itu ditandai gagal dan tidak diulang otomatis. Request masuk EXCEPTION dan tampil "Perlu perhatian". Kalau proses terputus saat panggilan AI berjalan, catatan biayanya tertinggal belum jelas. Unggahan live berikutnya berhenti sebagai BUDGET_BLOCKED sampai Tech Lead memeriksanya.

**Pesan di layar.** Antrean menulis "Proses pembacaan terputus". Layar review menampilkan "Proses sudah berhenti". Di tab "Riwayat perubahan" tercatat "Proses terputus".

**Istilah lain.** proses terhenti, server restart, macet di sedang diproses, proses putus.

**Langkah penanganan**
1. Catat nama file dari subjudul layar review, lalu tanggal kejadian dari tab "Riwayat perubahan".
2. Tekan "Salin ID untuk admin", lalu laporkan ke Tech Lead bahwa request ini perlu diproses ulang.
3. Untuk mencegah kejadian berikutnya, tim teknis menunggu antrean selesai sebelum memulai ulang server.

**Dilarang.** Mengunggah file yang sama untuk memancing proses ulang. Sistem hanya membuka request lama.

**Selesai kalau.** Dokumen diproses ulang lewat run baru. Ini prosedur target, di aplikasi PoC belum ada tombol proses ulang.

**Bedanya dengan.** EXTRACTION_FAILED berarti proses selesai tapi gagal. PROCESS_INTERRUPTED berarti proses terpotong di tengah jalan.

**Pertanyaan umum.** Invoice saya lama sekali di "Sedang diproses", apakah ini kasusnya? Belum tentu, karena kode ini baru muncul sesudah worker hidup lagi. Satu panggilan AI bisa menunggu sampai 90 detik sebelum dihentikan. Kalau status tidak berubah jauh sesudah itu, laporkan ke Tech Lead.

Aturan: batasan teknis PoC.
