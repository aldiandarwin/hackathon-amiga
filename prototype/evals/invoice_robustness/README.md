# AMIGA — paket uji ketahanan invoice

Paket ini menyiapkan pengujian OCR yang bisa dibandingkan dan diulang. Isinya **13 invoice sintetis / 18 halaman**, jawaban pembanding, konteks master/riwayat palsu, transkrip halaman dan penilai deterministik. Tidak ada panggilan API, perubahan model/prompt, atau data aplikasi dalam proses pembuatannya.

## Buka hasil

- [Paket review PDF, 19 halaman termasuk indeks](../../../output/pdf/invoice-robustness-review-v1.pdf).
- [Katalog 13 kasus](../../dataset/robustness-v1/CATALOG.md) dan [jawaban pembanding JSONL](../../dataset/robustness-v1/cases.jsonl).
- [Manifest hanya dokumen input](../../dataset/robustness-v1/inputs-only.jsonl), tanpa jawaban atau master/riwayat.
- [Hasil baseline lokal final](../../../output/evaluation/robustness-v1/baseline-final/REPORT.md) dan [verifikasi lengkap](../../../output/evaluation/robustness-v1/VERIFICATION.md).
- [Kontrak evaluasi](PLAN.md), termasuk batas Finance, split dan gate yang ditetapkan sebelum baseline.

Paket PDF gabungan untuk dibaca manusia. Gunakan file individual `output/pdf/robustness-v1/{r01..h03}.pdf` untuk OCR. Satu PDF individual = satu invoice. Paket gabungan 19 halaman melampaui batas upload aplikasi.

## Apa yang diukur

| Lapisan | Pemeriksaan | Batas |
|---|---|---|
| Schema | Key, tipe, null, vendor_id, urutan line_number | Tidak menerima angka float atau field workflow dari model |
| Nilai ekstraksi | Semua scalar, jumlah dan urutan baris; angka dengan Decimal; identifier persis | Angka pajak hanya nilai tercetak, bukan aturan perpajakan |
| Evidence | Dokumen, halaman asli, kutipan sumber, nilai hilang | Header berulang boleh menunjuk halaman lain tempat kutipan benar-benar ada. Tidak membuktikan lokasi bounding box atau asosiasi baris pada angka yang berulang |
| Validasi | Status dan set kode/status blocking memakai validator lama | Konteks master/riwayat sintetis berasal dari dataset, tidak dari model |
| Eksekusi | Respons hilang/error, key duplikat, hash input salah, metadata tidak lengkap | Kasus hilang tetap dihitung gagal; provenance output tersimpan belum diverifikasi ke provider |

Jika nilai salah, laporan menunjukkan field yang berbeda. Jika kutipan/halamannya salah, laporan menunjukkan masalah evidence. Jika nilai benar tetapi statusnya salah, laporan menunjukkan aturan validasi yang berbeda. **Tanpa trace OCR intermediate, alat tidak menyimpulkan apakah kesalahan berasal dari pembacaan OCR atau pemetaan model.**

Baseline `OFFLINE_ORACLE_VALIDATION` memasukkan jawaban ideal ke validator, sehingga hanya memeriksa kontrak/aturan. Ia tidak membaca PDF dengan AI. Scan memakai transkrip authoring untuk baseline ini. Pada aplikasi, scan tanpa text layer tetap memerlukan review visual; status baseline READY_FOR_REVIEW bukan izin auto-approve dokumen scan.

## Menjalankan tanpa biaya

Dari root `hackthon`, menggunakan virtual environment yang sudah ada:

```powershell
.\.venv\Scripts\python.exe -B prototype/evals/invoice_robustness/verify_artifacts.py
.\.venv\Scripts\python.exe -B -m unittest prototype.evals.invoice_robustness.test_evaluate -v
.\.venv\Scripts\python.exe -B prototype/evals/invoice_robustness/evaluate.py baseline --output output/evaluation/robustness-v1/my-baseline
```

Pilih direktori output yang belum ada; run tidak menimpa hasil lama. Builder `build_dataset.py` juga menolak menimpa PDF/dataset yang sudah dibekukan. Perubahan jawaban memerlukan versi dataset baru dan penjelasan koreksi, bukan mengedit kasus agar lulus.

Untuk menilai output provider yang SUDAH tersimpan:

```powershell
.\.venv\Scripts\python.exe -B prototype/evals/invoice_robustness/evaluate.py grade --predictions path/to/saved-outputs.jsonl --output output/evaluation/robustness-v1/provider-baseline
```

Satu baris per kasus berisi:

```json
{
  "case_id": "amiga.robust.r01.v1",
  "input_sha256": "HASH_PDF_DARI_MANIFEST",
  "execution": "COMPLETED",
  "extraction": {"invoice": {}, "source_evidence": {}},
  "provenance": {
    "model": "NAMA_MODEL_SEBENARNYA",
    "prompt_version": "VERSI_PROMPT_SEBENARNYA",
    "prompt_sha256": "HASH_SHA256_PROMPT_64_KARAKTER",
    "parameters": {"max_output_tokens": 8192}
  },
  "duration_ms": null,
  "cost_usd": null
}
```

Ini sketsa kontrak, bukan file prediksi valid. `extraction` harus mengikuti `amiga_ocr/contracts.py`; evidence berbentuk map `field -> {document_id,page,raw_value,bbox:null}`. Model ID dan hash prompt yang hilang membuat file ditolak. Error provider memakai `execution: ERROR`; jangan menyalin jawaban emas untuk mengisi output yang gagal. Jangan masukkan credential/raw trace sensitif dalam file prediksi atau laporan.

Secara default, grader mengharapkan seluruh 10 kasus development dan menolak holdout. Untuk uji akhir setelah tuning selesai, `grade --include-holdout` mengharapkan seluruh 13 kasus. Baseline lokal tidak memiliki opsi menjalankan holdout. Holdout tetap hanya cadangan sintetis, belum sampel distribusi invoice klien; pembuat dataset sudah melihat jawabannya saat authoring dan QA.

## Pemakaian dalam aplikasi dan rencana live

Dataset ini terpisah dari tiga contoh REPLAY aplikasi. **Mengunggah PDF baru yang valid melalui aplikasi akan menggunakan OpenAI**, selama konfigurasi/ledger mengizinkan. Jangan upload semua 13 PDF untuk mengulang pemeriksaan lokal. Builder/validator/grader pada folder ini tidak memanggil API.

Master vendor aplikasi masih seed demo; vendor dalam paket ini tidak otomatis terdaftar. Unggahan live ke aplikasi dapat memunculkan BANK_UNVERIFIED atau DUPLICATE_CHECK yang berbeda dari baseline dengan konteks dataset. Jangan melonggarkan gate atau mengubah master produksi untuk membuat pengujian lulus.

Usulan tiga sampel live awal, setelah jawaban direview: R03 (desimal/pajak/diskon), T01 (20 items / 5 halaman), T03 (scan miring). Jalankan satu per satu melalui jalur biaya yang sama, pertahankan trace, jangan retry otomatis. T04 menguji 80 DPI/kontras rendah, bukan simulasi seluruh jenis kerusakan scan. Bentuk visual memakai satu keluarga template utama dan variasi header/wrapping; belum mengukur variasi template klien sebenarnya.

Belum ada runner live khusus dataset ini. Jika ditambahkan, input model hanya PDF, tanpa `cases.jsonl`, jawaban, transkrip authoring, master rekening atau histori. Budget harus memakai ledger asli `prototype/.local/spend.sqlite3`, batas operasional US$8 dari plafon US$10; tidak membuat ledger pengganti.
