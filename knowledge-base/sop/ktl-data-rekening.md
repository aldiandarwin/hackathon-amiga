---
sop_id: KTL-DATA-REKENING
kategori: kontrol
tahap: intake, review, audit
peran: pic-klien, finance-reviewer, system-admin
status_aturan: brief-v2.0
sumber: brief hal. 2 dan 3; BRD 6.1 dan 6.3; arsitektur §5, §7, §8, §9, dan §12; app/static/index.html dialog unggah; database-design-draft akses dan audit; app/service.py process_next trace; app/review.py download dan verification; app/verify_page.py; app/voucher_pdf.py informasi rekening; app/database.py seed vendor dan spesimen; app/specimen.py; app/schema.sql signature_specimens; acceptance template pencatatan hasil
---

# Data rekening dan dokumen invoice adalah data sensitif

**Aturan.**
- Nomor rekening dan isi invoice hanya diakses oleh akun yang ditugaskan ke klien itu.
- Status dan dokumen invoice dikelola di aplikasi. AMIGA Robot Admin hadir untuk menggantikan pemantauan lewat WhatsApp dan email.
- Bukti pengujian dan screenshot tidak memuat rekening nyata.
- Spesimen tanda tangan akun demo dibuat sintetis dan hanya tercetak di voucher lama. Voucher baru memakai tanda tangan basah.

**Alasan.** Salah ketik atau kebocoran rekening bisa membuat pembayaran salah tujuan. Hasil baca AI juga tidak membuktikan rekening itu sah.

**Cara sistem menegakkan.** File baru dikirim ke Amazon Bedrock untuk ekstraksi, termasuk nomor rekening di dalamnya, dan ke OpenAI hanya kalau Bedrock gagal. PDF disimpan privat dan hanya dibuka sesudah izin dicek. Kode app tidak menulis isi dokumen ke log server biasa, tapi respons AI lengkap, termasuk rekening, tersimpan di file trace privat. Voucher PDF juga memuat rekening, jadi disimpan privat dan hanya bisa diunduh akun yang ditugaskan ke klien itu. Halaman verifikasi publik dari kode QR sengaja tidak menampilkan rekening maupun gambar tanda tangan. Rekening dicocokkan ke master vendor dengan hasil BANK_VERIFIED, BANK_MISMATCH, atau BANK_UNVERIFIED. Di PoC, BANK_VERIFIED hanya berarti cocok dengan master demo.

**Pertanyaan umum.** Siapa yang boleh mengubah rekening di master vendor? Usulan tim: Finance, berdasarkan bukti yang tercatat. Sumber verifikasi rekening belum diputuskan, pemilik: Finance. Boleh pakai invoice klien asli untuk demo? Hanya dengan izin penggunaan data dari AMIGA.
