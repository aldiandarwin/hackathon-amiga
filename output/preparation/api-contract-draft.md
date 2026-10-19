# Draft kontrak API AMIGA v1

Status: rancangan awal antarmuka untuk tim. Sebagian endpoint sudah diimplementasikan dalam MVP lokal; daftar kontrak yang benar-benar tersedia ada di [app/README.md](../../app/README.md). Rancangan batch awal di bawah memakai manifest/file references; implementasi lokal memakai manifest diikuti raw PDF per item. Assignment, return/reject, serta handover masih usulan. Base path `/api/v1`.

## Aturan umum

- Identitas aktor berasal dari sesi terverifikasi, bukan `user_id` pada request body.
- Backend memeriksa role dan assignment klien pada setiap endpoint, termasuk sumber PDF/voucher/audit.
- State/version yang dikirim frontend diperiksa ulang terhadap database.
- Semua perubahan bisnis menulis audit dalam transaksi yang sama.
- Error bisnis tidak menampilkan data atau identitas dokumen klien lain.

## Endpoint dan hasil

| Method / path | Input pokok | Hasil |
|---|---|---|
| `POST /intake-batches` | Metadata batch, manifest request, PDF invoice dan lampiran | HTTP 202 bila ada request diterima; status per item |
| `GET /batches/{id}` | Batch ID | Daftar request accepted/rejected dan status masing-masing |
| `GET /requests` | Filter client/status/exception/due date, pagination | Antrean yang boleh diakses user |
| `GET /requests/{id}` | Request ID | Metadata, draft version, evidence, checks dan permitted actions |
| `GET /documents/{id}/access` | Document ID | Akses PDF privat setelah authorization |
| `PATCH /requests/{id}/draft` | `expected_version`, perubahan field, alasan | Versi baru dan hasil validasi ulang |
| `POST /requests/{id}/retry` | Alasan, expected processing run/version | Job/run baru; tidak menimpa history |
| `POST /requests/{id}/review` | Action, `expected_version`, catatan | Approval/return/reject dan voucher status |
| `POST /requests/{id}/assignment` | PIC/reviewer/backup yang ditugaskan, alasan | Assignment baru dan audit |
| `GET /requests/{id}/voucher` | Request ID | PDF/status yang terikat approved version |
| `POST /requests/{id}/handover` | Approved voucher/version dan catatan handover | Pencatatan handover; detail semantik perlu keputusan PO |
| `GET /requests/{id}/audit` | Request ID dan pagination | Timeline read-only sesuai akses |

## Intake dan multiple upload

Manifest wajib mengelompokkan file: satu request mempunyai satu invoice utama dan daftar lampiran. Multiple invoice bukan otomatis satu request. Satu PDF yang ternyata berisi beberapa invoice perlu ditandai untuk keputusan PIC pada PoC.

Satu item intake memuat `client_id`, request type, channel, received date, invoice file reference, supporting file references, dan metadata opsional sesuai checklist. Backend memeriksa klien dan file reference tersebut; path/nama file tidak dipakai sebagai identitas terpercaya.

Respons batch mempunyai `batch_id`, `items`, dan ringkasan accepted/rejected. Setiap accepted item memuat `request_id`, `request_status: QUEUED`, dan URL status. Rejected item memuat client-side item reference dan error yang relevan, sehingga dokumen lain tetap dapat ditemukan.

Idempotency key intake berlaku untuk user+operasi+payload yang sama. Mengulang key dengan payload berbeda ditolak. Pengiriman invoice baru dengan key berbeda tetap melalui duplicate check bisnis.

File divalidasi dan tersimpan sebelum request dinyatakan accepted; request+job+audit committed bersama. Kegagalan storage tidak menghasilkan job yang mengacu ke file tidak tersedia.

## Koreksi dan approval

PATCH draft menghasilkan versi baru; respons dari editor lama mendapat `409 VERSION_CONFLICT`. Koreksi field menjalankan checks ulang. Perubahan setelah approval memerlukan review baru; voucher sebelumnya tidak dipakai untuk versi baru.

Review action: `approve`, `return`, `reject`. Return/reject memerlukan alasan. Approve wajib memeriksa Finance Reviewer, assignment klien, uploader != reviewer, versi belum berubah, status sesuai, blocking checks telah diselesaikan, dan pemeriksaan duplikasi terbaru.

System Admin tidak memiliki approval transaksi. Service Lead menangani assignment sesuai kewenangan. Penyelesaian exception dan approval tidak menerima klaim `checks_passed` dari frontend.

Review success mengembalikan `approved_version` dan `voucher_status`; approval dapat berhasil sementara rendering masih PENDING/FAILED. Retry rendering tetap memakai snapshot yang sama, bukan latest draft.

## State dan error

State brief: `QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `EXCEPTION`, `AMIGA_REVIEWED`, `SENT_TO_CLIENT`. `REJECTED` adalah state tambahan yang diusulkan. Job dan voucher mempunyai status teknis terpisah.

| HTTP / code | Kondisi |
|---|---|
| 401 `UNAUTHENTICATED` | Sesi tidak valid |
| 403 `FORBIDDEN` / `SELF_APPROVAL_FORBIDDEN` | Aksi tidak boleh dilakukan oleh aktor |
| 404 `NOT_FOUND` | Resource tidak ada atau tidak boleh terlihat oleh user |
| 409 `VERSION_CONFLICT` / `INVALID_TRANSITION` | Versi/status tidak sesuai |
| 413 `FILE_TOO_LARGE` | Batas upload aplikasi terlampaui; batas aplikasi belum dikunci |
| 422 `INVALID_DOCUMENT` / `INVALID_PAYLOAD` | File/payload tidak valid |
| 422 `UNRESOLVED_EXCEPTION` | Approval mempunyai blocking check |

Provider error sesudah HTTP 202 masuk status processing/checks request, bukan membuat seluruh batch gagal. Frontend menampilkan status dan aksi retry/manual review yang boleh dilakukan. Detail timeout, retry limit, dan interval polling masih konfigurasi usulan.
