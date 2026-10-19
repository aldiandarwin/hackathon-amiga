# Chat Robot Admin

Chat Robot Admin tersedia di semua layar: dashboard Next.js dan halaman review. Tiap user punya riwayat percakapan
sendiri, dan user lain tidak bisa membukanya.

Chat bisa mencari invoice lama per topik, mencari invoice yang mirip, melacak posisi dan alasan dikembalikan, serta
menjawab pertanyaan SOP. Chat hanya membaca. Menyetujui dan mengembalikan tetap di layar invoice.

## Cara kerja

- **Model.** `gpt-6-luna` lewat OpenAI Responses API, `store: false`, reasoning `none`. Harga diverifikasi
  15 Okt 2026 dan berlaku sampai 22 Okt 2026 (`chat_llm.py`). Sesudah itu chat pindah ke mode cari sampai harga
  dicek ulang.
- **Tool.** Lima tool read-only di `chat_agent.py`: `cari_invoice`, `invoice_serupa`, `detail_invoice`, `cari_sop`,
  dan `kartu_sop`. Kartu invoice dan rujukan SOP di bawah jawaban dibangun server dari hasil tool.
- **Akses.** Sama persis dengan antrean `GET /api/v1/requests`, lewat `chat_search.visible_rows`. Tesnya
  membandingkan keduanya untuk PIC, Finance, dan Manajer Keuangan.
- **Data ke OpenAI.** Vendor, nomor, tanggal, total, status, deskripsi item, nama klien, nama dan jabatan pelaku di
  riwayat, serta alasan dikembalikan. Nomor rekening, NPWP, dan file asli tidak pernah dikirim. Deret 8 digit atau
  lebih di teks bebas disamarkan.
- **Mode cari.** Kalau kunci kosong, anggaran habis, harga kedaluwarsa, atau AI belum menjawab dalam 45 detik, chat
  menjawab lewat pencarian kata kunci tanpa AI. Panel menandainya dengan catatan kuning.
- **Sudah sesuai atau belum.** `detail_invoice` membawa `cek_angka` yang dihitung server: subtotal, diskon, biaya lain,
  dan PPN terhadap total, serta harga yang sudah termasuk PPN. Ada juga keputusan Finance beserta catatan yang ia
  biarkan terbuka, dan `langkah_anda` per peran. Kendala terbuka dibaca sebagai catatan, bukan vonis. Chat hanya
  menyarankan langkah yang bisa dilakukan penanya. Aturan ini lahir dari invoice SIPLah 16 Okt 2026, ketika chat
  menyuruh Manajer Keuangan memilih opsi tanpa PPN.
- **Voucher final dan Hubungi klien.** Di tahap final, PIC diarahkan ke menu Hubungi klien untuk mengirim voucher ke
  Telegram klien. Finance dan Manajer Keuangan tetap selesai. Kiriman tercatat di riwayat dengan label sendiri.
- **Catatan kartu tidak bocor.** Riwayat memberi jawaban lama catatan `[Kartu invoice yang tampil: …]` supaya "yang
  pertama" bisa ditunjuk. QA 16 Okt 2026 menemukan model menyalin catatan itu, id invoice ikut. Server membuangnya
  lewat `no_card_notes`, sama seperti em-dash.

## Tampilan

- **Satu jendela Robot Admin.** Sejak 16 Okt 2026 (Aldian) jendela SOP terpisah dihapus. Di layar review, semanggi di
  bar aksi membuka chat ini, dan badgenya menghitung kendala. Sapaan mendaftar kendala invoice yang sedang dibuka:
  `sop.js` membagikannya lewat `window.amigaRobotChecks` dan event `amiga:checks`. Memilih kendala membuka kartu SOP
  sebagai balasan tanpa AI (`window.amigaSopCard`). AI baru dipakai lewat "Tanya soal ini" atau pertanyaan yang diketik.
