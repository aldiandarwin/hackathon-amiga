---
sop_id: EXC-BUDGET_BLOCKED
kategori: exception
kode: BUDGET_BLOCKED
tahap: ekstraksi
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/service.py process_next dan intake file kembar; app/static/app.js updateBudget dan loadDetail; app/static/batches.js; app/main.py budget; prototype/amiga_ocr/live_budget.py reserve dan snapshot; app/static/index.html bilah anggaran; prototype/OPENAI_SETUP.md batas biaya; app/README.md penyimpanan dan biaya serta multiple upload; web/app/page.tsx baris dashboard
---

# BUDGET_BLOCKED: ekstraksi AI dihentikan batas anggaran

**Ringkasnya.** Pencatat biaya menolak panggilan AI baru. Penyebabnya batas anggaran eksperimen tercapai, ada catatan request sebelumnya yang statusnya belum jelas, atau file catatan biaya tidak ditemukan. Request masuk EXCEPTION dan tampil "Perlu perhatian". Di hasil batch, filenya tetap "Diterima", karena batas anggaran baru diperiksa saat ekstraksi.

**Pesan di layar.** Antrean menulis "Batas anggaran AI tercapai". Layar review menampilkan "Proses sudah berhenti" dengan keterangan "Pemrosesan berhenti karena batas anggaran atau catatan request sebelumnya. Teruskan ID request ke admin."

**Istilah lain.** anggaran habis, kuota habis, batas biaya, slot uji habis.

**Langkah penanganan**
1. Lihat bilah "Anggaran eksperimen" di bawah antrean untuk sisa slot uji. Slot yang tersisa tidak menjamin pemrosesan jalan. Kalau catatan biaya hilang, bilah menulis "Informasi anggaran tidak tersedia; pemrosesan tetap memeriksa ledger."
2. Tekan "Salin ID untuk admin", lalu teruskan ID itu ke Tech Lead.
3. Untuk latihan atau demo tanpa AI baru, buka invoice yang sudah terbaca di dashboard. Mengunggah ulang file yang sama tidak memproses ulang request ini.

**Dilarang.** Mengunggah ulang berkali-kali. Menghapus, mengganti, atau membuat ulang catatan biaya untuk melewati batas.

**Selesai kalau.** Tech Lead memastikan anggaran dan catatan biaya aman, lalu dokumen diproses ulang. Di aplikasi PoC belum ada tombol proses ulang.

**Pertanyaan umum.** Berapa batas anggarannya? Plafon eksperimen US$10 dengan batas operasional alat US$8. Sejak 14 Okt 2026 setiap percobaan memesan cadangan US$0,30. Percobaan sebelumnya tetap tercatat US$1. Sisa slot tampil di panel anggaran.

Aturan: batasan teknis PoC, bukan aturan Finance.
