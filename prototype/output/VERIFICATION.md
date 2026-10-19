# Hasil verifikasi prototype AMIGA

Generated UTC: 2026-10-15T18:35:50.453500+00:00

Hasil: **PASS**. Unit tests: **82**, failures: 0, errors: 0.
Scenario runs: **30**, passed: **30**.

Semua input sintetis dan extraction memakai fixture. Tidak ada API call, billing, atau uji akurasi OCR nyata.
Izin review diuji dengan trusted context lokal; database RLS, autentikasi HTTP, audit persistence, voucher, dan SLA belum diuji.

| Case | Provider mock | Expected | Actual | Result |
|---|---|---|---|---|
| normal | ocr_space | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| normal | mistral | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| missing_bank | ocr_space | EXCEPTION | EXCEPTION | PASS |
| missing_bank | mistral | EXCEPTION | EXCEPTION | PASS |
| wrong_total | ocr_space | EXCEPTION | EXCEPTION | PASS |
| wrong_total | mistral | EXCEPTION | EXCEPTION | PASS |
| duplicate | ocr_space | EXCEPTION | EXCEPTION | PASS |
| duplicate | mistral | EXCEPTION | EXCEPTION | PASS |
| different_client | ocr_space | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| different_client | mistral | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| partial_ocr | ocr_space | EXCEPTION | EXCEPTION | PASS |
| partial_ocr | mistral | EXCEPTION | EXCEPTION | PASS |
| failed_ocr | ocr_space | EXCEPTION | EXCEPTION | PASS |
| failed_ocr | mistral | EXCEPTION | EXCEPTION | PASS |
| unsupported_value | ocr_space | EXCEPTION | EXCEPTION | PASS |
| unsupported_value | mistral | EXCEPTION | EXCEPTION | PASS |
| forged_quote | ocr_space | EXCEPTION | EXCEPTION | PASS |
| forged_quote | mistral | EXCEPTION | EXCEPTION | PASS |
| bank_mismatch | ocr_space | EXCEPTION | EXCEPTION | PASS |
| bank_mismatch | mistral | EXCEPTION | EXCEPTION | PASS |
| unknown_bank_master | ocr_space | EXCEPTION | EXCEPTION | PASS |
| unknown_bank_master | mistral | EXCEPTION | EXCEPTION | PASS |
| unknown_history | ocr_space | EXCEPTION | EXCEPTION | PASS |
| unknown_history | mistral | EXCEPTION | EXCEPTION | PASS |
| missing_discount | ocr_space | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| missing_discount | mistral | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| missing_discount_gap | ocr_space | EXCEPTION | EXCEPTION | PASS |
| missing_discount_gap | mistral | EXCEPTION | EXCEPTION | PASS |
| five_pages | ocr_space | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |
| five_pages | mistral | READY_FOR_REVIEW | READY_FOR_REVIEW | PASS |

Detail checks tersedia pada [verification.json](verification.json).
