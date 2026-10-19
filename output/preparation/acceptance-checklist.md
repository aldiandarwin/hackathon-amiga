# Checklist penerimaan AMIGA Tim 9

Update 13 Oktober 2026: MVP lokal sudah memiliki intake, review/koreksi, approval independen, voucher, dan batch. **Acceptance produksi belum selesai.** Bukti terbaru: [tahap 4](../app-stage4/VERIFICATION.md), [approval/voucher tahap 3](../app-stage3/VERIFICATION.md), [komponen ekstraksi](../../prototype/output/VERIFICATION.md), serta [tiga smoke OpenAI live](../../prototype/output/OPENAI_SMOKE.md).

Sebanyak 80 tes unik lulus pada pemeriksaan tahap 4: 39 integrasi/dokumen aplikasi dan 41 kontrak ekstraksi/ledger. API aplikasi yang berjalan juga lulus uji batch REPLAY campuran tanpa biaya. Browser tahap 4 diblokir kebijakan tool, sehingga interaksi dan layout fitur batch belum diverifikasi. Bukti visual tahap 3 tidak dianggap mencakup UI batch baru.

Update 14 Oktober 2026 malam, tahap 8: tanda tangan elektronik dua tahap (Finance lalu Direksi AMIGA, BOD internal),
gambar spesimen tanda tangan di voucher, pengembalian ke Finance, kunci sesudah final, voucher v4 dengan QR, dan halaman
verifikasi publik. Persetujuan bayar klien tetap di luar aplikasi. Suite app 164 tes dan prototype 80 tes
lulus. KPI brief diukur ulang dan semuanya di bawah target kecuali satu dokumen sintetis 15,3 detik. Bukti:
[tahap 8](../app-stage8/VERIFICATION.md).

Update 15 Oktober 2026 malam: penyetuju akhir menjadi Manajer Keuangan AMIGA (kode peran tetap `AMIGA_DIRECTOR`,
login `manajer.keuangan@amiga.local`). Hanya PIC yang mengunggah; Finance memeriksa, mengoreksi, menyetujui, atau
mengembalikan. Voucher v7 punya tiga kotak tanda tangan basah (PIC, Finance, Manajer Keuangan) tanpa spesimen dan
tanpa kode. Persetujuan di aplikasi tetap memakai password ulang dan pernyataan. AC-23 sampai AC-26 disesuaikan.

Label **LOKAL LULUS** terbatas pada sampel sintetis dan skenario yang tertulis; **SEBAGIAN** berarti masih ada bagian kriteria yang belum dibuktikan; **BELUM** berarti belum tersedia/diuji. Transport palsu dan REPLAY tidak membuktikan akurasi OCR live atau SLA produksi.

Tambahan 13 Oktober 2026: [paket robustness](../evaluation/robustness-v1/VERIFICATION.md) menyediakan 13 PDF sintetis dan jawaban pembanding. Sepuluh kasus development sesuai validator dengan input ideal, 12 kontrol cacat ditolak, 13 tes grader dan 41 regresi prototype lulus. Tiga holdout belum dievaluasi. Ini kesiapan pengujian; status OCR live lima halaman/scan dan SLA di bawah belum berubah.

## Skenario utama dan kontrol

