# Prototype lokal AMIGA: OCR response -> invoice JSON -> validasi

Status: tersedia demo offline dan runner OpenAI live terpisah. Demo `demo.py` tetap memakai fixture tanpa biaya; `live_demo.py` membaca PDF sintetis melalui API dengan budget persisten. Lihat [konfigurasi OpenAI dan batas biaya](OPENAI_SETUP.md).

## Tujuan

Menjadi fondasi codebase tim dari nol. Dua adapter offline mengubah saved JSON OCR.space/Mistral ke kontrak halaman yang sama. Fixture extractor menyediakan kandidat invoice sintetis; validator dan permission check menjalankan logika lokal. Runner OpenAI terpisah menghasilkan kandidat langsung dari PDF.

Tiga PDF invoice sintetis telah diproses oleh OpenAI: [hasil smoke live](output/OPENAI_SMOKE.md). Modul ini sekarang dipakai oleh [aplikasi upload dan review lokal](../app/README.md). Hasil sintetis tidak membuktikan akurasi extraction pada invoice AMIGA.

## Cara menjalankan dari folder hackthon

```powershell
python -B -X utf8 prototype/demo.py --case normal --provider ocr_space
python -B -X utf8 prototype/demo.py --case missing_bank --provider mistral
python -B -X utf8 prototype/demo.py --case wrong_total --output prototype/output/demo-wrong-total.json
python -B -X utf8 prototype/tools/run_checks.py
```

Semua contoh memakai file sintetis dan input dari fixture. `--output` menyimpan JSON ke path yang dipilih. Opsi `--case` dapat dilihat melalui `python -B prototype/demo.py --help`.

Jika `python` tidak tersedia di terminal tim, gunakan interpreter Python yang disiapkan tim. Tidak diperlukan package install.

## Struktur dan port integrasi

| File | Peran |
|---|---|
| [contracts.py](amiga_ocr/contracts.py) | Tipe provider-neutral, extractor protocol, strict extraction contract |
| [adapters.py](amiga_ocr/adapters.py) | Normalisasi saved response, page mapping, merge chunks |
| [validation.py](amiga_ocr/validation.py) | Evidence, Decimal arithmetic, field wajib, bank/duplicate checks, izin review lokal |
| [pipeline.py](amiga_ocr/pipeline.py) | Orkestrasi dan respons standar, kegagalan -> EXCEPTION |
| [fixtures.py](amiga_ocr/fixtures.py) | Input sintetis dan trusted context untuk demo |
| [test_pipeline.py](tests/test_pipeline.py) | Regression tests lokal |

Input `process_invoice`: raw provider JSON, adapter, extractor, identitas dokumen, expected page count dari intake yang terpercaya, Context dari backend, dan Actor terverifikasi. Jangan menerima Context/Actor/master vendor sebagai klaim dari browser.

`InvoiceExtractor.extract(document)` merupakan port yang nanti diganti dengan OpenAI structured extraction atau parsing document annotations Mistral. Saat ini FixtureExtractor mengembalikan data yang sudah disediakan, bukan menginterpretasikan teks secara otomatis.

Adapter OCR.space/Mistral hanya menormalisasi respons tersimpan. Format dasarnya mengikuti [OCR.space response](https://ocr.space/ocrapi) dan [Mistral OCR response](https://docs.mistral.ai/studio/document-processing/basic_ocr), diperiksa 12 Oktober 2026. Transport live baru tersedia untuk OpenAI direct PDF melalui `openai_live.py`; OCR.space/Mistral belum dipanggil langsung.

## Perilaku yang sudah diimplementasikan

- Nomor rekening tetap string dan leading zero dipertahankan.
- Angka memakai decimal string, diverifikasi dengan Decimal; null tidak dijadikan nol.
- Evidence dipetakan per field, termasuk `line_items[0].quantity`. Kutipan harus ada pada dokumen/halaman asli dan konsisten dengan nilai yang diekstrak.
- Bukti sumber yang hanya merupakan substring identifier lebih panjang ditolak.
- Kandidat duplikasi hanya dicari pada client+vendor+nomor invoice yang sesuai dalam trusted history.
- Master/riwayat yang belum dimuat membuat check NOT_CHECKED dan menghalangi kesiapan review.
- OCR parsial, kontrak malformed, total/line total berbeda, dan rekening tidak terverifikasi menghasilkan EXCEPTION.
- READY_FOR_REVIEW tetap belum approved. Permission helper menolak uploader, System Admin, user tanpa Finance role/client assignment, serta expected version yang berbeda.
- Model tidak boleh mengisi vendor_id atau status/approval. Vendor ID diselesaikan dari trusted demo directory.
- Source response dan supplied fixture tidak ditimpa oleh pipeline.

## Aturan demo dan keterbatasan

Rules default `demo-rules.v1` adalah asumsi prototype, belum checklist Finance: IDR, toleransi nol, total = sum(line totals) - stated discount + stated tax. Format invoice yang memiliki biaya tambahan, withholding, tax-included pricing atau penyesuaian lain memerlukan rules yang disepakati.

Numeric strings dibatasi 40 digit dan array 1000 items untuk prototype. Bounding boxes hanya null. Evidence tanggal memerlukan kutipan ISO; tanggal lokal/angka ambigu dikembalikan untuk review. Kontrak ini lebih ketat daripada contoh ilustratif architecture yang memiliki beberapa evidence agregat per baris.

Quote/value matching memeriksa konsistensi kandidat terhadap teks OCR, bukan keaslian invoice, ketepatan OCR terhadap gambar, kelengkapan semua item dokumen, atau identitas pemilik rekening nyata. Semua itu masih membutuhkan pengujian provider dan review manusia. Negative/credit-note policy juga perlu rules Finance; prototype tidak menetapkan perlakuan bisnis finalnya.

Permission helper bukan authorization API, transaksi approval, atau RLS. Tidak ada database, audit persistence, HTTP endpoint, autentikasi, PDF voucher, deployment atau pengujian performa 15/2/3 detik. Pengujian source-page mapping lima halaman tidak membuktikan PDF lima halaman telah diproses OCR live.

## Bukti dan langkah berikutnya

Jalankan `prototype/tools/run_checks.py` untuk menyimpan [laporan lokal](output/VERIFICATION.md), detail JSON, dan contoh respons. Laporan menyebut scope offline serta live provider calls = 0.

Berikutnya: perluas dataset berizin ke scan dan format invoice lain; bangun backend upload, storage, antrean dan layar review dari fondasi ini; hubungkan vendor/history dengan database. Integrasi bank/review tetap harus diverifikasi ulang di transaksi backend.

Tidak ada commit/push pada tahap prototype ini.
