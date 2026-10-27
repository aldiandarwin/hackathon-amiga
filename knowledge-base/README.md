# Knowledge base SOP AMIGA Robot Admin

Nama bucket dan ID resource pada contoh adalah placeholder publik. Sesuaikan dengan resource milik environment Anda sebelum menjalankan perintah AWS.
Demo penilaian lokal dengan replay tidak memerlukan perintah AWS di dokumen ini.

Korpus SOP untuk RAG di Amazon Bedrock, kelompok 9 MAIN Hackathon 2026.

## Status per 15 Oktober 2026, malam (Manajer Keuangan dan tanda tangan basah)

- **Penyetuju akhir kini Manajer Keuangan AMIGA, bukan Direksi.** 32 kartu disesuaikan: label "Menunggu manajer
  keuangan", menu Persetujuan, Finance tidak mengunggah, dan voucher v7 dengan tiga kotak tanda tangan basah (PIC,
  Finance, manajer keuangan). Kode internal tetap `AMIGA_DIRECTOR`, dan `sop_id` `PERAN-DIREKSI-AMIGA` dipertahankan
  supaya tidak ada file `dist/` yang perlu dihapus. Isinya kini peran Manajer Keuangan.
- **Kata "tanda tangan" di aplikasi jadi "persetujuan".** Kutipan seperti "Setujui", "Voucher & persetujuan", dan pesan
  password ikut diganti. Kode penolakan seperti `SIGNATURE_PASSWORD_INVALID` tidak berubah.
- **Empat galat bawaan sesudah commit Codex 15 Oktober beres.** Kutipan "Lebar penuh" dan "Satu halaman" dihapus dari
  `LAYAR-REVIEW`, dan `TAX_ADJUSTMENT_CONFIRMATION_REQUIRED` serta `TAX_ADJUSTMENT_INVALID` terdaftar sebagai penolakan.
  `bangun_korpus.py --cek` lolos.

## Status per 15 Oktober 2026, malam

- **69 kartu, sinkron dengan pengajuan PIC dan portofolio klien.** 47 kartu disesuaikan: PIC mengoreksi lalu mengajukan
  ke Finance, PIC mendaftarkan vendor baru, dua tim masing-masing 10 klien, PIC membuat klien baru, label
  "Belum diajukan", dan teks layar baru dari commit Codex 15 Oktober. Kartu `EXC-VENDOR_NEW` ditambahkan.
- **`bangun_korpus.py --cek` versi ketat lolos lagi.** 35 kutipan layar yang rusak sejak commit Codex 15 Oktober sudah
  diganti teks layar terkini. `NOT_SUBMITTED`, `INTAKE_LOCKED`, `VENDOR_EXISTS`, `CLIENT_EXISTS`, dan `VENDOR_NEW`
  terdaftar di `kosakata.json` dan disebut kartu.

## Status per 14 Oktober 2026, malam (tahap 8)

- **68 kartu, sinkron dengan alur tanda tangan.** Dua kartu baru: `PERAN-DIREKSI-AMIGA` dan `TOLAK-TANDA-TANGAN`.
  38 kartu lama disesuaikan dengan layar split-screen, dialog tanda tangan, tiga status baru, dan voucher v4.
  Delapan kode penolakan baru, `AMIGA_APPROVED`, dan `AMIGA_DIRECTOR` terdaftar di `kosakata.json`.
  `bangun_korpus.py --cek` lolos.
- **Penanda tangan kedua adalah Direksi AMIGA (BOD internal), bukan direksi klien.** Satu akun BOD memegang semua klien.
  Persetujuan bayar dan pembayaran tetap di klien, di luar aplikasi. Kartu `PERAN-DIREKSI-KLIEN` diganti nama jadi
  `PERAN-DIREKSI-AMIGA`, dan nilai peran di front matter jadi `amiga-director`. Kartu juga menjelaskan spesimen tanda
  tangan, alasan penolakan di bar aksi, dan muat ulang sesudah konflik.
- **Lima perbaikan dari audit kegunaan sudah diterapkan dan disetujui Aldian 14 Oktober.** Letaknya di kartu
  `TAX_FAKTUR_NOT_FOUND`, `MISSING_EVIDENCE`, `UNSUPPORTED_CURRENCY`, dan `LINE_TOTAL_MISMATCH`. Audit ulang malam yang
  sama: 14 dari 23 kartu kendala lolos dengan pembacaan kriteria yang lebih ketat, dan keempat kartu itu ikut lolos.
  Rinciannya di `output/app-stage8/AUDIT_ULANG_ROBOT_ADMIN.md`.
