---
sop_id: EXC-HUMAN_CORRECTION_PENDING
kategori: exception
kode: HUMAN_CORRECTION_PENDING
tahap: review, persetujuan
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: app/service.py snapshot dan edit; prototype/amiga_ocr/validation.py:21; app/review.py SOURCE_CHECKS, assess, dan approve; app/static/app.js renderDecision dan openSign; app/tests/test_app.py:154; brief hal. 5 review independen; output/app-stage3/VERIFICATION.md
---

# HUMAN_CORRECTION_PENDING: nilai sudah dikoreksi manusia dan menunggu review

**Ringkasnya.** Isian ini sudah diubah manusia dari hasil AI awal. Sistem menandainya NOT_CHECKED supaya diperiksa lagi, jadi request menjadi EXCEPTION walau koreksinya benar. Tanda ini tidak menghalangi persetujuan.

**Pesan di layar.** "Nilai telah dikoreksi manusia; bukti asli tetap disimpan untuk review." diikuti nama field yang diubah.

**Istilah lain.** sudah dikoreksi masih perlu perhatian, status tidak berubah sesudah simpan, koreksi manual.

**Langkah penanganan**
1. Pastikan setiap isian yang dikoreksi sesuai PDF.
2. Cek tab "Riwayat perubahan". Nilai lama, nilai baru, dan alasannya harus tercatat jelas.
3. PIC yang mengoreksi tetap bisa mengajukan, dengan catatan bila dialog masih menampilkan kendala.
4. Sesudah diajukan, Finance Reviewer yang bukan pengunggah memutuskan lewat "Setujui" atau "Kembalikan ke PIC".

**Dilarang.** Mengembalikan nilai ke hasil AI yang salah supaya tanda ini hilang. Tanda memang hanya hilang kalau isian sama lagi dengan hasil AI awal.

**Selesai kalau.** Reviewer mencentang pernyataan di dialog persetujuan lalu menyetujui. Daftar tanda yang dikonfirmasi tercatat di keputusan.

**Pertanyaan umum.** Kenapa status tetap "Perlu perhatian" sesudah koreksi disimpan? Setiap isian yang berbeda dari hasil AI awal mendapat tanda ini. Isian itu juga bisa mendapat tanda kutipan sumber, karena kutipan lama tetap dipakai. Semua tanda itu menahan status di demo-rules.v1, tapi tidak menghalangi persetujuan.

Aturan: demo-rules.v1. Tanda yang cukup dikonfirmasi reviewer adalah aturan PoC, belum disetujui Finance.
