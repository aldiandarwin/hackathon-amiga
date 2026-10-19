---
sop_id: KTL-PEMISAHAN-TUGAS
kategori: kontrol
tahap: review, persetujuan
peran: pic-klien, finance-reviewer, service-lead, system-admin, robot-admin, amiga-director
status_aturan: brief-v2.0
sumber: brief hal. 6, 7 tabel peran, dan hal. 9 skenario 5; BRD 6.1; app/review.py assess, approve, dan director_approve; app/service.py edit dan submit; app/static/app.js updateSave dan updateApproval; app/database.py seed akun dan locked_request; app/voucher_clean.py render_clean v7; prototype/amiga_ocr/validation.py:167-182; arsitektur §7; acceptance AC-05 dan AC-20
---

# Pemisahan tugas: siapa yang tidak boleh menyetujui

**Aturan.**
- Hanya PIC yang mengunggah, dan pengunggah tidak boleh menyetujui invoice itu.
- PIC mencocokkan lalu mengajukan. Finance memeriksa lalu menyetujui, tidak boleh mendahului PIC.
- Penyetuju Finance tidak boleh menjadi manajer keuangan yang menyetujui voucher yang sama.
- System Admin tidak punya hak persetujuan transaksi.
- AI tidak pernah menyetujui. Aturan otomatis paling jauh menghasilkan "Siap diperiksa".
- Service Lead tidak mengotorisasi pembayaran klien.

**Alasan.** Pemisahan tugas mencegah konflik kepentingan dan pembayaran yang lolos tanpa pemeriksa kedua.

**Cara sistem menegakkan.** Unggah ditolak untuk selain PIC. Tombol "Setujui" hanya aktif untuk Finance Reviewer, lalu untuk Manajer Keuangan AMIGA. PIC hanya mendapat tombol "Ajukan ke Finance". Kalau tombol nonaktif, bar aksi menulis alasannya. Server memeriksa ulang saat persetujuan dikirim:
- FORBIDDEN: akun bukan Finance Reviewer, atau bukan Manajer Keuangan AMIGA untuk persetujuan akhir.
- NOT_SUBMITTED: PIC belum mengajukan invoice itu ke Finance.
- SELF_APPROVAL_FORBIDDEN: pengunggah menyetujui invoicenya sendiri, atau penyetuju Finance menjadi manajer keuangan.
- NOT_FOUND: akun tidak ditugaskan ke klien itu.

Nama PIC pengaju dan reviewer dibekukan di data voucher, lalu tercetak bersama nama manajer keuangan di tiga kotak tanda tangan. Peran System Admin belum ada di PoC, jadi penolakannya baru diuji di kontrak prototipe.

**Pertanyaan umum.** Bisakah Finance mengunggah invoice? Tidak lagi. Server menolak dengan FORBIDDEN, dan menu Finance berisi "Persetujuan". Invoice lama yang dulu diunggah Finance tetap butuh Finance Reviewer lain pada klien itu.