- **Eval RAG diulang 14 Oktober malam, biaya US$0,0060.** Retrieval tidak turun: set panel 11/12, set lama 10/10, sitasi
  sah 24/24. Review ketat jawaban panel 5 dari 12. Jawaban tahap 7 dengan aturan yang sama 6 dari 12.
- **App membaca kartu dari folder `sop/`.** Izin S3 student_9 dicabut 14 Oktober, jadi langkah unggah ke bucket di
  bawah tidak lagi dipakai app.

## Status per 14 Oktober 2026, malam (tahap 7)

- **Set uji sempat tercemar, sekarang dijaga.** Commit `957b817` menyalin kalimat soal 3 ke baris "Istilah lain" kartu `HUMAN_CORRECTION_PENDING`. Penjaga lama tidak menangkapnya karena membaca file yang tidak ada dan hanya memeriksa rangkaian 6 kata. Penjaga sekarang membaca semua `eval/*.json` dan memeriksa baris "Istilah lain" per 4 kata. Kartu dipulihkan ke versi sebelum commit itu.
- **Tanpa kebocoran, soal 3 kembali salah arah.** Kartu `HUMAN_CORRECTION_PENDING` tidak terambil, dan jawabannya menyuruh menunggu persetujuan koreksi yang tidak ada di app. Cacat 13 Oktober ini belum sembuh. Gerbang otomatis tetap lolos karena hanya memeriksa format dan sitasi.
- **Uji jalur panel.** `eval/rag-uji-panel.json` berisi 12 soal ber-`kode`, dijalankan dengan `jalankan_uji.py --set rag-uji-panel.json`. Retrieval 11/12, sitasi sah 12/12, tetapi review manual ketat hanya 8 dari 12. Rincian dan rekomendasinya ada di `output/app-stage7/AUDIT_KEGUNAAN.md`.

## Status per 14 Oktober 2026, sore (tahap 6)

- **66 kartu.** Tiga kartu baru untuk identitas pajak yang dibaca otomatis: `TAX_FAKTUR_NOT_FOUND`, `NPWP_MISMATCH`, dan `NPWP_CHECK`. Kartu unggah, review, dan pajak disesuaikan dengan foto JPG/PNG dan nomor faktur yang tidak lagi diketik. `bangun_korpus.py --cek` lolos.
- **Jawaban lebih manusiawi.** Prompt `kb.SISTEM` menyapa "Anda", maksimal lima langkah, tanpa kode di kalimat, dan tidak lagi menulis "Kamu hanya memberi panduan". `GET /api/v1/sop/label` memberi judul ramah per kode untuk layar.
- **Uji tersimpan.** `eval/rag-uji.json` (12 pertanyaan) dan `eval/jalankan_uji.py`. Hasil akhir: retrieval 10/10, sitasi sah 12/12, gerbang lolos. Rincian di `output/app-stage6/VERIFICATION.md`.

## Status per 14 Oktober 2026

- **63 kartu, sinkron dengan tahap pajak.** Empat kartu `TAX_*` dan kartu `ALUR-POTONGAN-PAJAK` ditambahkan. Dua kartu lama disesuaikan dengan mesin pajak. `bangun_korpus.py --cek` lolos.
- **App sudah memanggil RAG.** `app/sop_api.py` menyediakan `GET /api/v1/sop/kartu` dan `POST /api/v1/sop/tanya`. Panel Panduan SOP ada di layar review. Bukti ada di `output/app-stage5/VERIFICATION.md`.
- **Izin S3 `student_9` dicabut 14 Oktober.** `GetObject` dan `ListBucket` ditolak. Embedding Titan V1 dan Nova Lite tetap jalan. App dan `rag.py --lokal` membaca kartu dari folder `sop/`, jadi salinan di bucket sudah basi.

## Status per 13 Oktober 2026

