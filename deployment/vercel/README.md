# Deploy AMIGA: Vercel frontend + EC2 backend

Repository publik: `aldiandarwin/hackathon-amiga`. Frontend berada di folder `web/`.
FastAPI, worker, PostgreSQL, dokumen, ledger biaya, dan provider AI tetap di backend EC2.
Voucher terbaru memakai v8: tanda tangan PIC dan vendor; persetujuan Finance dan Manajer Keuangan tetap di aplikasi/QR.

## 1. Siapkan origin backend HTTPS

Gunakan domain API dengan sertifikat tepercaya yang meneruskan request **langsung ke FastAPI di `127.0.0.1:8787`**.
Jangan memakai URL aplikasi Next.js EC2 sebagai backend: proxy berlapis akan memeriksa origin frontend yang berbeda.
Contoh nginx ada di [nginx-backend.conf.template](nginx-backend.conf.template). Sesuaikan domain dan lokasi sertifikat sebelum memasangnya.
Backend tetap hanya mendengarkan loopback; database tidak perlu dibuka ke internet.

Gunakan backend deployment EC2 yang sudah memiliki IAM role/Bedrock. Terapkan perubahan `app/settings.py` dan `app/main.py`
dengan tetap mempertahankan `runtime_scope`, pengaman mode EC2, serta pengaturan provider pada branch `ec2-bedrock-deploy`.
Jangan menimpa seluruh backend EC2 dengan checkout lokal tanpa merekonsiliasi perbedaan tersebut.

Tambahkan dua variabel berikut di environment service backend atau `.env` backend:

```dotenv
AMIGA_PUBLIC_BASE_URL=https://amiga.example.com
AMIGA_PROXY_SECRET=<secret-acak-yang-sama-dengan-Vercel>
```

Buat secret secara privat, misalnya `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Simpan di pengaturan environment; jangan masukkan ke Git, chat, browser, atau variabel `NEXT_PUBLIC_*`.
Secret minimal 32 karakter ASCII tanpa spasi. Dengan secret aktif, **semua route backend** memerlukan header `X-Amiga-Proxy-Secret`.
Cookie login otomatis memakai Secure jika public origin HTTPS. QR voucher baru memakai domain frontend tersebut;
URL QR pada voucher yang sudah ditandatangani tetap mengikuti nilai yang dibekukan saat penandatanganan.

Restart backend pada jendela pemeliharaan setelah job aktif selesai. Health check internal perlu mengirim header secret
dari environment service. Request langsung tanpa secret harus membalas HTTP 403, termasuk `/api/v1/health`.

## 2. Import frontend ke Vercel

| Pengaturan | Nilai |
| --- | --- |
| Git repository | `aldiandarwin/hackathon-amiga` |
| Production branch | `main` |
| Root Directory | `web` |
| Framework | Next.js |
| Build Command | `npm run build` |
| Output Directory | Default Next.js |

Atur variabel **server-only**, tersedia pada build dan runtime:

| Variable | Contoh / ketentuan |
| --- | --- |
| `AMIGA_BACKEND_ORIGIN` | `https://api-amiga.example.com`; origin saja, tanpa path/query, wajib HTTPS publik di Vercel |
| `AMIGA_PUBLIC_BASE_URL` | `https://amiga.example.com`; domain frontend yang benar-benar dipakai pengguna |
| `AMIGA_PROXY_SECRET` | Secret yang sama dengan backend |

Domain `*.vercel.app` boleh dipakai sebagai public origin jika itu domain final yang dipilih. Untuk domain khusus,
hubungkan domain tersebut dan akses aplikasi dari sana. Pemeriksaan origin memakai **persis** origin dan Host yang dikonfigurasi.
Alias lain tidak dapat menjalankan aksi tulis. Origin preview berbeda membutuhkan konfigurasi dan backend uji tersendiri;
jangan mengarahkan semua preview ke data production secara otomatis.

Perubahan `AMIGA_BACKEND_ORIGIN` memerlukan build/deploy ulang karena rewrite dibentuk saat build.
Build Vercel akan gagal dengan pesan nama variabel jika konfigurasi belum lengkap, URL tidak aman, secret terlalu pendek,
atau frontend dan backend menunjuk origin yang sama.

Tidak diperlukan `vercel.json`: route proxy mengikuti `web/next.config.ts` dan `web/proxy.ts`.
Session dan CSRF tetap diverifikasi backend. Secret proxy tidak menggantikan autentikasi pengguna.
Status health `worker_ready` tetap menjadi sumber pemeriksaan worker; HTTP 200 saja belum membuktikan antrean berjalan.

## 3. Validasi deployment

1. Buka domain frontend; login sebagai PIC dan pastikan session tetap tersedia setelah reload.
2. Pastikan cookie `amiga_session` memiliki Secure, HttpOnly, SameSite=Strict.
3. Cek health lewat domain frontend dengan request tanpa cache; pastikan `worker_ready=true`.
4. Uji unggah invoice sintetis, review dokumen sumber, pengajuan PIC, persetujuan Finance dan Manajer Keuangan, lalu unduh voucher v8.
5. Buka QR voucher baru lewat domain frontend. Voucher lama mengikuti URL yang dibekukan.
6. Pastikan request dari origin asing dan API langsung tanpa secret ditolak. Request ber-session tanpa CSRF juga harus ditolak.
7. Uji AI dan Telegram secara terpisah sesuai kredensial serta batas biaya yang disepakati. Build frontend tidak membuktikan integrasi tersebut aktif.

Jangan cache session, API invoice, dokumen sumber, atau halaman review. Middleware backend mengirim `Cache-Control: no-store`.
Saat mengembalikan konfigurasi lokal, kosongkan `AMIGA_PROXY_SECRET`, kembalikan public origin ke localhost,
hapus variabel deployment di environment frontend, lalu build/start ulang. Data invoice dan voucher tidak perlu dihapus.

## 4. Pemeriksaan lokal tanpa data production

```powershell
cd web
npm test
npx --no-install tsc --noEmit
npm run build
cd ..
.\.venv\Scripts\python.exe -m unittest app.tests.test_vercel_proxy app.tests.test_voucher_clean
```

Smoke test transport berada di `web/tests/proxy-smoke.mjs`. Jalankan dengan `AMIGA_TEST_TLS_CERT` dan
`AMIGA_TEST_TLS_KEY` yang menunjuk sertifikat lokal tepercaya untuk localhost/127.0.0.1, lalu
`node web/tests/proxy-smoke.mjs` dari root AMIGA. Test memakai Next.js sebenarnya, gateway HTTPS lokal,
FastAPI melalui HTTPS, dan session sintetis. Database, worker, AI, dan Telegram tidak dijalankan.

## Referensi

- [Next.js rewrites](https://nextjs.org/docs/app/api-reference/config/next-config-js/rewrites)
- [Next.js Proxy: request headers](https://nextjs.org/docs/app/api-reference/file-conventions/proxy)
- [Vercel: external origins dan secret header](https://vercel.com/docs/routing/rewrites)

Hasil pemeriksaan snapshot awal tercatat di `docs/VERIFICATION.md`.
Deployment live, perubahan DNS/sertifikat, IAM, dan pengiriman Telegram perlu diverifikasi pada environment tujuannya.
