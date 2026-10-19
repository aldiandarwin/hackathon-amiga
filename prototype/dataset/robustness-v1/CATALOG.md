# Synthetic invoice robustness v1

13 kasus rekayasa; bukan invoice klien. Jawaban belum disahkan Finance.

| ID | Kasus | Split | Halaman | Items | Status validasi ideal |
|---|---|---|---|---|---|
| R01 | digital-normal | regression | 1 | 3 | READY_FOR_REVIEW |
| R02 | leading-zero-identifiers | regression | 1 | 3 | READY_FOR_REVIEW |
| R03 | decimal-tax-discount | regression | 1 | 3 | READY_FOR_REVIEW |
| T01 | five-page-line-items | targeted | 5 | 20 | READY_FOR_REVIEW |
| T02 | scan-clean | targeted | 1 | 3 | READY_FOR_REVIEW |
| T03 | scan-skew | targeted | 1 | 3 | READY_FOR_REVIEW |
| T04 | scan-low-resolution | targeted | 1 | 3 | READY_FOR_REVIEW |
| T05 | missing-bank-account | targeted | 1 | 3 | EXCEPTION |
| T06 | incorrect-stated-total | targeted | 1 | 3 | EXCEPTION |
| T07 | duplicate-in-trusted-history | targeted | 1 | 3 | EXCEPTION |
| H01 | alternate-layout-two-pages | holdout | 2 | 8 | READY_FOR_REVIEW |
| H02 | partly-unreadable-account | holdout | 1 | 3 | EXCEPTION |
| H03 | unknown-vendor | holdout | 1 | 3 | EXCEPTION |

Status ideal memakai transkrip authoring lengkap. Status scan pada aplikasi tetap memerlukan review visual; lihat README.
