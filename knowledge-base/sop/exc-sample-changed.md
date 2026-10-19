---
sop_id: EXC-SAMPLE_CHANGED
kategori: exception
kode: SAMPLE_CHANGED
tahap: intake, ekstraksi
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/service.py sample_input dan process_next; app/main.py demo dan demo_batch; app/batches.py demo dan receive; app/static/app.js enter dan loadDetail; app/static/review-guide.js amigaReadFailure; app/sop_api.py label; web/app/page.tsx tanda Contoh; app/README.md contoh tanpa API key
---

# SAMPLE_CHANGED: file contoh demo tidak cocok dengan hasil tersimpan

**Ringkasnya.** Request contoh memakai PDF sintetis dan hasil AI yang sudah disimpan, jadi tidak memanggil AI baru. Di dashboard, barisnya bertanda Contoh. Kalau file contoh atau datasetnya berubah, hasil tersimpan tidak boleh dipakai lagi. Ini hanya terjadi pada request contoh. Aplikasi tidak lagi punya tombol untuk membuat request contoh baru.

**Pesan di layar.** Di dashboard, kolom Kendala menulis File contoh demo tidak cocok dengan hasil tersimpan. Layar review menulis "AI belum berhasil membaca invoice" dan "Proses sudah berhenti".

**Istilah lain.** contoh gagal, tombol contoh error, data demo berubah.

**Langkah penanganan**
1. Jangan mengubah file contoh atau hasil tersimpannya untuk memaksa contoh jalan.
2. Tekan "Salin ID untuk admin", lalu teruskan ID itu ke Tech Lead. Pemulihan file contoh adalah tugas tim teknis.
3. Untuk demo, pakai invoice lain yang sudah ada di antrean.

**Dilarang.** Mengedit PDF contoh, dataset, atau file hasil tersimpan.

**Selesai kalau.** Tim teknis memulihkan pasangan file contoh dan hasilnya. Request contoh yang sudah gagal tidak diproses ulang.

**Pertanyaan umum.** Apakah ini berpengaruh ke invoice unggahan biasa? Tidak. Kode ini khusus request contoh.

Aturan: batasan teknis PoC.
