---
sop_id: LAYAR-BATCH
kategori: layar
tahap: intake, antrean
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: web/app/unggah/page.tsx form unggah, dialog klien baru, dan progres unggahan; web/lib/upload.ts PROBLEM_NOTES, STEP_LABELS, dan progressOf; web/components/shell.tsx navFor; app/batches.py detail; app/clients.py; app/README.md multiple upload
---

# Halaman unggah invoice dan progres unggahan

**Bagian layar**
- Menu "Unggah invoice" di sidebar, khusus PIC, membuka halaman ini.
- Bagian Detail invoice: kolom Klien berupa dropdown, atau langsung terisi kalau PIC hanya punya satu klien. Tombol "+ Klien baru" ada tepat di bawahnya. Lalu ada "Jenis pajak" dan centang "Penerima punya NPWP/NIK".
- "+ Klien baru" membuka dialog "Daftarkan klien baru": "Nama klien", "Kota", "Bidang usaha", "NPWP klien (opsional)", dan "Kode voucher (opsional)". Klien yang baru disimpan langsung terpilih.
- Bagian File invoice: area tarik file untuk 1 sampai 5 file PDF, JPG, atau PNG, maksimal 5 MB per file, plus daftar file terpilih dan ukurannya.
- Tombol "Unggah invoice" mengirim semua file. Lalu bagian Progres unggahan memuat satu baris per file.

**Arti tampilan**
- Catatan di samping ukuran file, misalnya lebih dari 5 MB, berarti file itu akan ditolak.
- "Pilih klien dulu." berarti kolom Klien masih kosong. Belum ada file yang dikirim.
- Tiap baris file punya langkah Terkirim, Dibaca AI, Diperiksa aturan, dan Siap direview. Tombol Buka di layar review membuka invoicenya.
- "Ditolak" selalu disertai alasannya. File itu tidak masuk antrean, dan file lain tetap jalan.
- "Belum terkirim" berarti AMIGA belum menerima file itu.
- "Perlu dicek" berarti AI belum berhasil membaca, atau aturan menemukan hal yang perlu dicek di layar review.
- Catatan invoice yang sama sudah pernah diunggah berarti isinya kembar dengan unggahan lama, jadi tidak diproses ulang.

**Pertanyaan umum.** Siapa yang bisa melihat hasil unggahan? Invoice yang diterima muncul di dashboard semua akun yang ditugaskan ke klien itu. Progres per file dan tombol Kirim ulang yang belum terkirim hanya ada di halaman pengunggah selama masih terbuka.
