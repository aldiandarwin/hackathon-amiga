---
sop_id: LAYAR-REVIEW
kategori: layar
tahap: review, persetujuan
peran: finance-reviewer, pic-klien, amiga-director
status_aturan: demo-rules.v1
sumber: app/static/index.html layar review, bar aksi, dan dialog persetujuan; app/static/app.js renderChecks, inputField, renderFields, updateSave, updateApproval, showEvidence, updatePageIndicator, renderHistory, signatureHTML, renderDecision, dan openSign; app/static/numbers.js; app/static/app.css layar terbagi dan kelas changed; prototype/amiga_ocr/contracts.py:79-84 dan 109-119; app/static/review-guide.js amigaCheckHint
---

# Layar review invoice dan arti isiannya

**Bagian layar**
- Kiri: "Invoice asli" berisi gambar tiap halaman, penunjuk halaman, dan tautan "Buka PDF". Sesudah voucher ada, muncul tab "Invoice asli" dan "Draf voucher" atau "Voucher final".
- Kanan: tab "Data invoice", "Voucher & persetujuan", dan "Riwayat perubahan".
- Tab "Data invoice" dibagi per bagian: "Invoice", "Identitas", "Item", "Nominal", dan "Rekening". Barang tampil satu per satu.
- Tab "Voucher & persetujuan" berisi nominal dibayar, kotak pengajuan PIC, kotak persetujuan Finance dan Manajer Keuangan AMIGA, koreksi, serta kartu voucher.
- Bawah: bar aksi hanya berisi tombol yang bisa dipakai. Finance melihat "Kembalikan ke PIC" dan "Setujui", atau hanya "Simpan koreksi" selama ada perubahan. PIC melihat "Ajukan ke Finance". Manajer keuangan melihat "Kembalikan ke Finance".

**Arti tampilan**
- Saat isian dipilih, kolom kiri melompat ke halaman sumbernya dan menampilkan kutipan nilainya.
- Kendala tampil di atas bagian isiannya, dengan hitungan dan saran. "Pakai saran" hanya mengisi form, Finance tetap menyimpan dan memutuskan. Isian yang disebut kendala diberi tanda "Perlu dicek".
- Isian yang berbeda dari hasil AI awal berlatar kuning muda dan menampilkan "Nilai awal dari dokumen".
- Tanggal dipilih dari kalender. Angka memakai titik pemisah ribuan dan koma desimal, misalnya 1.500.000,50. Format lain seperti 25000.00 ditolak, dan bar aksi menulis "Periksa isian merah sebelum menyimpan".

**Pertanyaan umum.** Kenapa isian tidak bisa diketik? PIC hanya bisa mengoreksi selama "Belum diajukan", sesudahnya koreksi oleh Finance Reviewer. Manajer keuangan tidak mengoreksi. Sesudah "Disetujui manajer keuangan", isian terkunci untuk semua akun.