| ID | Skenario | Hasil yang diharapkan |
|---|---|---|
| AC-01 | Upload invoice valid, review independen dan generate voucher | Alur selesai; PDF memakai approved version |
| AC-02 | Invoice mempunyai minimal 3 line items | Seluruh baris/angka sumber terjaga; kalkulasi benar |
| AC-03 | Nomor rekening tidak tersedia | Null, MISSING_EVIDENCE, EXCEPTION; tidak diisi oleh tebakan AI |
| AC-04 | Vendor/nomor invoice sama pada scope klien yang sama | POSSIBLE_DUPLICATE, keputusan reviewer tercatat |
| AC-05 | Uploader mencoba approve, termasuk dengan beberapa role | Ditolak oleh backend; versi/voucher tidak berubah |
| AC-06 | User klien A mencoba akses request/PDF/voucher/audit B | Tidak terlihat/ditolak; direct object access ikut diuji |
| AC-07 | Reviewer mengganti nominal | Before/after, actor, waktu dan version dapat ditelusuri |
| AC-08 | Batch beberapa invoice dengan satu file invalid | Status per item jelas; request lain tidak hilang/tertukar |
| AC-09 | Invoice 5 halaman, items lintas halaman | Halaman dan urutan lengkap; chunk mapping benar |
| AC-10 | Nominal sumber tidak cocok dengan jumlah item | TOTAL_MISMATCH; tidak mengubah angka sumber diam-diam |
| AC-11 | Data kalkulasi tidak lengkap/angka ambigu | Tidak dinyatakan PASSED; butuh aturan/koreksi yang dapat ditelusuri |
| AC-12 | Vendor invoice sah merupakan revisi | Hubungan revisi dan alasan resolusi jelas; tidak lolos sebagai transaksi baru tanpa konteks |
| AC-13 | OCR timeout/429/response parsial | Retry terbatas; status dan recovery jelas; draft parsial tidak dianggap lengkap |
| AC-14 | Worker restart setelah mengklaim job | Recovery lease; hasil lama tidak menimpa run terbaru |
| AC-15 | Dua editor; edit bersamaan dengan approval | Version conflict atau transaksi konsisten; PDF bukan campuran versi |
| AC-16 | Dua kandidat invoice sama disetujui serentak | Duplicate check saat approval mencegah dua invoice aktif yang sama |
| AC-17 | Data diubah setelah approval | Versi baru perlu review; voucher lama tetap terlacak |
| AC-18 | Render voucher gagal lalu retry | Snapshot approved tetap sama; tidak membuat nomor/voucher ganda |
| AC-19 | Backup tidak ditugaskan / delegasi dicabut | Akses ditolak; handover/assignment tercatat |
| AC-20 | System Admin mencoba approve transaksi | Ditolak; role admin tidak menjadi hak approval |
| AC-21 | Isi invoice mengandung instruksi untuk model | Isi diperlakukan sebagai data; workflow tidak dapat diubah melalui dokumen |
| AC-22 | Pengguna mencoba mengubah/menghapus audit | Ditolak; riwayat bisnis dan snapshot tetap tersedia |
| AC-23 | Finance menyetujui, lalu Manajer Keuangan AMIGA menyetujui | Voucher final memuat tiga kotak tanda tangan basah dan QR; halaman verifikasi menunjukkan sah tanpa nominal dan rekening |
| AC-24 | Manajer Keuangan AMIGA mengembalikan voucher dengan alasan | Approval batal, versi disalin, Finance mengoreksi atau menyetujui ulang dengan nomor baru |
| AC-25 | Data diubah sesudah persetujuan | Edit sesudah persetujuan Finance membatalkan approval; edit sesudah final ditolak |
| AC-26 | Voucher memakai tanda tangan basah | Voucher v7 tidak mencetak spesimen maupun kode; voucher v4 sampai v6 yang sudah terbit tetap utuh; halaman verifikasi tidak menampilkan gambar tanda tangan |

## Cakupan bukti saat ini

