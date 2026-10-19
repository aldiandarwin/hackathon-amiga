# AMIGA — upload dan review invoice lokal

**Pintu utama:** `http://127.0.0.1:3000/`. Jalankan backend di bawah, lalu `npm run build` dan `npm run start`
di `web/`. Dashboard, unggah, login, review, dan persetujuan dibuka di satu alamat. Port 8787 menjalankan API;
alamat lamanya mengarahkan ke UI pada port 3000. Hanya PIC yang mengunggah; menu Finance dan Manajer Keuangan berisi
**Persetujuan**. Sesudah Finance menyetujui, manajer keuangan masuk lewat **Ganti akun** atau **Masuk sebagai Manajer
Keuangan** pada review, memeriksa **Menunggu manajer keuangan**, lalu menyetujui atau mengembalikan.

Di tab **Data invoice → Nominal**, PPN yang tidak tercantum dapat dipilih sebagai **Tambahkan PPN di atas total invoice**.
Alasan wajib dicatat. Sistem menyimpan total sumber, tambahan PPN, potongan PPh, dan nominal vendor secara terpisah.
Finance wajib mengonfirmasi tambahan ini saat menyetujui. Voucher v7 memakai logo dan palet AMIGA, dengan satu
ringkasan nominal, tiga kotak tanda tangan basah, dan QR yang bisa diklik. Alasan, hitungan rinci, catatan konfirmasi vendor, hash dan jejak review
tersedia di layar review/audit/verifikasi; bagian tersebut tidak dicetak berulang pada voucher.
Penambahan ini tidak otomatis dipilih saat unggah. Voucher v1–v6 tetap dapat dirender tanpa perubahan byte.
Jika Finance sudah menyetujui, perubahan pajak menjadi versi baru yang perlu disetujui ulang sebelum manajer keuangan.

Tahap 1–4 MVP tim 9. Stack: FastAPI, PostgreSQL 17, worker lokal, ReportLab PDF, HTML/CSS/JavaScript. Browser menampilkan halaman PDF asli berdampingan dengan kandidat invoice, kutipan sumber, hasil validasi, dan riwayat koreksi.

## Menjalankan di komputer ini

Dari root `hackthon`:

```powershell
docker compose --env-file .env -f app/compose.yaml up -d --wait
.\app\start.ps1
```

Buka http://127.0.0.1:8787. Akun dan password lokal ada di `.appdata/demo-access.txt`; jangan commit file tersebut. Tim A, `pic@amiga.local` dan `finance@amiga.local`, memegang 10 klien yang sama, termasuk PT Arunika Sejahtera (ARS). Tim B, `pic.b@amiga.local` dan `finance.b@amiga.local`, memegang 10 klien lain, termasuk PT Bumi Persada (BMP). Hanya PIC yang mengunggah. PIC mengoreksi selama invoice belum diajukan, lalu mengajukannya ke Finance. PIC juga dapat membuat klien baru untuk timnya. Finance memeriksa, mengoreksi, lalu menyetujui atau mengembalikan invoice yang sudah diajukan. `manajer.keuangan@amiga.local` adalah Manajer Keuangan AMIGA untuk 20 klien: menyetujui voucher final atau mengembalikannya ke Finance. Uploader tidak dapat menyetujui invoice sendiri.

Server hanya mendengarkan localhost. Jalankan `.\app\start.ps1 -Restart` sesudah mengubah Python. Script hanya menghentikan listener port 8787 apabila command line cocok dengan Python project dan `app.run`; restart dapat memutus pekerjaan aktif, jadi tunggu antrean selesai. Untuk menjalankan di terminal: `.\.venv\Scripts\python.exe -B -m app.run`.

