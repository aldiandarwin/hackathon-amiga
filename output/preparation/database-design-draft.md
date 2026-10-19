# Draft desain database AMIGA

Status: usulan PostgreSQL. Belum ada SQL migration, RLS policy, akun database, atau deployment yang dibuat.

## Struktur inti

| Entitas | Data penting | Relasi / invariant |
|---|---|---|
| `clients` | Identitas dan konfigurasi rules/template | Batas tenant aplikasi |
| `user_profiles` | Auth subject dan nama pengguna | Profil global; role operasional melalui assignment |
| `client_assignments` | Client, user, role, delegator, masa berlaku | Assignment diperiksa pada setiap akses |
| `vendors` | Client, nama sumber dan identitas master | Vendor diselesaikan dalam scope klien |
| `vendor_bank_accounts` | Client/vendor, rekening, bukti dan verifikator | Data OCR tidak otomatis menjadi master terverifikasi |
| `upload_batches` | Initiator, waktu, status intake | Mengelompokkan request, bukan menggabungkan invoice |
| `requests` | Client, batch, PIC, uploader, metadata, state, current/approved version | Satu invoice utama; status dikendalikan backend |
| `documents` | Client/request, type, uploader, object key, checksum, page count | Invoice/lampiran asli privat |
| `processing_jobs` | Request/run, kind, status, attempt, lease token/expiry, next attempt | Klaim atomik dan recovery setelah restart |
| `processing_runs` | Provider/model, prompt/schema version, raw output reference, waktu/usage/error | Riwayat append-only per processing attempt |
| `invoice_versions` | Client/request, version, invoice snapshot, source, actor | Snapshot immutable; machine/human provenance |
| `invoice_line_items` | Client/request/version, urutan, nilai sumber | Item selalu terikat versi invoice |
| `validation_results` | Client/request/version, rules version, checks | Hasil validasi tidak dilekatkan ke versi lain |
| `review_decisions` | Client/request/version, actor, action, alasan, waktu | Approval menunjuk versi eksplisit |
| `voucher_templates` | Client/scope, version, template reference | Template berversi sesuai persetujuan Finance |
| `vouchers` | Client/request, approved version, template version, number, object key/status | PDF terikat snapshot approved |
| `audit_events` | Client/request, action, actor, timestamp, before/after, version/run | Tidak dapat UPDATE/DELETE oleh role aplikasi |

## Tipe dan penyimpanan

ID dapat memakai UUID; Request ID tampilan dipisahkan dari primary key bila diperlukan. Identitas invoice/rekening memakai TEXT. Nominal dan quantity menggunakan NUMERIC dengan precision/scale disepakati; tidak menggunakan floating point untuk uang.

JSONB menyimpan snapshot invoice, source evidence, checks dan metadata provider. Kolom relational menyimpan data untuk pencarian, status dan constraints. PDF/raw artefak besar berada di storage privat; database menyimpan referensi dan checksum.

`client_id` ada pada setiap entitas transaksi. Gunakan composite foreign key untuk request-document-version-voucher agar ID klien yang berbeda tidak dapat dihubungkan. Profile Auth global tidak perlu dipecah menjadi satu profile per klien.

## Constraints dan indexes

- Unique version dalam satu request.
- Unique line number dalam satu invoice version.
- Unique idempotency key processing job pada scope yang disepakati.
- Unique voucher artefak untuk pasangan approved version dan template version, dengan strategi regeneration yang eksplisit.
- Index request pada client+state+received date dan client+due date.
- Index kandidat duplikasi pada client+vendor+nomor invoice ternormalisasi; jangan menolak upload revisi dengan unique invoice number tanpa aturan.
- Index job pada status+next attempt; index audit pada request+timestamp.

## Transaksi review

1. Periksa identitas, role, assignment klien dan uploader.
2. Lock request serta identitas invoice yang dipakai untuk duplikasi, termasuk bila identitas baru belum mempunyai request approved.
3. Baca ulang expected version, blocking checks dan kandidat duplikasi aktif.
4. Tulis review decision, approved version, status, job voucher dan audit dalam satu transaksi.
5. Render PDF di luar transaksi, menggunakan approved snapshot yang immutable.

Revisi invoice mempunyai hubungan eksplisit ke request/invoice asal dan keputusan supersession dari pihak berwenang. Tindakan ini tidak otomatis menyatakan pembayaran sebelumnya dibatalkan.

## Akses dan audit

API, RLS dan storage policy menggunakan client assignment yang berlaku. Service account yang bypass RLS tetap memerlukan pemeriksaan akses eksplisit. Frontend tidak boleh menulis langsung kolom approval, version pointer, vendor verification, atau audit.

Role aplikasi tidak mempunyai hak UPDATE/DELETE terhadap version snapshots dan audit. Mutasi melalui fungsi/role terbatas memastikan perubahan dan audit atomik. Hal ini membatasi pengguna/aplikasi; bukan bukti tamper resistance terhadap administrator database.

Rekening sensitif dan raw extraction tidak dicetak ke log aplikasi umum. Akses object dilakukan sesudah authorization dan dicatat seperlunya. Storage key berbentuk client/request/document membantu pengelompokan, tetapi tidak menggantikan policy akses.

## Kesiapan implementasi

Migration perlu disesuaikan dengan schema dan Auth yang benar-benar digunakan repo tim. Default currency, tipe role, field wajib, status tambahan, retention, numbering voucher, dan matrix duplikasi/revisi belum dianggap keputusan final.
