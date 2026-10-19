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

## Jalankan lokal

Prasyarat: Python 3.13, Node.js 24, npm, dan Docker untuk PostgreSQL.

```powershell
git clone https://github.com/aldiandarwin/hackathon-amiga.git
cd hackathon-amiga
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app/requirements.lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m app.configure_local
docker compose --env-file .env -f app/compose.yaml up -d --wait
.\app\start.ps1
```

Di terminal lain:

```powershell
cd web
npm ci
npm run build
npm run start
```

Buka `http://127.0.0.1:3000/`. Kredensial demo dihasilkan lokal oleh konfigurator dan tersimpan
di `.appdata/demo-access.txt`; jangan unggah berkas tersebut. Detail operasional ada di [app/README.md](app/README.md).
Provider live dinonaktifkan pada `.env.example`; aktifkan hanya setelah kredensial dan batas biaya diisi.
Sample replay sintetis tersedia melalui endpoint demo yang didokumentasikan dalam backend.

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

```powershell
cd web
npm test
npm run build
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