## Setup pertama pada checkout baru

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r app/requirements.lock.txt
.\.venv\Scripts\python.exe -B -m app.configure_local
docker compose --env-file .env -f app/compose.yaml up -d --wait
.\.venv\Scripts\python.exe -B -m app.run
```

`configure_local` membuat password lokal yang belum ada, mempertahankan konfigurasi yang sudah terisi, dan tidak menginisialisasi atau mengubah ledger OpenAI. Jalankan sebelum startup database pertama. Mengganti password setelah database dibuat memerlukan prosedur rotasi tersendiri; seed akun tidak menimpa akun lama.

Tiga tombol contoh bekerja tanpa API key dan memakai hasil OpenAI sintetis tersimpan di `sample-results.json`. File PDF sumber ada di `output/pdf/invoice-smoke-pack.pdf`, beserta kontrak dataset di `prototype/dataset/cases.jsonl`. Hash sumber dan dataset diperiksa sebelum replay. Raw trace API dan credential tidak diperlukan untuk contoh.

## Alur dan kontrak yang sudah berjalan

1. Login membentuk sesi cookie HttpOnly/SameSite, CSRF, dan assignment klien dari server.
2. Upload menerima **1–5 file per batch**: PDF maksimal 5 halaman, atau foto JPG/PNG, maksimal 5 MB per file, satu invoice per file. PDF terenkripsi, gambar rusak, atau ekstensi yang tidak cocok dengan isinya ditolak. Byte asli disimpan di tabel append-only `request_files`, satu transaksi dengan request dan job.
3. Worker membaca dokumen dengan Amazon Nova 2 Lite lewat AWS Bedrock. Kalau Bedrock gagal, OpenAI dipanggil sekali sebagai cadangan. Setiap percobaan, termasuk respons mentahnya, tersimpan di `extraction_runs`. Validasi tetap deterministik. Tidak ada retry otomatis di luar satu cadangan itu. Job yang terputus menjadi exception saat worker berikutnya mulai.
4. PIC mengoreksi data selama invoice belum diajukan; sesudahnya koreksi menjadi tugas Finance. Setiap koreksi memakai alasan dan `expected_version`. Perubahan membuat snapshot baru serta audit before/after. Versi lama tidak ditimpa; konflik versi ditolak HTTP 409.
5. PDF, gambar pratinjau, list, detail dan koreksi memakai pembatasan assignment klien yang sama. PIC tidak dapat mengoreksi draft yang sudah diajukan (HTTP 409 `INTAKE_LOCKED`). Review ini belum merupakan approval pembayaran.
6. Finance memeriksa semua halaman, memberi catatan, lalu menyetujui versi aktif. Server memeriksa ulang total, field wajib, rekening master dan duplikasi dalam transaksi. Pemeriksaan sumber manual dicatat bersama hasil mesin asli.
7. Worker merender voucher demo privat dari snapshot approval. Nomor unik per klien/tahun, satu voucher per versi; klik ganda tidak menambah nomor. Render gagal dapat diulang dari payload yang sama tanpa API baru.
8. Batch menyimpan manifest dan hasil setiap file secara terpisah. File ditolak tidak menghilangkan request valid. Riwayat batch bertahan setelah reload; pengunggah dapat memilih ulang file dengan nama dan isi yang sama untuk melanjutkan item belum terkirim.
9. Koreksi setelah approval membuat versi baru dan menonaktifkan voucher lama. Keputusan, snapshot, dan PDF lama tetap disimpan; unduhan aktif versi lama ditolak HTTP 409.
10. Sebelum submit, pengunggah memilih satu dari empat pilihan pajak: Tanpa pajak, PPN 11% saja, PPh 23 2% saja, atau PPN 11% + PPh 23 2%. Nomor faktur dan NPWP dibaca dari dokumen; Finance hanya mengisi nomor faktur bila muncul `TAX_FAKTUR_NOT_FOUND`. Server memeriksa PPN tertulis terhadap hitungan faktur, lalu menghitung potongan dan jumlah dibayarkan dari tabel `pajak-poc.v2` di `app/taxes.py` (asumsi PoC, perlu konfirmasi Finance). Panel review menautkan dasar hukum resmi dan memberi peringatan per baris bila objek invoice tampak tidak cocok. PIC sebelum mengajukan, atau Finance sesudahnya, dapat mengganti pilihan sebagai versi baru; approval ditahan sampai pajak terhitung dan membekukan blok pajak ke voucher.
11. PIC mengajukan invoice ke Finance dengan centang pernyataan tanggung jawab. Enam isian wajib harus terisi: vendor, nomor invoice, tanggal, mata uang, total, dan nomor rekening. NPWP dan faktur boleh kosong. Catatan minimal 5 karakter wajib bila masih ada kendala atau ada vendor baru. Audit `INTAKE_SUBMITTED` menyimpan teks pernyataan, kendala terbuka, catatan, dan hash isi. Finance tidak dapat menyetujui sebelum pengajuan (`NOT_SUBMITTED`).
12. Vendor yang belum dikenal master klien didaftarkan saat PIC mengajukan, dengan rekening dan NPWP dari invoice. Finance dan manajer keuangan melihat tanda vendor baru yang tidak menahan. Vendor lama tidak pernah diubah; rekening milik vendor lain ditolak `VENDOR_EXISTS`.
13. Klien dipilih sebelum unggah. PIC dapat membuat klien baru; klien itu langsung di-assign ke pembuat, rekan setimnya, dan manajer keuangan aktif, dengan jejak di tabel append-only `client_events`. Nama atau kode kembar ditolak `CLIENT_EXISTS`.

| Endpoint | Fungsi |
|---|---|
| `POST /api/v1/login`, `GET /api/v1/session`, `POST /api/v1/logout` | Sesi lokal |
| `GET /api/v1/requests?client_id=client_a` | 100 request terbaru klien; tanpa `client_id`, 200 request terbaru dari semua klien yang di-assign |
| `POST /api/v1/clients` | `{name, city?, sector?, npwp?, code?}`, hanya PIC, HTTP 201 |
| `POST /api/v1/requests/{id}/submit` | `{expected_version, consent: true, note?}`, hanya PIC klien itu selama belum diajukan |
| `GET /api/v1/tax/rules` | Empat preset dropdown, tabel potongan PPh dan PPN `pajak-poc.v2`, serta tautan sumber resmi |
| `POST /api/v1/intake-batches` | Manifest `{client_id,items:[{filename,byte_size,sha256,tax_selection}]}`, header `Idempotency-Key` |
| `GET /api/v1/intake-batches?client_id=client_a` | 20 batch terbaru klien |
| `GET /api/v1/intake-batches/{id}` | Hasil penerimaan dan status pemrosesan per file |
| `POST /api/v1/intake-batches/{id}/items/{position}` | Raw PDF, hanya pemilik batch; posisi mulai 1 |
| `POST /api/v1/demo-batches/mixed?client_id=client_a` | Dua PDF contoh dan satu file rusak, tanpa API |
| `POST /api/v1/requests?client_id=client_a&filename=invoice.pdf` | Raw body `application/pdf`, header `Idempotency-Key` |
| `POST /api/v1/demo/{normal,missing_bank,wrong_total}?client_id=client_a` | Replay hasil sintetis tanpa API baru |
| `GET /api/v1/requests/{id}` | Draft, validasi, versi, audit, URL dokumen |
| `GET /api/v1/requests/{id}/document` | PDF asli privat |
| `GET /api/v1/requests/{id}/preview/{page}` | PNG halaman, render lokal |
| `PATCH /api/v1/requests/{id}/draft` | `{expected_version, invoice, reason, tax_selection?}` |
| `POST /api/v1/requests/{id}/review` | `{expected_version, reason, source_reviewed: true}` |
| `GET /api/v1/requests/{id}/voucher?version=N` | PDF privat versi aktif yang disetujui |
| `POST /api/v1/requests/{id}/voucher/retry` | `{expected_version, reason}`, hanya render gagal |
| `GET /api/v1/budget`, `GET /api/v1/health` | Status biaya lokal / worker |

Operasi yang mengubah data selain login memerlukan `X-CSRF-Token`. Identitas/role tidak diterima dari JSON browser. Invoice mempertahankan kontrak [prototype](../prototype/README.md): nilai uang berupa string desimal, nilai kosong `null`, rekening string, dan `vendor_id` tidak boleh diisi AI/browser.

## Penyimpanan dan biaya

- PostgreSQL menyimpan data bisnis pada schema `amiga_mvp`; volume berada di `.appdata/postgres`. Saat ini schema dibuat idempoten melalui `schema.sql`, belum sistem migration produksi.
- File asli ada di tabel `request_files` dan dicek ulang hash-nya setiap dibuka. `.appdata/documents` dan `.appdata/previews` hanya cache; voucher tersimpan di `.appdata/vouchers`. Trace upload live ada di `.appdata/traces`. Folder tersebut bukan static web directory.
- SQLite dipakai **hanya untuk ledger biaya lama**, `prototype/.local/spend.sqlite3`. Aplikasi dan CLI memakai ledger yang sama. Tidak ada tombol reset atau retry berbayar.
- Batas pengguna US$10, batas operasional alat US$8, reservasi US$0,30 per upaya generasi sejak 14 Okt 2026 (sebelumnya US$1). Tampilan biaya adalah estimasi berdasarkan usage, bukan tagihan akun resmi. Panggilan di luar alat ini tidak dihitung.
- Upload baru dibaca Bedrock (`AMIGA_EXTRACTION_PROVIDER`, bawaan `bedrock`) dengan ledger `prototype/.local/spend-bedrock.sqlite3`. OpenAI direct PDF menjadi cadangan (`AMIGA_EXTRACTION_FALLBACK`, bawaan `openai`; `none` mematikannya). Variabel environment proses menang atas `.env` untuk dua kunci ini. Agar aktif, gunakan konfigurasi dan ledger yang sudah disetujui pada [OPENAI_SETUP.md](../prototype/OPENAI_SETUP.md). Ledger yang hilang menghentikan proses; jangan membuat ledger baru untuk melewati batas atau menjalankan salinan ledger di beberapa mesin. Verifikasi harga saat ini kedaluwarsa 19 Oktober 2026; pemrosesan live berhenti setelah tanggal tersebut sampai diperbarui.

## Batas tahap ini

Akun lokal, 20 klien, dan master vendor/rekening adalah data demo. RLS, SSO, provisioning user, recovery operasional, backup, pengujian beban, deployment, serta migration produksi belum diterapkan. Aturan Finance masih `demo-rules.v1`.

Koreksi tidak otomatis membenarkan rekening atau menghapus kebutuhan bukti. Scan tanpa text layer ditandai untuk pemeriksaan visual. Tiga contoh memakai nomor invoice yang sama, sehingga contoh berikutnya juga dapat memunculkan flag duplikasi. Upload hash identik dalam klien dan mode yang sama membuka request lama, termasuk request gagal; belum ada alur pengajuan ulang.

Template `amiga-demo-v7` mengikuti Voucher Pengeluaran AMIGA, dengan tiga kotak tanda tangan basah (PIC, Finance, Manajer Keuangan) dan QR verifikasi. Voucher lama tetap `amiga-demo-v1` sampai `amiga-demo-v6`. Nomor `{kode klien}-{urut 5 digit}-{bulan}-{tahun}`, misalnya `ARS-00001-10-2026`, mengikuti pola voucher asli, tapi kode kliennya masih data demo. Manajer Keuangan AMIGA bisa mengembalikan voucher ke Finance. Persetujuan bayar klien tetap di luar aplikasi. PIC mengirim voucher final ke Telegram klien lewat menu Hubungi klien (webhook n8n, `AMIGA_N8N_VOUCHER_WEBHOOK_URL` dan `AMIGA_N8N_WEBHOOK_SECRET` di `.env`); statusnya tercatat terkirim hanya dengan nomor pesan Telegram. Reject, serta aturan dan template final belum diterapkan. Eksekusi pembayaran tetap di luar aplikasi. Adapter OCR.space dan Mistral masih normalisasi respons tersimpan. Transport live memakai Bedrock, dengan OpenAI sebagai cadangan.

## Verifikasi

```powershell
.\.venv\Scripts\python.exe -B -m unittest app.tests.test_app app.tests.test_review app.tests.test_batches app.tests.test_taxes app.tests.test_tax_flow app.tests.test_sop app.tests.test_storage app.tests.test_signoff app.tests.test_presentation app.tests.test_intake app.tests.test_portfolio app.tests.test_chat app.tests.test_handover -v
.\.venv\Scripts\python.exe -B -m unittest discover -s prototype/tests -v
node --check app/static/app.js
node --test app/tests/test_numbers.js
node --test app/tests/test_review_guide.js
node --test app/tests/test_payment_summary.js
node --check app/static/batches.js
node --check app/static/tax.js
node --check app/static/sop.js
node --check app/static/intake.js
node --check app/static/clients.js
```

Ringkasan nominal membedakan total tagihan, PPN, potongan PPh, dan rencana pembayaran ke vendor. Hasil pajak yang belum terhitung, kendala otomatis yang belum selesai, atau koreksi yang belum disimpan menahan tampilan nominal pembayaran; total invoice tidak menjadi penggantinya. Pembayaran dilakukan di luar aplikasi. Finance yang mengunggah diperingatkan bahwa reviewer lain harus menyetujui invoice tersebut.

Tes integrasi membutuhkan PostgreSQL yang berjalan; setiap tes memakai schema dan direktori privat terpisah. Tidak ada API berbayar dalam tes. Schema/data uji disimpan, tanpa penghapusan otomatis. Bukti tahap 1–2 ada di `output/app/`; approval/voucher tahap 3 ada di `output/app-stage3/`; batch tahap 4 ada di `output/app-stage4/`.

[Verifikasi tahap 4](../output/app-stage4/VERIFICATION.md): 80 tes lulus dan smoke API lokal lulus. Inspeksi browser untuk UI batch masih tertahan kebijakan tool; tampilan desktop/mobile dan interaksi file chooser belum dinyatakan terverifikasi.

## Demo tiga akun tanpa biaya API

1. Masuk sebagai `pic.b@amiga.local`, pilih satu klien yang belum pernah dipakai contoh di kanan atas, misalnya **PT Samudra Hasil Bahari**, lalu pilih contoh **Invoice lengkap**. Tombol contoh menunggu satu klien dipilih.
2. Buka request itu, cocokkan data, lalu pilih **Ajukan ke Finance**. Tanggal dipilih dari kalender dan mata uang dari daftar. Isian bertanda **Wajib** yang masih kosong tampil merah, dan tombol Ajukan membawa Anda ke sana. Perubahan yang belum disimpan ikut tersimpan saat diajukan. Centang pernyataan, dan tulis catatan bila masih ada kendala.
3. Keluar, masuk sebagai `finance.b@amiga.local`, buka request yang sama.
4. Cocokkan dokumen di kiri dengan data di kanan. Tiap kendala menulis hitungan dan saran dari angka invoice, tanpa AI. **Pakai saran** hanya mengisi form, lalu Finance menyimpan koreksi. Kendala tidak menahan persetujuan: Finance yang memutuskan, dan kendala yang masih terbuka tercatat di riwayat serta terlihat manajer keuangan. Yang tetap menahan hanya isian wajib yang kosong dan pajak yang belum dipilih atau belum terhitung. Pilih **Setujui**, isi catatan review, centang pernyataan, ketik password akun, lalu **Setujui** di dialog. Kalau data harus dibetulkan PIC, pilih **Kembalikan ke PIC** dengan alasan. Invoice kembali ke **Belum diajukan**, PIC membaca alasannya, memperbaiki, lalu mengajukan ulang. Rekening vendor yang didaftarkan pengajuan itu ikut bisa dibetulkan. Biaya di bawah subtotal (admin, ongkir, tools) diisi di **Biaya lain**, bukan Diskon.
5. Status menjadi **Menunggu manajer keuangan**. Draf voucher resmi ada di tab **Voucher & persetujuan**.
6. Buka `http://localhost:8787` di tab lain, lalu masuk sebagai `manajer.keuangan@amiga.local` dan pilih klien yang sama, atau biarkan **Semua klien**. Antrean manajer keuangan langsung membuka **Menunggu manajer keuangan**, dan menu **Persetujuan** memuat yang menunggu keputusannya.
7. Periksa draf voucher dan invoice asli, lalu pilih **Setujui**, atau **Kembalikan ke Finance** dengan alasan.
8. Sesudah manajer keuangan menyetujui, pilih **Unduh voucher final ↓** dan buka **Halaman verifikasi ↗**. Hash di halaman itu sama dengan hash file yang diunduh. Nomor vouchernya memakai kode klien, misalnya `SHB-00001-10-2026`. Cetak voucher final, lalu PIC, Finance, dan manajer keuangan tanda tangan basah di tiga kotaknya.
9. Untuk uji revisi, kembalikan dari akun manajer keuangan. Finance mengoreksi atau menyetujui ulang versi salinannya, lalu nomor voucher baru terbit.

