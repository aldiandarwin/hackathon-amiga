---
sop_id: KTL-MULTI-KLIEN
kategori: kontrol
tahap: antrean, review, audit
peran: pic-klien, finance-reviewer, service-lead, system-admin
status_aturan: brief-v2.0
sumber: brief hal. 7 dan hal. 9 skenario 6; BRD 6.3 risiko; app/main.py listing, detail, document, dan preview; app/database.py seed klien, tim, dan scoped_request; app/clients.py; app/batches.py scoped dan listing; app/review.py download dan verification; app/verify_page.py; web/app/page.tsx filter Klien; app/static/app.js fillClientSelect; app/README.md alur; output/preparation/api-contract-draft.md state dan error; acceptance AC-06
---

# Keamanan multi-klien: akses hanya ke klien yang ditugaskan

**Aturan.** Setiap akun hanya boleh melihat request, PDF, pratinjau, voucher, hasil batch, dan riwayat milik klien yang ditugaskan kepadanya.

**Alasan.** AMIGA melayani banyak klien. Data satu klien yang terlihat oleh pengguna klien lain adalah masalah kritis.

**Cara sistem menegakkan.** Penugasan klien dibaca dari server, bukan dari isian browser. Di data demo, tim A dan tim B masing-masing memegang 10 klien. PIC dan Finance satu tim memegang klien yang sama, sedangkan Manajer Keuangan AMIGA memegang 20 klien. Permintaan data klien lain, termasuk lewat alamat langsung, dijawab NOT_FOUND seolah datanya tidak ada. Setiap pilihan klien di aplikasi hanya berisi klien yang ditugaskan. Dashboard dan layar review menambah "Semua klien" bila kliennya lebih dari satu.

Klien baru buatan PIC langsung ditugaskan ke PIC dan Finance timnya, juga ke Manajer Keuangan AMIGA. Tim lain tidak melihatnya. Nama klien atau kode voucher yang sudah dipakai ditolak dengan CLIENT_EXISTS. Akses Backup terbatas pada klien yang didelegasikan, yang masih prosedur target.

Pengecualiannya halaman verifikasi dari kode QR voucher final. Halaman itu terbuka tanpa akun, tapi hanya memuat nomor voucher, status, penanda tangan, dan hash.

**Pertanyaan umum.** Saya perlu membantu klien lain, bagaimana caranya? Minta penugasan resmi. Pembagian tugas diatur Service Lead, sedangkan akun dan hak akses dikelola System Admin. Keduanya masih prosedur target, karena penugasan di PoC mengikuti tim akun demo.