| ID | Status | Bukti dan sisa pemeriksaan |
|---|---|---|
| AC-01 | LOKAL LULUS | Upload HTTP dengan transport palsu; alur REPLAY dua akun sampai PDF privat dibuktikan tahap 3. Belum satu alur aplikasi penuh memakai invoice nyata dan OCR live. |
| AC-02 | LOKAL LULUS | Tiga line items sintetis terjaga dalam tes kontrak, smoke OpenAI komponen, serta snapshot voucher. |
| AC-03 | LOKAL LULUS | Rekening hilang menjadi exception; approval ditolak sampai koreksi dan bukti sesuai aturan demo. |
| AC-04 | SEBAGIAN | Kandidat duplikat dan pemeriksaan ulang saat approval teruji. Alur resolusi duplikat/revisi dengan keputusan reviewer belum tersedia. |
| AC-05 | LOKAL LULUS | PIC dan uploader Finance ditolak backend; kombinasi role teruji pada kontrak komponen. |
| AC-06 | LOKAL LULUS | API request/dokumen/preview/audit/voucher/batch memeriksa assignment dan menolak akses silang. RLS database belum diterapkan. |
| AC-07 | LOKAL LULUS | Koreksi tersimpan dengan before/after, actor, alasan dan versi; versi lama tetap tersedia. |
| AC-08 | SEBAGIAN | 12 tes batch dan smoke API berjalan lulus: dua valid/satu invalid, idempotensi, rollback, restart dan resume. UI batch desktop/mobile belum lolos inspeksi browser. |
| AC-09 | SEBAGIAN | Pemetaan lima halaman dan urutan adapter teruji pada respons tersimpan; ekstraksi live invoice lima halaman lintas items belum diuji. |
| AC-10 | LOKAL LULUS | Mismatch diblokir tanpa memperbaiki angka sumber otomatis; teruji pada komponen live sintetis dan aplikasi REPLAY. |
| AC-11 | LOKAL LULUS | Angka ambigu, operand kosong, tanggal tidak valid dan rekening berawalan nol diuji pada kontrak. |
| AC-12 | SEBAGIAN | Revisi dalam satu request kini lewat pengembalian manajer keuangan: versi disalin, Finance mengoreksi atau menyetujui ulang (`test_signoff.py`). Relasi antar-request untuk invoice revisi yang diunggah ulang belum dibuat. |
| AC-13 | SEBAGIAN | Timeout/error/parsial gagal secara tertutup dan ledger tidak direset. Retry OCR otomatis sengaja dinonaktifkan demi anggaran; prosedur pengajuan ulang belum dibuat. |
| AC-14 | SEBAGIAN | Restart worker menandai proses terputus sebagai exception tanpa panggilan API ulang. Lease untuk pemulihan worker produksi belum ada. |
| AC-15 | SEBAGIAN | Versi usang ditolak; edit membatalkan approval; render versi lama tidak dipublikasikan. Edit Finance sesudah persetujuan memblokir persetujuan manajer keuangan (`test_finance_edit_after_signing_blocks_the_director`). Race edit-versus-approval belum diuji secara serentak. |
| AC-16 | SEBAGIAN | Duplicate check saat approval dan approval serentak untuk request yang sama teruji. Dua request kandidat duplikat yang di-approve serentak belum menjadi tes tersendiri. |
| AC-17 | LOKAL LULUS | Koreksi membuat versi baru, membatalkan approval aktif dan memblokir link voucher lama; arsip dipertahankan. |
| AC-18 | LOKAL LULUS | Gagal/restart render dan retry mempertahankan snapshot, nomor serta checksum; tidak membuat voucher kedua. |
| AC-19 | BELUM | Assignment demo statis tersedia; UI/delegasi backup dan alur handover belum diterapkan. |
| AC-20 | SEBAGIAN | Kontrak prototype menolak admin termasuk kombinasi role. User management/role admin pada aplikasi belum tersedia. |
| AC-21 | SEBAGIAN | Kontrak menolak injeksi approval/vendor ID serta payload di luar schema. Uji adversarial dokumen nyata terhadap model belum dilakukan. |
| AC-22 | LOKAL LULUS | Trigger PostgreSQL menjaga audit, versi, keputusan dan snapshot append-only pada skenario uji. Hak superuser database tetap di luar batas proteksi aplikasi demo. |
| AC-23 | LOKAL LULUS | 35 tes `app/tests/test_signoff.py`: alur Finance lalu Manajer Keuangan AMIGA, voucher v7 tiga kotak tanpa kode, hash PDF final sama dengan halaman verifikasi. Uji browser v7 menunggu login demo oleh Aldian. |
| AC-24 | LOKAL LULUS | `test_return_requires_a_reason_and_copies_the_version` dan `test_finance_resigns_a_returned_version_without_changes`. |
| AC-25 | LOKAL LULUS | `test_finance_edit_after_signing_blocks_the_director` dan `test_amiga_approved_request_is_locked`. |
| AC-26 | LOKAL LULUS | `test_v7_prints_no_specimen_while_the_steps_keep_their_hash`, `test_an_approver_without_a_specimen_still_approves`, `test_the_specimen_preview_is_gone`, pin hash v1 sampai v6, dan halaman verifikasi tanpa gambar di `test_public_verification_shows_signers_and_hashes_only`. |