- **Korpus sinkron dengan app tahap 1 sampai 4.** 58 kartu mengikuti kode sore 13 Oktober: unggah batch, review dan koreksi, persetujuan Finance, serta voucher demo. Build ketat lolos dengan korpus `b7f08061eacd37cc`.
- **Diperiksa independen dua putaran.** Putaran pertama oleh empat pemeriksa menemukan satu klaim salah dan puluhan nuansa yang menyesatkan atau kurang lengkap. Putaran kedua memeriksa ulang bagian yang diperbaiki dan menemukan lima hal lagi. Semuanya sudah diperbaiki.
- **RAG manual sudah jalan tanpa Knowledge Base.** `tools/rag.py` membaca 58 kartu dari akar bucket, memotongnya jadi 120 chunk, lalu mencari dengan embedding Titan V1 dan skor kata. Nova Lite menjawab dengan referensi kartu dan lokasi S3-nya. Rinciannya ada di bagian [RAG manual](#rag-manual-tanpa-knowledge-base).
- **Mutu jawaban RAG belum lolos pemeriksaan manual ketat.** Uji 8 pertanyaan lolos 8 secara otomatis, tapi hanya 4 yang lolos pemeriksaan manual ketat.
- **Kartu ada di dua tempat di S3.** Akar `s3://example-amiga-sop-bucket/` berisi salinan persis 58 kartu `sop/`, diunggah Aldian 13 Oktober malam. Prefix `amiga-sop/` berisi 116 berkas build `b7f08061eacd37cc` untuk jalur KB.
- **Jalur Knowledge Base diparkir.** KB `KBEXAMPLE1` memakai Cohere, dan izinnya belum dibuka. Mode cadangan `kb.py` tetap bisa dipakai tanpa embedding. Rinciannya ada di bagian [Status AWS](#status-aws-dan-cara-melanjutkan).
- **Perlu konfirmasi tim.** Kartu memakai Tech Lead sebagai tujuan eskalasi masalah teknis. Dokumen tim baru menyebut Tech Lead sebagai pemilik keputusan anggaran dan provider, dan acceptance checklist mencatat penanggung jawab teknis belum ditetapkan.

### Kalau app berubah lagi

Gerbang drift menahan build begitu app mengeluarkan kode baru atau mengubah teks layar yang dikutip kartu. Urutan sinkronnya:

1. Klasifikasikan kode baru di `kosakata.json`. Kode kelas exception wajib punya kartu EXC sendiri.
2. Perbarui kartu yang menyebut perilaku yang berubah, termasuk baris `sumber`.
3. Jalankan build ketat sampai LOLOS.
4. Periksa ulang kartu yang berubah secara independen terhadap kode.

## Isi folder

| Path | Isi |
|---|---|
| `sop/` | Kartu SOP, satu file satu topik, dengan front matter |
| `kosakata.json` | Klasifikasi setiap kode yang boleh muncul di kartu |
| `tools/bangun_korpus.py` | Lint dan build. Menulis `dist/` hanya kalau tidak ada cacat |
| `tools/rag.py` | RAG manual tanpa KB: `cari` dan `jawab` |
| `tools/kb.py` | Operasi AWS lewat boto3 untuk jalur KB dan mode cadangan: `periksa`, `siapkan`, `unggah`, `sinkron`, `status`, `tanya`, `jawab`, `uji` |
| `kb-config.json` | ID turunan resource AWS, tanpa ARN dan tanpa kredensial. ID KB diambil dari `.env` |
| `requirements.txt` | boto3 1.43.112 |
| `dist/`, `.state/` | Hasil build, cache embedding `rag.py` di `.state/rag/`, dan catatan kerja. Diabaikan git |

## Bentuk kartu

Satu kartu menjawab satu topik dan harus bisa dipahami tanpa kartu lain. RAG hanya melihat potongan yang terambil, jadi rujukan seperti "lihat di atas" dilarang.

| Kategori | Awalan | Jumlah | Pemakai utama |
|---|---|---|---|
| Fondasi | `FON` | 4 | Pertanyaan umum dan istilah |
| Alur | `ALUR` | 10 | Langkah kerja per tahap |
| Peran | `PERAN` | 7 | Boleh dan tidak boleh per peran |
| Layar | `LAYAR` | 3 | Arti tampilan antrean, review, dan batch |
| Exception | `EXC` | 31 | Asisten exception, satu kartu per kode |
| Penolakan | `TOLAK` | 7 | Arti pesan penolakan dan tindakannya |
| Kontrol | `KTL` | 6 | Aturan kontrol dan keputusan terbuka |

Front matter wajib berisi `sop_id`, `kategori`, `status_aturan`, dan `sumber`. Kartu EXC juga wajib punya `kode`.

`status_aturan` memakai salah satu dari empat nilai:

- `brief-v2.0` berarti berasal dari brief AMIGA.
- `demo-rules.v1` berarti aturan validasi PoC yang belum disetujui Finance.
- `poc-teknis` berarti batasan teknis PoC, bukan aturan bisnis.
- `belum-diputuskan` berarti keputusan masih terbuka.

Build mengubah front matter menjadi sidecar `.md.metadata.json`. Yang masuk metadata hanya `sop_id`, `kategori`, `kode`, `status_aturan`, dan `versi_kartu`, semuanya STRING. Baris `sumber` tidak ikut di-ingest.

## Membangun korpus

Jalankan dari folder `hackthon`:

```powershell
.\.venv\Scripts\python.exe knowledge-base\tools\bangun_korpus.py --cek
.\.venv\Scripts\python.exe knowledge-base\tools\bangun_korpus.py
```

`--cek` hanya lint. Tanpa opsi, build menulis `dist/`. `--parsial` menurunkan cakupan dan panjang menjadi peringatan, khusus saat menulis kartu bertahap.

Exit code adalah vonisnya. Satu cacat berarti `dist/` tidak ditulis sama sekali. Yang diperiksa:

- Front matter sesuai skema, `sop_id` unik, dan nama file sesuai `sop_id`.
- Label wajib per kategori ada.
- Setiap token kode di badan kartu terdaftar di `kosakata.json`, jadi salah ketik ditolak.
- Kode baru yang muncul di `app/` atau `prototype/amiga_ocr/` tapi belum terdaftar membuat build gagal. Ekstraksinya memakai `ast`, termasuk dua cabang ekspresi kondisional.
- Setiap teks bertanda kutip harus ada verbatim di kode app. Nama tombol karangan ditolak.
- Tanpa em-dash, tanpa titik koma di heading, dan tanpa rujukan yang tidak berdiri sendiri.
- Panjang badan kartu maksimal 1.800 karakter, karena model embedding Cohere menerima maksimal 512 token.
- Tidak boleh ada rangkaian 6 kata dari set uji di `eval/*.json` yang bocor ke kartu. Baris "Istilah lain" diperiksa lebih ketat, per 4 kata, karena sinonim di sana gampang tersalin dari soal. Set uji kosong membuat build gagal.

Build menolak jalan kalau `dist/` berisi file yang tidak dihasilkannya. Hapus file itu dulu secara sadar.

## Menambah atau mengubah kartu

1. Tulis atau ubah kartu di `sop/` dengan label wajib kategorinya.
2. Pastikan setiap langkah bisa ditelusuri ke sumber, lalu catat sumbernya di front matter.
3. Kalau app menambah kode baru, daftarkan kodenya di `kosakata.json` dan buat atau perbarui kartunya.
4. Jalankan build sampai vonisnya LOLOS.
5. Untuk RAG manual, unggah kartu yang berubah dari `sop/` ke akar bucket. `rag.py` membaca ulang S3 setiap pertanyaan, dan hanya chunk yang berubah yang di-embed ulang.
6. Untuk jalur KB, jalankan `kb.py unggah`, atau `kb.py sinkron` kalau KB sudah aktif. Mode cadangan menolak jalan kalau kartu di prefix `amiga-sop/` beda dengan build.

Contoh unggah ke akar bucket dengan AWS CLI:

```powershell
aws s3 cp knowledge-base\sop\ s3://example-amiga-sop-bucket/ --recursive --exclude "*" --include "*.md" --region ap-southeast-1
```

Kode yang hanya keluar dari kontrak prototipe, seperti `ROLE_NOT_ALLOWED`, diberi kelas `prototipe` di `kosakata.json`. Kode kelas ini tidak wajib disebut di kartu, karena tidak pernah tampil di aplikasi.

## Konfigurasi `.env`

`kb.py` dan `rag.py` membaca `.env` di folder `hackthon`. File yang sama dipakai app, jadi keduanya hanya menyalin key miliknya.

| Key | Dipakai untuk |
|---|---|
| `AWS_ACCESS_KEY` atau `AWS_ACCESS_KEY_ID`, plus `AWS_SECRET_ACCESS_KEY` | Kredensial boto3. Wajib berpasangan. Kalau keduanya kosong, dipakai rantai default boto3 |
| `AWS_REGION` | Opsional. Kalau diisi, harus `ap-southeast-1`. Embedding Titan di `rag.py` tetap dipanggil di us-east-1 |
| `AWS_BUCKET` | Bucket kartu. `kb.py` memakai prefix `amiga-sop/`, sedangkan `rag.py` membaca kartu ber-front matter di akar bucket |
| `BEDROCK_KB_ID` | KB untuk Retrieve dan ingestion `kb.py`. Kalau kosong, diambil dari `kb-config.json` |
| `BEDROCK_KB_ROLE_ARN` | Role saat `siapkan` membuat KB baru |
| `BEDROCK_EMBED_MODEL_ID` | Model embedding `rag.py`, sekarang `amazon.titan-embed-text-v1`. KB `KBEXAMPLE1` memakai Cohere, jadi mode KB `kb.py` melaporkan model beda selama jalur KB diparkir |
| `BEDROCK_MODEL_ID` | Model penjawab lewat Converse, dipakai `kb.py` dan `rag.py` |

- Key yang kosong jatuh ke nilai bawaan. `kb.py periksa` mencetak sumber setiap nilai.
- Nilai rahasia tidak pernah dicetak, termasuk lewat pesan galat. Galat baca `.env` hanya menampilkan pesan tetap.
- Opsi `--env <path>` di `kb.py` dan `rag.py` menunjuk file lain, misalnya untuk uji.

## RAG manual tanpa Knowledge Base

Ini jalur utama sejak 13 Oktober 2026 malam. Jalur ini tidak butuh izin role KB, cukup kredensial di `.env`.

Alurnya per pertanyaan:

1. Ambil semua `.md` di akar bucket yang front matter-nya punya `sop_id`. Berkas lain, seperti `SOP_DevOps_Command_Center_DCC.md`, dilewati dan dilaporkan.
2. Potong tiap kartu per bagian berlabel tebal, lalu gabungkan sampai 900 karakter. Hasilnya 120 chunk, dan tiap chunk diawali `sop_id` serta judul kartu.
3. Buat embedding tiap chunk dengan `BEDROCK_EMBED_MODEL_ID` di us-east-1. Vektornya disimpan di `.state/rag/`, jadi chunk hanya di-embed ulang kalau isinya berubah.
4. Hitung cosine similarity pertanyaan dengan semua chunk. Peringkatnya digabung dengan skor kata (TF-IDF potongan huruf) lewat reciprocal rank fusion, lalu ambil 5 chunk teratas.
5. Kirim kartu utuh dari chunk teratas sebagai konteks ke `BEDROCK_MODEL_ID`, dengan aturan prompt yang sama dengan `kb.py`.
6. Cetak jawaban dengan referensi: `sop_id`, judul kartu, bagian yang cocok, skor, dan lokasi `s3://`. Sitasi di luar konteks diberi peringatan.

```powershell
.\.venv\Scripts\python.exe knowledge-base\tools\rag.py cari "Siapa yang boleh menyetujui invoice?"
.\.venv\Scripts\python.exe knowledge-base\tools\rag.py jawab "Berapa maksimal file dalam satu batch unggah?"
```

`cari` hanya retrieval, tanpa model jawaban. `jawab` keluar dengan exit 1 kalau ada peringatan, misalnya jawaban tanpa sitasi.

Contoh jawaban dari uji 13 Oktober malam:

```text
1. Satu batch berisi 1 sampai 5 file. [TOLAK-BATCH]
2. Browser menolak lebih dulu jika memilih lebih dari lima file. [TOLAK-BATCH]
3. Pesan yang muncul adalah "Maksimal lima file per batch. Pilih ulang file." [TOLAK-BATCH]
4. Jika "Unggah & proses" ditekan, pesan berganti menjadi "Pilih satu hingga lima file." [TOLAK-BATCH]

Referensi:
1. [TOLAK-BATCH] Unggahan batch ditolak: arti pesan dan tindakannya
   bagian Ringkasnya, Pertanyaan umum, cosine 0.7591, kata 0.2521, s3://example-amiga-sop-bucket/tolak-batch.md
```

**Kenapa Titan V1 dan skor kata.** Hasil uji 13 pertanyaan, 13 Oktober malam:

| Konfigurasi | Set utama | Parafrase | Tambahan |
|---|---|---|---|
| Titan V2, chunk 900 | 5/6 | 3/4 | 2/3 |
| Titan V2, chunk 450 | 5/6 | 3/4 | 2/3 |
| Skor kata saja | 5/6 | 4/4 | 3/3 |
| Titan V1, chunk 900 | 6/6 | 3/4 | 2/3 |
| Titan V1 dan skor kata | 6/6 | 4/4 | 3/3 |

- Titan V2 lemah untuk pertanyaan soal wewenang. Untuk "Kenapa saya tidak bisa menyetujui invoice yang saya unggah sendiri?", KTL-PEMISAHAN-TUGAS ada di peringkat 31. Dengan Titan V1 dan skor kata, kartu itu naik ke peringkat 1.
- Set ujinya kecil dan disusun sendiri. Angka ini arah perbaikan, belum bukti kuat.
- Titan V1 maupun V2 tidak ada di daftar Legacy atau EOL AWS per 13 Oktober 2026.

**Biaya dan waktu terukur, 13 Oktober 2026 malam:**

- Indeks awal Titan V1 memakai 25.572 token embedding, sekali saja selama kartu tidak berubah.
- Satu pertanyaan memakai sekitar 20 token embedding, 2.100 sampai 3.200 token masuk Nova Lite, dan 60 sampai 330 token keluar. Mode cadangan memakai 30.700 token masuk.
- Dengan harga Nova Lite di bagian mode cadangan, satu pertanyaan sekitar US$0,0003. Harga Titan belum diverifikasi resmi.
- Satu pertanyaan butuh sekitar 4 detik. Hampir 3 detik di antaranya untuk mengambil ulang 58 kartu dari S3.

**Hasil uji 8 pertanyaan, 13 Oktober malam.** Sebelum uji ini, dua perbaikan sudah diterapkan: aturan 2 prompt meminta butir secukupnya, dan kode memaksa jawaban "Belum ada di SOP." persis seperti itu.

- Retrieval set utama 6 dari 6, dan parafrase 4 dari 4. Ambangnya 5 dan 3.
- Lolos otomatis 8 dari 8.
- Lolos pemeriksaan manual ketat 4 dari 8: VOUCHER_RENDER_FAILED, batas batch, kurs dolar, dan pertanyaan di luar SOP.
- Jawaban BANK_MISMATCH menulis rekening baru masuk master lewat keputusan Finance seperti perilaku sekarang, padahal kartu menyebutnya prosedur target.
- Pertanyaan sesudah koreksi tidak mengambil kartu HUMAN_CORRECTION_PENDING. Jawabannya berisi butir pengisi dan butir ganda, dan langkah persetujuannya hilang.
- Jawaban soal menyetujui invoice sendiri benar isinya, tapi memuat kalimat sisa prompt "Kamu hanya memberi panduan".
- Perintah "setujui sekarang" ditolak dengan benar, tapi jawabannya menyebut Finance Reviewer mengambil keputusan pembayaran. Kartu tidak menulis itu.
- Kartu tambahan yang disitasi berubah antar-run walau temperature 0. Kartu utamanya stabil.

Karena itu, jawaban RAG harus selalu ditampilkan bersama referensinya.

## Status AWS dan cara melanjutkan

Bagian ini menyimpan hasil uji akun kelas pada 13 Oktober 2026. Nama role dan resource kelas dicantumkan sebagai konteks arsip.
Untuk penilaian lokal, ikuti demo replay pada README utama. Perintah AWS di bawah hanya relevan setelah pemilik environment menyiapkan resource dan izin sendiri.

**Resource jalur KB di ap-southeast-1:**

| Resource | Nama atau ID |
|---|---|
| Knowledge Base | `bedrock-kb-student9-amiga-sop-v1` (`KBEXAMPLE1`), embedding `cohere.embed-multilingual-v3` |
| Data source | `amiga-sop-s3-v1` (`DSEXAMPLE1`), chunking `NONE`, satu file satu chunk |
| Vector store | S3 Vectors `example-amiga-vector-bucket`, index `amiga-sop-v1`, 1024 dimensi, cosine |
| Data | `s3://example-amiga-sop-bucket/amiga-sop/`, 116 berkas build `b7f08061eacd37cc` |

**Fakta izin, terverifikasi 13 Oktober 2026 malam:**

- `student_9` bisa memanggil Titan Text Embeddings V1 dan V2 di us-east-1 lewat InvokeModel. Catatan sore yang menyebut `student_9` dikunci ke ap-southeast-1 ternyata keliru.
- Titan tidak tersedia di ap-southeast-1. Model embedding di sana hanya `cohere.embed-english-v3`, `cohere.embed-multilingual-v3`, dan `cohere.embed-v4:0`.
- `student_9` ditolak memanggil `cohere.embed-multilingual-v3`, karena tidak ada policy identitas yang mengizinkannya. Request ID `93167098-a52f-4ea1-91a9-17b5fb319a6b`.
- Role `BedrockClassKBRole` juga belum diizinkan memanggil Cohere. Ingestion gagal dengan request ID `2ea69cf8-417e-48fb-881b-2ffd56cf21fd`, dan Retrieve gagal dengan `ValidationException` generik.
- Converse ke `apac.amazon.nova-lite-v1:0` di ap-southeast-1 berjalan.
- Policy IAM `student_9` tidak bisa dibaca dari akun ini.

**Kalau jalur KB mau dibuka lagi:**

- Minta mentor menambah izin `bedrock:InvokeModel` untuk `BedrockClassKBRole` pada `arn:aws:bedrock:ap-southeast-1::foundation-model/cohere.embed-multilingual-v3`.
- `BEDROCK_EMBED_MODEL_ID` dipakai bersama `rag.py`. Jalur KB dengan Cohere dan `rag.py` dengan Titan tidak bisa jalan bersamaan sebelum key itu dipisah.
- Sesudah izin dibuka, jalankan `kb.py sinkron`, lalu `kb.py periksa` sampai MODE KB SIAP. Sesudah itu baru set uji retrieval ditulis dan `kb.py uji` dijalankan.
- Kalau harus pindah model atau akun, model embedding KB tidak bisa diganti. KB lama dihapus dulu dengan persetujuan Aldian, lalu jalankan `kb.py siapkan --model <id> --nama-kb <nama> --indeks <index>`.
- Sebelum ingestion pertama, uji batas panjang kartu terhadap model yang dipakai. Anggaran 1.800 karakter belum pernah dikalibrasi ke model nyata.

```powershell
.\.venv\Scripts\python.exe knowledge-base\tools\kb.py periksa
.\.venv\Scripts\python.exe knowledge-base\tools\kb.py unggah
.\.venv\Scripts\python.exe knowledge-base\tools\kb.py sinkron
.\.venv\Scripts\python.exe knowledge-base\tools\kb.py tanya "rekening beda dengan master" --kode BANK_MISMATCH
.\.venv\Scripts\python.exe knowledge-base\tools\kb.py jawab "Kenapa rekening ditandai beda?"
.\.venv\Scripts\python.exe knowledge-base\tools\kb.py uji
```

`unggah` dan `sinkron` tidak pernah menghapus objek di S3. Objek yang tidak lagi ada di `dist/` hanya dilaporkan sebagai basi. `periksa` tidak pernah memulai ingestion.

## Mode cadangan tanpa embedding

Mode ini menjawab tanpa embedding sama sekali. Semua perintahnya memakai `--mode cadangan`.

- `tanya --mode cadangan --kode BANK_MISMATCH` mengambil kartu persis dari S3 tanpa model. Isinya dicocokkan dengan `versi_kartu` di build lokal. Ini jalur yang paling aman untuk asisten exception.
- `jawab --mode cadangan --kode BANK_MISMATCH` meminta model menjawab dari satu kartu itu saja.
- `jawab --mode cadangan "<pertanyaan>"` mengirim seluruh 58 kartu dari S3 ke model. Sebelumnya, hash isi S3 harus sama dengan build. Kalau beda, perintah berhenti dan menyuruh `unggah`.
- Kode yang tidak punya kartu langsung dijawab "SOP untuk kode ini belum tersedia." tanpa memanggil model.
- Setiap output diberi label "MODE CADANGAN: tanpa embedding". Mode ini bukan pencarian vektor.

**Biaya terukur, 13 Oktober 2026.** Satu pertanyaan bebas memakai sekitar 30.700 token masuk. Satu pertanyaan per kode sekitar 1.000 token. Harga Nova Lite profil APAC sekitar US$0,072 per 1 juta token masuk, dari situs pihak ketiga, dan harga resmi Singapura belum diverifikasi. Jadi satu pertanyaan bebas sekitar US$0,0023.

**Hasil uji 8 pertanyaan, putaran akhir sesudah satu perbaikan prompt.** Uji ini memakai prompt sebelum aturan 2 diubah, 13 Oktober malam.

- Lolos otomatis 7 dari 8. Kode tak dikenal tidak memicu panggilan model.
- Lolos pemeriksaan manual ketat 3 dari 8: arti dan langkah BANK_MISMATCH, VOUCHER_RENDER_FAILED, dan pertanyaan kurs dolar.
- Dua jawaban memuat kalimat sisa aturan prompt, "Kamu hanya memberi panduan", yang salah alamat.
- Satu jawaban menyitasi kartu yang tidak memuat faktanya. Batas 5 file per batch disitasi ke LAYAR-BATCH, padahal faktanya ada di TOLAK-BATCH.
- Pertanyaan di luar SOP dijawab benar, tapi tidak memakai kalimat baku "Belum ada di SOP.".
- Penolakan perintah menyetujui invoice benar, tapi ditutup saran umum yang tidak ada di kartu.
- Kartu utama yang disitasi stabil antar-run. Kartu tambahan berubah-ubah walau temperature 0.

Karena itu, jawaban mode cadangan harus selalu ditampilkan bersama sumbernya. Untuk asisten exception, tampilkan kartunya langsung.

## Kontrak pemakaian untuk app

Arahan mentor: app memanggil Bedrock dari FastAPI lewat boto3. Sudah diimplementasikan 14 Oktober di `app/sop_api.py`, dengan kartu dibaca dari folder `sop/`.

**Tanya bebas lewat `rag.py`, jalur utama.** Konfigurasi dan kredensial dibaca dari `.env`.

```python
import sys
sys.path.append("knowledge-base/tools")
import kb
import rag

kb.muat_env()
hasil = rag.jawab("Siapa yang boleh menyetujui invoice?")
print(hasil["jawaban"])
for r in hasil["referensi"]:
    print(r["sop_id"], r["judul"], r["s3"])
```

- `rag.jawab` mengembalikan dict berisi `jawaban`, `referensi`, `konteks`, `hasil` retrieval, token, latensi, dan `peringatan`. Tiap referensi memuat `sop_id`, `judul`, `bagian`, `skor`, `skor_kata`, dan `s3`.
- `rag.cari` hanya retrieval, tanpa model jawaban.
- Tampilkan referensi bersama jawaban. Kalau `peringatan` tidak kosong, tandai jawabannya untuk diperiksa manusia.

**Asisten exception lewat KB, diparkir.** Kalau KB dibuka lagi, ambil satu kartu untuk kode check yang gagal:

```python
import boto3

runtime = boto3.client("bedrock-agent-runtime", region_name="ap-southeast-1")
respons = runtime.retrieve(
    knowledgeBaseId="KBEXAMPLE1",
    retrievalQuery={"text": "Langkah penanganan untuk BANK_MISMATCH"},
    retrievalConfiguration={"vectorSearchConfiguration": {
        "numberOfResults": 1,
        "filter": {"equals": {"key": "kode", "value": "BANK_MISMATCH"}},
    }},
)
kartu = respons["retrievalResults"]
```

Tampilkan isi kartu beserta `sop_id`. Kalau hasilnya kosong, tampilkan "SOP untuk kode ini belum tersedia" tanpa fallback ke model. Selama KB diparkir, pakai `kb.kartu_s3` di bawah.

**Lewat `kb.py`.** App bisa memanggil fungsi yang sama dengan CLI. Konfigurasi dan kredensial dibaca dari `.env`.

```python
import sys
sys.path.append("knowledge-base/tools")
import kb

kb.muat_env()
kartu = kb.kartu_s3("EXC-BANK_MISMATCH")
hasil = kb.jawab_pertanyaan("Kenapa rekening ditandai beda?", kode=None, mode="cadangan")
```

- `kartu_s3` mengembalikan satu kartu persis dari S3, atau `None` kalau kartunya tidak ada.
- `jawab_pertanyaan` mengembalikan dict berisi `jawaban`, `sumber`, `kartu`, `skor`, token, latensi, dan `peringatan`. Pakai `mode="kb"` sesudah mode KB siap.
- Galat konfigurasi muncul sebagai `kb.GalatKB`, dan galat AWS sebagai `ClientError`.

**Batas keras.** Hasil RAG hanya panduan. Dia tidak pernah mengubah status, menyetujui, atau mengisi field invoice.

Untuk kode kegagalan proses seperti `BUDGET_BLOCKED` dan `DOCUMENT_CHANGED`, layar tidak menampilkan kodenya. App harus mengambil kode dari `error_code` request, bukan dari teks layar. Kegagalan voucher seperti `VOUCHER_RENDER_FAILED` juga tidak tampil di layar. Kodenya ada di `error_code` pada objek `voucher` di respons detail request.

## Teardown

Jangan jalankan tanpa persetujuan Aldian. Urutannya data source, KB, index, vector bucket, lalu objek S3.

```powershell
aws bedrock-agent delete-data-source --region ap-southeast-1 --knowledge-base-id KBEXAMPLE1 --data-source-id DSEXAMPLE1
aws bedrock-agent delete-knowledge-base --region ap-southeast-1 --knowledge-base-id KBEXAMPLE1
aws s3vectors delete-index --region ap-southeast-1 --vector-bucket-name example-amiga-vector-bucket --index-name amiga-sop-v1
aws s3vectors delete-vector-bucket --region ap-southeast-1 --vector-bucket-name example-amiga-vector-bucket
aws s3 rm s3://example-amiga-sop-bucket/amiga-sop/ --recursive --region ap-southeast-1
```

## Rujukan dokumentasi AWS

Diakses 2026-10-13.

- Format data source S3 dan sidecar metadata: <https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html>
- Strategi chunking, termasuk `NONE`: <https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html>
- S3 Vectors sebagai vector store KB: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html>
- Batas metadata S3 Vectors: <https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html>
- Model embedding yang didukung KB per region: <https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html>
- Cohere Embed Multilingual v3, batas 512 token: <https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-embed-multilingual.html>
- Operator filter Retrieve: <https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html>
- Request dan response Titan Text Embeddings V1 dan V2: <https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html>
- Daftar model Legacy dan EOL: <https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle-legacy.html>
