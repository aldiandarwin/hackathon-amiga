# OpenAI invoice smoke - hasil langsung

12 Oktober 2026. Tiga panggilan API aktual memakai key yang diizinkan Aldian. Semua dokumen adalah invoice digital sintetis, bukan invoice klien AMIGA.

Hasil: **3/3 kasus** dan **72 pemeriksaan field** lulus. Status kelayakan produksi: **CONDITIONAL**; dataset kecil ini tidak mengukur akurasi produksi atau scan.

| Kasus | Status hasil | Durasi API | Input / output token | Estimasi biaya konservatif | Hasil |
|---|---|---|---|---|---|
| amiga.pdf.normal.v1 | READY_FOR_REVIEW | 7.311 s | 750 / 679 | US$0.00043325 | PASS |
| amiga.pdf.missing_bank.v1 | EXCEPTION | 7.782 s | 738 / 1054 | US$0.00061925 | PASS |
| amiga.pdf.wrong_total.v1 | EXCEPTION | 6.477 s | 751 / 679 | US$0.000433375 | PASS |

Total estimasi usage konservatif: **US$0.001485875**, kurang dari US$0,002. `billed_cost_usd` tetap null karena invoice billing akun tidak dibaca.

Nomor rekening dengan leading zero dipertahankan. Rekening yang tidak ada tetap null dan menghasilkan MISSING_EVIDENCE. Total 510000.00 pada invoice salah tetap disalin tanpa diperbaiki model; validator menghitung 500000.00 dan menghasilkan TOTAL_MISMATCH. Tiga line items dipertahankan pada setiap kasus.

## Anggaran setelah uji

Plafon pengguna US$10; runner dibatasi US$8. Tiga request memakai US$3 cadangan permanen; tersisa US$5 cadangan untuk paling banyak lima percobaan tambahan. **US$3 ini bukan biaya API aktual**. Retry otomatis tidak aktif. Ledger dibaca sebelum setiap POST dan tidak reset per sesi.

Kontrol hanya mencakup runner ini. Aktivitas proyek lain dengan key yang sama berada di luar pencatatan. Pengaturan billing akun dan auto-recharge tidak diubah.

## Bukti dan batas kesimpulan

- Model: gpt-6-luna; prompt amiga-pdf-extract.v1; reasoning none; tier standard/default; max_output_tokens 8192; store=false; tanpa tools.
- Dataset dibekukan sebelum run. Semua tiga kasus berada di regression split; targeted/holdout belum ada. Validasi dataset dasar lulus; mode strict belum lulus karena kelengkapan split.
- Nilai acuan adalah engineering fixture, belum disahkan Finance. Grader memakai exact string/null, Decimal, jumlah baris, status dan required flags.
- Model menerima satu halaman PDF setiap request, tanpa golden JSON. Evidence dicek terhadap embedded PDF text yang dibaca secara independen oleh pypdf.
- Durasi ini hanya satu panggilan per kasus, bukan SLA end-to-end atau benchmark PDF lima halaman.
- Semua hasil live can_approve=false. Master rekening demo bukan bukti identitas rekening nyata.
- Belum menguji foto buram, scan tanpa text layer, tabel panjang, format vendor lain, database/RLS, upload API, atau voucher.
- Tidak ada baseline/candidate comparison dan tidak ada perubahan prompt berdasarkan hasil ini.

## Artefak

[Ringkasan JSON](openai-smoke.json), [setup dan batas biaya](../OPENAI_SETUP.md), [dataset](../dataset/cases.jsonl), [PDF fixture](../../output/pdf/invoice-smoke-pack.pdf), [tes lokal](VERIFICATION.md).

- [amiga.pdf.normal.v1](live/9e2cd35e-d68c-470f-b184-33452b3623ca/result.json): run `9e2cd35e-d68c-470f-b184-33452b3623ca`, UTC `2026-10-12T15:37:50.842398+00:00`.
- [amiga.pdf.missing_bank.v1](live/efb755c3-c8f6-46ad-b066-649cd1464c82/result.json): run `efb755c3-c8f6-46ad-b066-649cd1464c82`, UTC `2026-10-12T15:38:10.365341+00:00`.
- [amiga.pdf.wrong_total.v1](live/c0e4612e-8a91-404c-a5d8-9fcf546a99b4/result.json): run `c0e4612e-8a91-404c-a5d8-9fcf546a99b4`, UTC `2026-10-12T15:38:28.515295+00:00`.

Raw trace disimpan lokal di direktori yang sama dengan result.json dan diabaikan Git. Hash dataset file, input PDF, code serta token usage tersedia pada JSON. Hash dataset file menggunakan bytes asli; validator dataset eksternal mencetak hash canonical JSON yang berbeda metode.

Sumber tarif: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), diperiksa 12 Oktober 2026. Estimator memakai tarif cache-write untuk semua input agar konservatif, tanpa diskon cache hit.