Voucher lama berformat v1 sampai v3 tidak punya kotak manajer keuangan. Manajer keuangan hanya bisa mengembalikannya, lalu Finance menyetujui ulang dengan format v7.

Jika contoh sudah disetujui, buka hasil tersimpan; jangan membuat dataset/ledger baru hanya untuk mengulang demo. Tiga contoh pada klien yang sama memakai identitas invoice yang sama dan sengaja terdeteksi sebagai kandidat duplikat. PT Arunika Sejahtera dan PT Bumi Persada sudah berisi contoh, jadi contoh baru di sana ditandai sebagai kandidat duplikat. Pakai satu contoh per klien yang masih kosong.

## Ketahanan voucher

Approval, persetujuan Finance, nomor, payload, dan audit disimpan atomik. Salinan final yang disetujui manajer keuangan punya status render sendiri di tabel `voucher_signoffs`, memakai payload beku yang sama, dan ikut diulang lewat retry Finance bila gagal. Render punya status tersendiri (`PENDING`, `RENDERING`, `READY`, `FAILED`), sehingga kegagalan PDF tidak menghilangkan keputusan reviewer. Startup menandai render terputus sebagai gagal; Finance dapat mencoba lagi secara manual. Payload/template/nomor tidak berubah saat retry. File yang sudah ada hanya diterima bila hash sama; file rusak atau berbeda memerlukan penanganan operator, bukan ditimpa otomatis.

