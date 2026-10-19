# Google OCR — eksperimen invoice AMIGA

Permintaan Aldian: menguji alternatif Google selain OpenAI memakai kuota OCR gratis 1.000 unit. Credential ditemukan pada field `key` di `.env`; hanya keberadaan/formatnya diperiksa, nilainya tidak dicetak atau dimasukkan artefak.

## Pilihan layanan

- **Cloud Vision `DOCUMENT_TEXT_DETECTION`**: mengambil teks dan layout dari gambar dokumen. Ini jalur yang dipilih untuk kuota gratis 1.000 unit pertama per bulan. Satu halaman PDF dirender lokal menjadi satu gambar dan memakai satu fitur, sehingga satu halaman = satu unit. Tidak memakai Cloud Storage, Gemini, Invoice Parser atau OpenAI.
- **Document AI Invoice Parser**: mengeluarkan entity/line items invoice, mempunyai harga terpisah US$0.10 per dokumen hingga 10 halaman. Bahasa Indonesia belum tercantum pada daftar bahasa processor tersebut. Tidak dijalankan pada eksperimen ini.
- **Enterprise Document OCR**: alternatif Document AI yang mendukung bahasa Indonesia dan OCR teks; membutuhkan konfigurasi processor/auth yang berbeda dari API key Cloud Vision yang tersedia.

Sumber resmi diperiksa 13 Oktober 2026: [gambaran OCR Google](https://cloud.google.com/use-cases/ocr?hl=id), [harga Cloud Vision](https://cloud.google.com/vision/pricing), [setup termasuk billing](https://docs.cloud.google.com/vision/docs/setup), [OCR Vision](https://docs.cloud.google.com/vision/docs/ocr), [harga Document AI](https://cloud.google.com/products/document-ai/pricing), dan [processor/bahasa](https://docs.cloud.google.com/document-ai/docs/processors-list).

## Hasil aktual

Satu request live dikirim memakai R03, satu halaman, raster 150 DPI, fitur tunggal `DOCUMENT_TEXT_DETECTION`. Google mengembalikan **HTTP 403 / PERMISSION_DENIED / BILLING_DISABLED**. Tidak ada teks OCR, tidak ada retry dan tidak ada panggilan ke sampel lain. Hasil teredaksi tersimpan di [initial-smoke.json](../../../output/evaluation/google-vision/initial-smoke.json); raw error hanya di `.appdata/google-vision` yang diabaikan Git.

Status kualitas OCR: **INCONCLUSIVE** karena tidak ada output. Status ekstraksi JSON invoice: **NOT_TESTED**. Error ini membuktikan prasyarat billing belum siap, bukan bahwa OCR Google akurat atau buruk.

Google mensyaratkan billing aktif meskipun memakai free tier. Aktivasi/link akun billing harus dilakukan pemilik project. Pastikan Cloud Vision API aktif pada project yang memiliki API key yang sama, serta sisa kuota gratis cukup untuk tujuh halaman. Sisa kuota bulanan dan tagihan akun tidak dapat dibaca dengan credential saat ini; biaya nol hanya berlaku jika kuota gratis masih tersedia.

## Runner yang disiapkan

`probe.py` default hanya membaca input, memeriksa hash PDF/page count dan menunjukkan rencana lokal. Tidak melakukan request:

```powershell
.\.venv\Scripts\python.exe -B prototype/evals/google_vision/probe.py
.\.venv\Scripts\python.exe -B -m unittest prototype.evals.google_vision.test_probe -v
```

Setelah billing/API dan free quota siap, command live yang tersedia:

```powershell
.\.venv\Scripts\python.exe -B prototype/evals/google_vision/probe.py --run --cases r03 t01 t03 --output output/evaluation/google-vision/live-01
```

Ini membutuhkan direktori output baru. R03 satu halaman, T01 lima halaman, T03 satu halaman: **maksimal tujuh unit per run**, tiga request dokumen. Runner berhenti pada error pertama dan tidak retry. Cap berlaku per run; menjalankan command live berulang dapat memakai unit tambahan. Tidak ada reset atau modifikasi ledger OpenAI, dan ledger tersebut tidak mencatat penggunaan Google.

Endpoint tetap `vision.googleapis.com`; key dikirim melalui header `X-Goog-Api-Key`, bukan URL. Payload hanya berisi gambar halaman dan satu fitur. Output JSON tidak mencetak key atau pesan error mentah yang mungkin memantulkan credential. Respons parsial/halaman kosong tidak dinyatakan lengkap.

Pada run yang berhasil, runner menyimpan teks per halaman dan **source quote coverage** terhadap jawaban dataset. Jawaban tidak dikirim ke Google dan tidak dipakai untuk mengisi hasil OCR. Coverage hanya menunjukkan apakah kutipan nilai tersedia; belum membuktikan pemetaan field, urutan/kelengkapan line items, hubungan kolom tabel, rekening terverifikasi atau accuracy JSON invoice. Untuk itu diperlukan mapper/extractor terpisah yang hasilnya dinilai dengan evaluator invoice yang sudah ada.

Enam tes offline lulus: jumlah unit, case duplikat, payload tanpa jawaban, key melalui header, error billing terminal, halaman parsial dan timeout tanpa retry. Log: [offline-tests.log](../../../output/evaluation/google-vision/offline-tests.log). Ini tes runner dengan respons palsu, bukan keberhasilan OCR live.

Tidak ada perubahan billing, IAM, API activation, prompt/model, database aplikasi atau dependency installation selama percobaan. Eksperimen belum terhubung ke UI upload aplikasi; UI tersebut tetap memakai jalur OpenAI lama.
