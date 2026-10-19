---
sop_id: ALUR-REVIEW-KOREKSI
kategori: alur
tahap: review
peran: pic-klien, finance-reviewer
status_aturan: demo-rules.v1
sumber: brief hal. 5 dan 8; app/static/app.js renderFields, markDirty, updateSave, dan submit koreksi; app/static/numbers.js; app/static/index.html catatan koreksi; app/service.py snapshot, detail, dan edit; app/review.py SOURCE_CHECKS dan director_return; app/README.md alur; app/static/review-guide.js amigaCheckHint
---

# Review dan koreksi hasil ekstraksi invoice

**Tujuan.** Memastikan data hasil baca AI sama dengan PDF asli sebelum masuk persetujuan.

**Siapa.** PIC Klien mengoreksi selama "Belum diajukan". Finance Reviewer tim itu bisa mengoreksi sebelum maupun sesudah pengajuan.

**Prasyarat.** Ekstraksi sudah selesai, jadi status bukan lagi "Menunggu proses" atau "Sedang diproses".

**Langkah**
1. Buka invoice dari antrean, misalnya lewat filter "Belum diajukan" atau "Perlu perhatian".
2. Baca kendala dan sarannya. "Pakai saran" hanya mengisi form.
3. Cocokkan tiap isian dengan PDF. Kutipan sumber tampil di atas dokumen saat isian dipilih.
4. Ubah nilai yang salah. Tanggal dan mata uang dipilih dari daftar. Angka memakai titik pemisah ribuan dan koma desimal, misalnya 150.000,50.
5. Finance menekan "Simpan koreksi" dengan "Alasan koreksi" minimal 5 karakter. PIC menekan "Simpan draf" atau langsung "Ajukan ke Finance".

**Hasil.** Koreksi tersimpan sebagai versi baru, dan nilai lama serta baru tercatat di tab "Riwayat perubahan". Isian yang berbeda dari hasil AI awal mendapat tanda HUMAN_CORRECTION_PENDING, jadi statusnya EXCEPTION. Isian yang diubah juga bisa mendapat tanda kutipan sumber. Tanda-tanda ini tidak menghalangi persetujuan. Koreksi sesudah persetujuan Finance membatalkan approval dan voucher lamanya. Sesudah "Disetujui manajer keuangan", koreksi ditolak.

**Kontrol.** Versi lama tidak pernah ditimpa. Koreksi tidak membenarkan rekening secara otomatis. PIC tidak bisa mengoreksi sesudah mengajukan, server menolak dengan INTAKE_LOCKED. Finance bisa "Kembalikan ke PIC" dengan alasan, lalu PIC mengajukan ulang.

**Pertanyaan umum.** Kenapa "Simpan koreksi" tidak terlihat? Tombolnya baru muncul sesudah ada perubahan. Kalau nonaktif, ada format angka yang salah.