Trigger PostgreSQL menjaga keputusan dan snapshot voucher tidak dapat ditimpa. Format PDF memakai dependensi pada lockfile; template yang berubah harus diberi versi baru dan renderer lama dipertahankan bila masih ada pekerjaan tertunda. Master rekening serta user management saat ini hanya seed demo.

## Multiple upload dan pemulihan koneksi

Tombol unggah menerima 1–5 PDF, JPG, atau PNG. Alur yang sama tersedia di dashboard Next.js (`web/`, halaman `/unggah`). Browser menghitung SHA-256 dan membuat manifest, lalu mengirim file satu per satu. Server memeriksa ukuran, hash, format, halaman, sesi dan assignment. Hasil penerimaan (`PENDING`, `ACCEPTED`, `REJECTED`) terpisah dari status request. HTTP 202 pada pengiriman item berarti hasil item dicatat; periksa `items[].status`, bukan hanya kode HTTP.

Buka **Riwayat batch** untuk melihat hasil. Pengunggah memilih **Lanjutkan file yang belum terkirim** dan memilih ulang file aslinya untuk item PENDING. File ACCEPTED tetap menunjuk request yang sama; file REJECTED memerlukan batch baru setelah sumber diperbaiki. Respons yang hilang tidak memicu retry OCR otomatis. Data request/job/audit/tautan item committed dalam satu transaksi.

**Coba batch campuran** menggunakan file sintetis tetap: invoice lengkap, file rusak, dan invoice tanpa rekening. File valid yang pernah diunggah sebagai contoh akan membuka request yang sudah ada; label hasil menjelaskannya. Mode REPLAY tidak dapat dipilih lewat manifest dari browser untuk dokumen sembarang.

Lampiran pendukung, penggabungan beberapa PDF menjadi satu invoice, dan deteksi otomatis beberapa invoice dalam satu PDF belum tersedia. Batas lima file adalah batas demo lokal; kapasitas layanan produksi belum diuji. Setiap file baru tetap melewati ledger lama di worker. Jika saldo slot habis, file dapat diterima tetapi ekstraksinya berhenti sebagai exception anggaran.
