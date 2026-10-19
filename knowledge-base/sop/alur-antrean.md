---
sop_id: ALUR-ANTREAN
kategori: alur
tahap: antrean
peran: pic-klien, finance-reviewer, service-lead, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 7 dan 8 layar 01; app/main.py listing; app/database.py seed akun dan tim; web/app/page.tsx DashboardPage dan QueueRowView; web/lib/api.ts loadDashboard; web/components/shell.tsx navFor
---

# Antrean: memantau invoice yang masuk

**Tujuan.** Melihat invoice satu klien atau semua klien yang ditugaskan, statusnya, dan mana yang perlu ditindaklanjuti.

**Siapa.** PIC Klien dan Finance Reviewer memakai antrean setiap hari. Manajer Keuangan AMIGA memegang 20 klien, tapi hanya melihat invoice yang menunggu, sudah disetujui, atau dikembalikannya. Service Lead memantau beban kerja dan membagi ulang tugas, yang masih prosedur target.

**Prasyarat.** Akunmu sudah ditugaskan ke kliennya. Dashboard memuat semua klien akunmu sekaligus. Akun dengan lebih dari satu klien bisa mempersempitnya lewat saringan Klien, atau kembali ke "Semua klien".

**Langkah**
1. Buka menu "Dashboard" di sidebar. Finance dan Manajer Keuangan juga punya menu "Persetujuan", khusus invoice yang menunggu keputusannya.
2. Saring status lewat kotak ringkasan atau pilihan Status, misalnya "Belum diajukan", "Perlu perhatian", atau "Siap diperiksa". Manajer Keuangan terbuka di "Menunggu manajer keuangan", akun lain di semua status.
3. Cari lewat vendor, nomor invoice, atau nama file.
4. Klik baris invoice untuk membuka layar review.

**Hasil.** Daftar memuat paling banyak 100 invoice terbaru per klien, yang terbaru di atas. Tiap baris memuat vendor dan nomor invoice, status, kendala, nominal ke vendor, dan waktu dibuat. Daftar diperbarui otomatis tiap 15 detik. Penyaringan per tenggat waktu masih prosedur target.

**Kontrol.** Antrean hanya menampilkan klien yang ditugaskan ke akunmu. Target waktu muat layar antrean maksimal 2 detik.

**Pertanyaan umum.** Invoice lama tidak muncul di daftar? Dashboard PoC hanya memuat 100 invoice terbaru per klien. Klien yang daftarnya terpotong disebut di catatan bawah daftar. Invoice yang lebih lama tetap tersimpan, hanya tidak tampil.
