# AMIGA Robot Admin — Hackathon

Proof of concept untuk mengubah invoice vendor menjadi voucher pembayaran dengan ekstraksi AI,
validasi deterministik, pemeriksaan manusia, dan jejak persetujuan.

**Repository:** [aldiandarwin/hackathon-amiga](https://github.com/aldiandarwin/hackathon-amiga).
**Deploy frontend:** [Vercel + backend EC2](deployment/vercel/README.md). Root Directory Vercel: **`web`**.

## Alur dan fitur

1. PIC mengunggah invoice PDF/JPG/PNG, maksimal lima file dan 5 MB per file.
2. AI mengekstrak data; aturan bisnis memeriksa nominal, pajak, rekening, bukti, dan potensi duplikasi.
3. PIC mencocokkan hasil dengan dokumen sumber dan mengajukannya ke Finance.
4. Finance memeriksa, mengoreksi, menyetujui, atau mengembalikan invoice.
5. Manajer Keuangan memberi persetujuan akhir atau mengembalikan ke Finance.
6. Voucher **v8** mencetak dua kotak tanda tangan basah: **Diajukan Oleh (PIC)** dan **Diterima Oleh (vendor)**.
   Persetujuan Finance dan Manajer Keuangan tetap tercatat dalam aplikasi dan melalui QR.

Dashboard, upload, review dokumen berdampingan, chat Robot Admin dengan SOP bersitasi, serta workflow
n8n untuk pengiriman voucher ke Telegram tersedia dalam kode. Integrasi AI/Telegram memerlukan
konfigurasi layanan masing-masing; pembayaran dilakukan di luar aplikasi.

## Arsitektur

| Bagian | Teknologi / folder |
| --- | --- |
| Frontend dan proxy satu origin | Next.js / React / TypeScript, `web/` |
| Backend, auth, review, voucher | FastAPI / Python, `app/` |
| Database dan antrean | PostgreSQL; worker berjalan di backend |
| Ekstraksi dan validasi | `prototype/amiga_ocr/` |
| SOP dan retrieval | 70 kartu di `knowledge-base/sop/` |
| Pengiriman voucher | Workflow n8n di `app/integrations/n8n/` |
| Data pengujian | Fixture sintetis di `prototype/dataset/` dan `output/pdf/` |

Pilihan deployment: **frontend di Vercel, backend + worker + PostgreSQL di EC2**.
Backend menerima secret proxy server-only; autentikasi pengguna, role, dan CSRF tetap diperiksa.
Demo lokal tetap tersedia pada `http://127.0.0.1:3000/` dengan backend loopback port 8787.

## Jalankan lokal untuk penilaian

Jalur utama penilaian adalah **demo replay tanpa API**. Aplikasi memakai dokumen sintetis dan hasil ekstraksi tersimpan.
Instruktur dapat memeriksa pengajuan PIC, koreksi Finance, persetujuan Manajer Keuangan, audit, dan voucher PDF.
Replay tidak menguji kemampuan AI membaca invoice baru. Upload file baru, chat AI, dan pengiriman Telegram memerlukan konfigurasi layanan tersendiri.

### Prasyarat

Panduan ini untuk **Windows dan PowerShell**. Perintah untuk macOS/Linux belum diuji dalam panduan ini.

- Git, Python **3.13**, Node.js **24**, dan npm.
- Docker Desktop sudah dibuka dan engine siap. Database memakai PostgreSQL 17 dari Docker Compose.
- Port **3000** untuk frontend, **8787** untuk backend, dan **15432** untuk database tersedia.
- Internet diperlukan untuk mengunduh repo, dependency, dan image Docker pada setup pertama.

Versi frontend yang pernah dipakai: Node 24.21.0 dan npm 11.19.0. Tidak perlu API key untuk contoh replay.

### Terminal A menjalankan backend

Jalankan clone dari folder kerja pilihan Anda:

```powershell
git clone https://github.com/aldiandarwin/hackathon-amiga.git
cd hackathon-amiga
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app/requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -B -m app.configure_local
docker compose --env-file .env -f app/compose.yaml up -d --wait
$env:AMIGA_PUBLIC_BASE_URL = 'http://127.0.0.1:3000'
.\.venv\Scripts\python.exe -B -m app.run
```

Biarkan terminal ini terbuka. Log Uvicorn harus menyebut `Application startup complete` dan port 8787.
Perintah Python langsung tidak membutuhkan aktivasi venv atau menjalankan berkas `.ps1`.

`configure_local` membuat password database dan akun demo yang belum ada. Konfigurasi yang sudah terisi dipertahankan.
Untuk checkout yang sudah pernah dikonfigurasi, lanjutkan dari langkah Docker dan startup backend.

### Terminal B menjalankan frontend

Buka terminal kedua **di folder `hackathon-amiga` hasil clone yang sama**, yaitu folder yang memuat `app/` dan `web/`.
Lalu jalankan:

```powershell
cd web
npm.cmd ci
npm.cmd run build
npm.cmd run start
```

Biarkan terminal ini terbuka. Buka **http://127.0.0.1:3000/** setelah server Next.js menampilkan `Ready`.
Login dan seluruh pekerjaan pengguna dibuka pada port 3000. Port 8787 melayani backend.
Jangan menyalin `web/.env.example` menjadi env frontend lokal. File tersebut berisi placeholder untuk deployment Vercel.

### Pastikan kedua layanan siap

Di terminal ketiga, jalankan:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/v1/health
Invoke-RestMethod http://127.0.0.1:3000/api/v1/health
```

Keduanya harus menjawab `status = ok` dan `worker_ready = True`. HTTP 200 pada halaman depan saja belum membuktikan backend siap.
Jika salah satu pemeriksaan gagal, periksa tabel troubleshooting sebelum mencoba demo.

### Akun demo dihasilkan di komputer instruktur

Dari folder root hasil clone:

```powershell
Get-Content .appdata/demo-access.txt
```

File itu memuat password lokal untuk akun demo. Password tidak disimpan di repository dan tidak perlu meminta password milik pengembang.
Untuk alur satu tim, gunakan:

| Peran | Email |
| --- | --- |
| PIC Tim B | `pic.b@amiga.local` |
| Finance Tim B | `finance.b@amiga.local` |
| Manajer Keuangan | `manajer.keuangan@amiga.local` |

Gunakan password hasil konfigurator untuk login dan konfirmasi persetujuan. Akun Tim A juga tercantum di file akses.
Ganti peran dengan **Ganti akun**. Untuk penilaian ini, cukup gunakan satu origin `http://127.0.0.1:3000`.

## Demo penilaian tanpa API

1. Buka **http://127.0.0.1:3000/review**, lalu login sebagai PIC Tim B.
2. Pilih satu klien, misalnya **PT Samudra Hasil Bahari**, pada pemilih klien di kanan atas.
3. Pada bagian **COBA ALURNYA**, pilih **Invoice lengkap**. Contoh ini memakai hasil tersimpan, tanpa panggilan AI baru.
   Tombol contoh ada di halaman `/review`, bukan halaman `/unggah`.
4. Cocokkan data dengan invoice sumber. Lengkapi isian wajib dan periksa pilihan pajak, lalu **Ajukan ke Finance**.
   Centang pernyataan dan isi catatan jika masih ada kendala. Simpan URL request agar mudah dibuka kembali.
5. Pilih **Ganti akun**, login sebagai Finance Tim B, lalu buka request yang sama.
   Periksa sumber, nominal, pajak, dan rekening. Simpan koreksi jika ada.
6. Pilih **Setujui**, isi catatan review, centang pernyataan, dan ketik password lokal untuk mengonfirmasi.
   Status berikutnya adalah **Menunggu manajer keuangan**. Draf PDF ada di **Voucher & persetujuan**.
7. Pilih **Masuk sebagai Manajer Keuangan** atau **Ganti akun**, login dengan akun manajer, lalu buka request yang sama.
8. Periksa draf dan sumber invoice. Setujui dengan pernyataan dan password, atau uji **Kembalikan ke Finance** dengan alasan.
9. Setelah disetujui, pilih **Unduh voucher final** dan buka **Halaman verifikasi**.
   Voucher terbaru adalah **v8**, dengan dua kotak tanda tangan basah untuk PIC dan vendor penerima pembayaran.
   Persetujuan Finance dan Manajer Keuangan tercatat di aplikasi. Pembayaran tetap di luar aplikasi.

| Contoh tambahan | Yang diperiksa instruktur |
| --- | --- |
| Rekening kosong | Penandaan informasi yang belum lengkap dan kebutuhan koreksi manusia |
| Total tidak cocok | Perbandingan hitungan dengan angka sumber dan catatan keputusan Finance |
| Coba batch campuran | Dua file sintetis valid dan satu file rusak, dengan status per file |

Gunakan klien lain untuk contoh tambahan jika ingin menghindari penandaan duplikasi antarskenario.
Contoh yang sudah dibuat dapat membuka hasil tersimpan yang sama. Tidak perlu mengunggah ulang atau mengubah ledger.
Link dan QR lokal memakai alamat komputer instruktur; QR tersebut tidak menjadikan aplikasi dapat diakses dari ponsel atau internet.

## Troubleshooting lokal

| Gejala | Pemeriksaan dan tindakan |
| --- | --- |
| PowerShell memblokir script | Gunakan `.\.venv\Scripts\python.exe -B -m app.run` dan `npm.cmd` seperti panduan di atas. Tidak perlu mengubah execution policy. |
| Docker daemon tidak dapat dihubungi | Buka Docker Desktop dan tunggu engine siap, lalu ulangi perintah Compose. |
| PostgreSQL belum healthy | Jalankan `docker compose --env-file .env -f app/compose.yaml logs --tail 40 postgres`. Jika log masih memulihkan database, tunggu sampai `database system is ready to accept connections`, lalu ulangi perintah Compose. |
| Port 3000, 8787, atau 15432 terpakai | Periksa `Get-NetTCPConnection -State Listen` dan pemilik port. Jalankan panduan setelah port standar tersedia. Jangan menghentikan proses yang tidak Anda kenali. Mengubah port frontend juga memerlukan penyesuaian origin backend. |
| Layar menampilkan layanan belum bisa dihubungi | Pastikan terminal A dan B masih hidup, lalu ulangi kedua health check. |
| Login gagal setelah mengganti konfigurasi | Gunakan file akses yang sesuai dengan database lokal. Konfigurator tidak mengganti password akun yang sudah tersimpan di database. |
| Contoh tidak tersedia atau hash sumber berbeda | Pastikan clone lengkap, termasuk `app/sample-results.json`, `prototype/dataset/cases.jsonl`, dan `output/pdf/invoice-smoke-pack.pdf`. |
| Upload file baru berhenti pada pembacaan AI | Jalur replay tidak membaca file baru. Ekstraksi live memerlukan kredensial provider yang valid, ledger biaya, dan verifikasi harga yang masih berlaku. Untuk demo tanpa API, gunakan tombol contoh di `/review`. |

Detail backend ada di [app/README.md](app/README.md), frontend di [web/README.md](web/README.md),
dan konfigurasi ekstraksi live di [prototype/OPENAI_SETUP.md](prototype/OPENAI_SETUP.md).

## Deploy ke Vercel

Import repo ini, pilih **Root Directory `web`**, dan gunakan preset Next.js dengan build `npm run build`.
Domain dan secret sengaja memakai placeholder sampai environment tujuan ditentukan.

| Variable server-only | Nilai yang harus diisi |
| --- | --- |
| `AMIGA_BACKEND_ORIGIN` | Origin backend HTTPS terpisah yang meneruskan langsung ke FastAPI |
| `AMIGA_PUBLIC_BASE_URL` | Origin frontend final, misalnya `https://amiga.example.com` |
| `AMIGA_PROXY_SECRET` | Secret acak yang sama dengan backend EC2 |

Backend memerlukan public origin dan secret yang sama. Jangan menaruh secret pada variabel `NEXT_PUBLIC_*`.
Panduan lengkap, template nginx, dan pengujian sesudah deploy ada di [deployment/vercel/](deployment/vercel/README.md).
Repo ini memuat penyesuaian Vercel; konfigurasi IAM dan service EC2 yang sudah ada harus dipertahankan saat integrasi.

## Verifikasi

Jalankan dari root repo. Hentikan frontend `next start` milik Anda dengan Ctrl+C sebelum build ulang.

```powershell
cd web
npm.cmd test
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe -m unittest app.tests.test_vercel_proxy app.tests.test_sop.SopEndpointTests app.tests.test_voucher_clean
node --test app/tests/test_payment_summary.js app/tests/test_review_guide.js
.\.venv\Scripts\python.exe knowledge-base/tools/bangun_korpus.py --cek
```

Tes database lain membutuhkan PostgreSQL dan konfigurasi lokal. Bukti pemeriksaan snapshot awal:
[docs/VERIFICATION.md](docs/VERIFICATION.md). Lulus tes fixture atau build tidak membuktikan
integrasi AI, Telegram, maupun deployment production sudah aktif.

## Isi publik dan asal kode

Snapshot awal diambil dari modul AMIGA pada `aldiandarwin/aldian_skills`, termasuk voucher v8
(`f0f666f`) dan penyesuaian proxy Vercel pada 19 Oktober 2026. Repo ini dimulai dengan riwayat baru.
Kredensial, riwayat monorepo, data invoice nyata, dokumen brief/BRD klien, database lokal, ledger,
konfigurasi konektor, log runtime, dan dependensi terpasang tidak termasuk snapshot.
Workflow n8n perlu memilih kredensial sendiri setelah import; resource AWS memiliki contoh kosong.

Persetujuan dan pembayaran klien berlangsung di luar aplikasi. Implementasi ini merupakan PoC hackathon;
status integrasi bergantung pada environment yang dikonfigurasi.
