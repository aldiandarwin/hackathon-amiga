---
sop_id: ALUR-PERSETUJUAN
kategori: alur
tahap: persetujuan
peran: finance-reviewer
status_aturan: brief-v2.0
sumber: brief hal. 5 dan 7; arsitektur §7 workflow; app/review.py SOURCE_CHECKS, assess, verify_signer, dan approve; app/signing.py REVIEWER_CONSENT; app/main.py approve; app/static/index.html bar aksi dan dialog persetujuan; app/static/app.js renderDecision, updateApproval, openSign, dan submit persetujuan; app/voucher_clean.py render_clean v7; output/app-stage8/VERIFICATION.md; acceptance AC-23 dan keputusan sebelum acceptance final
---

# Persetujuan independen oleh Finance

**Tujuan.** Reviewer independen menyetujui data invoice, supaya kesalahan AI dan konflik kepentingan tertahan.

**Siapa.** Finance Reviewer yang ditugaskan ke klien itu. Finance tidak mengunggah, PIC yang mengunggah.

**Prasyarat.** PIC sudah mengajukan, enam isian wajib terisi, pajak terhitung, dan semua koreksi sudah disimpan. Status "Siap diperiksa", "Perlu perhatian", atau "Dikembalikan manajer keuangan". Kendala yang masih terbuka tidak menahan persetujuan.

**Langkah**
1. Cocokkan semua isian dengan dokumen asli, termasuk rekening dan nominal. Baca saran di tiap kendala, lalu putuskan: koreksi dulu, "Kembalikan ke PIC", atau setujui.
2. Tekan "Setujui" di bar bawah.
3. Di dialog "Setujui review", isi "Catatan review" minimal 5 karakter. Kalau masih ada kendala, tulis kenapa tetap disetujui. Catatan ini tercetak di voucher.
4. Centang pernyataan bahwa data sudah dicocokkan dengan dokumen asli. Isi "Password akun Anda", lalu tekan "Setujui".

**Hasil.** Status menjadi AMIGA_REVIEWED, di layar "Menunggu manajer keuangan". Versi data dibekukan. Draf voucher resmi dibuat otomatis. Namamu tercetak di kotak "Diperiksa Oleh".

**Kontrol.** Sistem memeriksa ulang password, peran, penugasan, pengunggah, versi, keutuhan file, isian wajib, dan pajak. Mata uang selain IDR ikut memblokir. Kendala lain tercatat di riwayat dan terlihat Manajer Keuangan. Koreksi sesudah persetujuan membatalkan approval dan draf voucher lama.

**Pertanyaan umum.** Bisakah invoice ditolak? Belum. Finance bisa "Kembalikan ke PIC", dan Manajer Keuangan AMIGA ke Finance. Status REJECTED belum diputuskan, pemilik: Finance dan Product Owner.

Aturan: kendala sebagai saran, bukan pemblokir, adalah aturan PoC sejak 15 Okt 2026, belum disetujui Finance.
