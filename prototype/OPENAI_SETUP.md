# OpenAI untuk eksperimen invoice AMIGA

Konfigurasi lokal sudah dibuat di `.env` pada root `hackthon`, memakai API key yang sudah diizinkan Aldian. Key tidak dicetak ke terminal dan tidak disimpan di dokumen, dataset, atau hasil uji. `.env`, ledger, dan raw trace live diabaikan Git. `.env.example` berisi contoh tanpa secret.

## Batas biaya yang aktif

| Kontrol | Nilai |
|---|---|
| Plafon dari Aldian | US$10 untuk eksperimen ini |
| Batas operasional alat | US$8, boleh diturunkan melalui `.env` |
| Cadangan permanen setiap POST | US$0,30 sejak 14 Oktober 2026 (sebelumnya US$1); termasuk request gagal/timeout |
| Maksimum request generasi | Sebanyak cadangan yang muat di batas operasional, tidak reset harian atau per proses |
| Model yang diizinkan | `gpt-6-luna` |
| Endpoint | `https://api.openai.com/v1/responses` |
| Tier / reasoning / output | Standard (`default`) / `none` / maksimum 8192 token |
| Tools berbayar | Tidak diaktifkan |
| Retry otomatis | 0 |
| Harga terakhir diperiksa | 12 Oktober 2026; review ulang setelah 19 Oktober 2026 |

Cadangan per POST adalah **cadangan otorisasi**, bukan biaya request. Cadangan tidak dikembalikan secara otomatis walaupun usage lebih murah. Tiga percobaan awal menggunakan US$3 cadangan, sementara estimasi biaya usage seluruhnya kurang dari US$0,002. Pada 14 Oktober 2026 cadangan diturunkan dari US$1 ke US$0,30 supaya sisa batas cukup untuk 7 invoice real case. Lima percobaan lama tetap tercatat US$1.

Ledger SQLite berada di `prototype/.local/spend.sqlite3`; transaksi `BEGIN IMMEDIATE` mencadangkan biaya sebelum POST dan mencegah dua request berjalan bersamaan. Jika ada `PENDING`, `UNCERTAIN`, atau `COST_BREACH`, request baru ditolak. Ledger hilang tidak dibuat ulang oleh runner. Jangan menghapus, mengganti, mengembalikan backup lama, atau membuat ledger baru untuk melewati batas.

Dasar cadangan: harga long-context paling konservatif pada model ini adalah US$0,25 per sejuta token input (cache-write) dan US$0,75 per sejuta output. Bahkan 1.050.000 token input + 8192 output menghasilkan US$0,268644; cadangan US$0,30 masih di atas angka itu. Ini menggunakan harga yang diverifikasi, bukan janji harga selamanya. Model, host dan tier dikunci; harga kedaluwarsa memblokir panggilan sampai ditinjau.

Kontrol berlaku pada **runner AMIGA di workspace ini**, bukan seluruh akun OpenAI. Proyek lain yang memakai key yang sama tidak tercatat. Tidak ada perubahan pada saldo, auto-recharge, atau pengaturan billing akun. Laporan biaya berasal dari `usage` dan tarif, bukan tagihan final termasuk pajak. [Dokumentasi spend limits](https://developers.openai.com/api/docs/guides/spend-limits) menjelaskan kontrol akun/proyek serta kemungkinan keterlambatan enforcement.

## Menjalankan

Dari root `hackthon`:

```powershell
# Lokal, tidak ada koneksi atau biaya API:
python -B -X utf8 prototype/live_demo.py
python -B -X utf8 prototype/tools/run_checks.py

# GET untuk cek key dan akses model; tidak membuat generasi:
python -B -X utf8 prototype/live_demo.py --preflight

# Satu panggilan generasi; memakai cadangan dari ledger yang sama:
python -B -X utf8 prototype/live_demo.py --run normal
python -B -X utf8 prototype/live_demo.py --run missing_bank
python -B -X utf8 prototype/live_demo.py --run wrong_total
```

`--run all` menjalankan tiga kasus berurutan dan berhenti pada kegagalan pertama. Pengulangan command adalah request baru dan memakan cadangan baru. Jangan mengulang hanya untuk melihat hasil: baca `output/live/<run_id>/result.json` dan [laporan smoke](output/OPENAI_SMOKE.md).

Transport API dan budget memakai Python standard library. Runner PDF membutuhkan `pypdf`; generator fixture membutuhkan `reportlab`. Keduanya sudah tersedia pada bundled runtime Codex di mesin ini. Pada mesin tim, siapkan dependency tersebut terlebih dahulu sesuai prosedur tim. Tidak ada package yang di-install pada sesi ini.

## Cakupan uji

Alur live adalah satu halaman PDF -> OpenAI Responses structured JSON -> normalisasi kontrak invoice -> validator Decimal dan evidence. Hanya PDF sintetis yang dikirim. Golden answer, master rekening demo, dan isi BRD tidak dikirim ke model. Respons tidak menyimpan state percakapan (`store=false`); ini bukan klaim zero retention pada akun/provider.

Dataset `dataset/cases.jsonl` dan PDF dibekukan sebelum API dipanggil. Tiga kasus adalah regression smoke tests, tanpa targeted set atau holdout. Validator dataset dasar lulus; mode `--strict` sengaja belum lulus karena dua split itu belum tersedia. Tidak ada perbandingan baseline/candidate atau keputusan kelayakan produksi.

Setiap hasil menyimpan model, prompt version/hash, code hash, dataset hash, input hash, token usage, dan durasi request. Golden hanya dipakai oleh grader sesudah model menjawab. Angka dibandingkan dengan Decimal, string/null secara tepat, serta jumlah baris dan flag workflow. Evidence diverifikasi dengan teks yang diekstrak `pypdf` dari PDF, bukan transkripsi model sendiri. Ini cocok untuk PDF digital pada smoke ini; scan tanpa text layer membutuhkan jalur evidence dan evaluasi visual lain.

Rekening/master vendor yang dipakai validator adalah data demo. `READY_FOR_REVIEW` belum approved; semua hasil live tetap `can_approve=false`. Tidak ada API upload, login, database bisnis, audit approval, atau voucher produksi. SQLite di sini hanya mencatat biaya eksperimen; usulan database bisnis tetap PostgreSQL.

Sumber teknis yang diperiksa: [harga dan batas GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [PDF inputs](https://developers.openai.com/api/docs/guides/file-inputs), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [batas token output](https://developers.openai.com/api/docs/guides/token-counting).
