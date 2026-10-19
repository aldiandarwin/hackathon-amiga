---
sop_id: ALUR-HUBUNGI-KLIEN
kategori: alur
tahap: serah_terima
peran: pic-klien
status_aturan: poc-teknis
sumber: Aldian 16 Okt 2026; app/handover_api.py overview, add_contact, disable_contact, dan send; app/handover_n8n.py; app/schema.sql client_contacts dan voucher_deliveries; web/app/hubungi-klien/page.tsx
---

# Hubungi klien: kirim voucher final ke Telegram klien

**Tujuan.** Menyerahkan voucher final ke klien lewat Telegram, dengan bukti kirim yang tercatat.

**Siapa.** Hanya PIC, untuk klien timnya. Finance dan manajer keuangan melihat jejak kirimnya di riwayat invoice.

**Prasyarat.** Status "Disetujui final" dan voucher final sudah jadi. Penerima sudah menekan Start di bot Telegram AMIGA, dan ID Telegram-nya terdaftar untuk klien itu.

**Langkah**
1. Buka menu "Hubungi klien" di sidebar.
2. Untuk demo, setiap klien sudah punya penerima bawaan "Aldian (demo)". Penerima lain didaftarkan sekali di bagian Penerima Telegram: nama dan ID Telegram. ID grup diawali tanda minus. Admin AMIGA melihat ID itu dari pesan Start yang diterima bot.
3. Pilih voucher dan penerima, cek pratinjau pesannya, lalu centang konfirmasi.
4. Tekan tombol Kirim ke Telegram, lalu tunggu status Terkirim beserta bukti nomor pesan Telegram.

**Hasil.** Klien menerima PDF voucher final dengan ringkasan nomor voucher, invoice, vendor, nilai bayar, dan waktu persetujuan manajer keuangan. Status invoice tetap "Disetujui final".

**Kontrol.** Satu voucher dikirim satu per satu. Kiriman kedua saat yang pertama masih berjalan ditolak dengan HANDOVER_BUSY. Status terkirim hanya dicatat sesudah Telegram memberi nomor pesan. Riwayat hanya menyimpan 4 digit akhir ID Telegram.

**Pertanyaan umum.** Muncul HANDOVER_NOT_CONFIGURED? Artinya "Pengiriman Telegram belum aktif." Admin AMIGA belum mengisi sambungan pengirimnya (n8n), jadi voucher belum bisa dikirim. Muncul HANDOVER_FAILED? Telegram belum menerima voucher. Coba lagi, atau hubungi admin. Muncul HANDOVER_UNCERTAIN? Artinya "Status kiriman belum pasti." Cek Telegram penerima dulu sebelum mengirim ulang, supaya voucher tidak terkirim dua kali.