## Performa dan benchmark provider

| ID | Target brief | Pengukuran |
|---|---|---|
| PERF-01 | Ekstraksi PDF hingga 5 halaman <=15 detik | Waktu preflight+OCR+mapping+schema validation; queue wait dan total upload-to-ready juga dicatat |
| PERF-02 | Antrean/review <=2 detik | UI dapat digunakan dengan form dan sumber yang dibutuhkan; kondisi jaringan/file dicatat |
| PERF-03 | Voucher <=3 detik sesudah approval | Dari approval committed sampai PDF tersimpan dan dapat diakses |
| PERF-04 | Voucher final sesudah persetujuan Manajer Keuangan AMIGA (tambahan) | Dari persetujuan manajer keuangan sampai salinan final tersimpan |

Tentukan batas timer dan kondisi demo bersama tim sebelum pengujian. Report hasil gagal secara eksplisit; pemakaian async atau mock tidak dianggap bukti target OCR live terpenuhi.

Status 14 Oktober 2026 malam, tahap 8 ([bukti](../app-stage8/VERIFICATION.md)):

- PERF-01: Bedrock Nova 2 Lite sesudah kirim ulang diam-diam dimatikan. 33 dari 34 dokumen sintetis di bawah 15 detik
  (maks 15,3 detik), 7 dari 7 invoice nyata di bawah 15 detik (maks 7,4 detik).
- PERF-02: antrean median 0,13 detik dan review median 0,15 detik, maks 0,29 detik, 20 kali ukur.
- PERF-03: draf voucher dengan spesimen median 0,55 detik, maks 0,85 detik, 11 kali ukur.
- PERF-04: voucher final dengan dua spesimen maks 0,65 detik, 2 kali ukur.

Ini pengukuran PoC lokal di satu laptop, bukan SLA produksi. Batas 15 detik tidak bisa dijamin 100% untuk model jarak
jauh, jadi hasilnya dilaporkan sebagai persentase dokumen di bawah target.

Bandingkan provider dengan sampel berizin dan expected data yang sama. Catat vendor/nomor/tanggal/rekening/total benar atau salah, item coverage, jumlah koreksi reviewer, latency, actual usage, biaya, error dan fallback. Sampel sintetis berguna untuk development, tetapi hasilnya tidak membuktikan akurasi pada invoice AMIGA nyata.

## Template pencatatan hasil

Untuk setiap ID simpan: file/sample ID, versi code/rules/prompt/schema, provider/model, expected output, actual output, PASS/FAIL/NOT_RUN, durasi/usage jika relevan, screenshot/log teredaksi, dan issue/owner bila gagal. Hindari menyimpan data rekening nyata dalam bukti publik.

## Keputusan sebelum acceptance final

- Checklist Finance: field/lampiran wajib dan sumber verifikasi rekening.
- Rules: perhitungan, rounding, tax/discount, duplicate/revision resolution.
- Template voucher: v7 mengikuti contoh Voucher Pengeluaran AMIGA, dengan tiga kotak tanda tangan basah. Numbering `ARS-00001-10-2026` dan teks batas
  otorisasi masih usulan tim.
- Persetujuan Manajer Keuangan AMIGA di aplikasi: kontrol internal tambahan yang perlu disetujui AMIGA, termasuk siapa
  manajer keuangan dan penggantinya. Voucher v7 memakai tanda tangan basah; TTE tersertifikasi lewat PSrE tetap opsi produksi.
- Role/assignment: reviewer independen dan backup.
- Provider/budget/data permission: OpenAI key dan eksperimen sintetis sudah diizinkan Aldian dengan plafon US$10; runner berhenti pada US$8. Invoice klien berizin dan budget deployment tim masih perlu disiapkan.
- Semantik SENT_TO_CLIENT: download atau konfirmasi handover PIC.

Pemilik keputusan bisnis: Finance/Product Owner AMIGA. Penanggung jawab teknis dan pembagian pengujian perlu dikonfirmasi dalam tim; belum ditetapkan oleh paket ini.
