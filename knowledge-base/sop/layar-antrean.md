---
sop_id: LAYAR-ANTREAN
kategori: layar
tahap: antrean
peran: pic-klien, finance-reviewer, amiga-director
status_aturan: brief-v2.0
sumber: web/app/page.tsx DashboardPage, QueueRowView, Issue, dan pendingNote; web/lib/status.ts STATUSES, displayStatus, dan approvalStage; web/components/shell.tsx navFor; web/lib/api.ts loadDashboard; app/main.py listing; app/presentation.py queue_summary; app/service.py stage; app/taxes.py net_payable
---

# Dashboard antrean invoice

**Bagian layar**
- Menu "Dashboard" di sidebar membuka Dashboard antrean. Daftarnya diperbarui tiap 15 detik, atau lewat "Muat ulang".
- Ringkasan status: kotak "Semua invoice" plus tiga kotak sesuai peran. PIC: "Belum diajukan", "Perlu perhatian", "Siap diperiksa". Finance: "Perlu perhatian", "Siap diperiksa", "Menunggu manajer keuangan". Manajer keuangan: "Menunggu manajer keuangan", "Disetujui manajer keuangan", "Dikembalikan manajer keuangan".
- Daftar invoice punya saringan Klien dan Status, plus pencarian vendor, nomor invoice, atau nama file. Saringan dan kolom Klien hanya ada kalau akun memegang lebih dari satu klien. Pilihannya termasuk "Semua klien".
- Kolom tabel: Invoice, Klien, Status, Kendala, Nominal ke vendor, dan Dibuat (WIB). Klik baris untuk membuka layar review.

**Arti tampilan**
- Menekan kotak ringkasan menyaring daftar ke status itu.
- Judul baris adalah nama vendor, atau nama file kalau vendor belum terbaca. Di bawahnya ada nomor invoice, nama file, "Menunggu dibaca AI", atau "Data invoice belum terbaca".
- Kendala memakai judul kartu SOP untuk kendala pertama, plus jumlah kendala lainnya. Contohnya AI gagal membaca invoice.
- Nominal ke vendor adalah "Jumlah dibayarkan" sesudah potongan PPh, atau Belum ditetapkan selama pajak belum terhitung.
- Invoice yang sudah dibaca AI tapi belum diajukan PIC selalu dihitung "Belum diajukan".
- Manajer keuangan hanya menerima invoice di tiga status kotaknya, dan terbuka di "Menunggu manajer keuangan".

**Pertanyaan umum.** Kenapa angka di kotak ringkasan berbeda dengan jumlah baris tabel? Kotak menghitung semua invoice klien terpilih, sedangkan tabel ikut disaring Status dan pencarian. Keduanya memuat paling banyak 100 invoice terbaru per klien.