- **Hitungan sama dengan bar aksi.** Sejak 16 Okt 2026 (Aldian) badge semanggi dan kalimat "punya N kendala" hanya
  menghitung `approval.blocking_checks`, angka yang sama dengan bar aksi. Sisanya tampil di kelompok terpisah lewat
  `window.amigaRobotCheckGroups`: "Cocokkan dengan dokumen" untuk pemeriksaan sumber, lalu "Catatan".
- **Kendala tetap terjangkau.** Saat percakapan berjalan, bar "Lihat N kendala" di bawah kepala jendela memunculkan
  daftarnya lagi tanpa menghapus percakapan. Link "Panduan SOP" di daftar kendala dan chip "Sumber SOP" membuka
  kartunya di jendela yang sama.
- **Kartu tanpa kode mesin.** Kartu SOP di layar memakai `teks_layar` dari `sop_api.screen_text`: kode kendala jadi
  judul kartunya, status jadi labelnya di layar, kode lain jadi frasa pendek. File kartu tidak berubah, jadi retrieval
  dan AI tetap membaca kodenya. Kode baru di kartu tanpa terjemahan membuat `test_sop.py` gagal.
- **Pintu per peran.** Tombol "Tanya Robot Admin" milik chat disembunyikan di layar review karena semanggi sudah jadi
  pintunya. Manajer Keuangan tidak punya semanggi dan tidak mendapat daftar kendala, jadi tombol chatnya tetap tampil.
- **Jawaban ringkas.** Untuk hasil pencarian, teks jawaban cukup satu sampai dua kalimat. Vendor, total, dan status ada
  di kartu. Tanda pisah panjang dari model diganti koma oleh server (`plain_dashes` di `chat_agent.py`).
- **Paragraf lega.** Satu paragraf paling banyak dua kalimat atau sekitar tiga baris panel. Server memecah paragraf
  yang lebih panjang (`airy` di `chat_agent.py`), karena model tidak selalu patuh prompt.
- **Status kartu terkini.** Kartu invoice di riwayat dibaca ulang tiap kali percakapan dibuka. Invoice yang sudah
  disetujui sejak dijawab tampil "Disetujui final", termasuk di riwayat yang dibaca model.
- **Privasi.** Kalimat privasi tampil di sapaan awal tiap percakapan baru, bukan di bawah kotak ketik.

## Konfigurasi

Semua di `.env` root `hackthon`, yang tidak masuk Git.

- `OPENAI_API_KEY` dan `AMIGA_LIVE_ENABLED=true` sudah dipakai ekstraksi.
- `AMIGA_CHAT_STOP_USD` opsional. Bawaannya 2.00, dan nilai di atas 2.00 ditolak.

Ledger chat ada di `public.chat_usage`, satu untuk semua schema di database ini. Ledger ekstraksi di
`prototype/.local` terpisah dan tidak disentuh.

## Biaya dan waktu

Terukur di QA 15 Okt 2026: median satu panggilan 4,6 detik, rata-rata US$0,00009 per panggilan. Satu pertanyaan
butuh dua sampai empat panggilan, jadi cap US$2 cukup untuk ribuan pertanyaan.

## Sebelum demo

1. Build ulang dashboard karena `web/app/layout.tsx` dan `web/next.config.ts` berubah: `npm run build`, lalu
   `npm run start` di `web/`.
2. Kirim satu pertanyaan sesudah server menyala. Panggilan pertama sesudah prompt atau tool berubah bisa sampai
   16 detik karena OpenAI menyiapkan skema tool.
3. Kirim juga satu pertanyaan SOP. Di QA 15 Okt malam, pertanyaan SOP pertama sesudah server menyala butuh sekitar
   30 detik sampai terjawab, karena kartu SOP baru dimuat saat itu.

## Tes

```bash
.\.venv\Scripts\python.exe -B -m unittest app.tests.test_chat -v
node --test app/tests/test_chat_dock.js
.\.venv\Scripts\python.exe -B -m app.chat_llm --smoke
```

`--smoke` memanggil OpenAI sungguhan di schema `amiga_qa_chat`, biayanya di bawah US$0,001.
