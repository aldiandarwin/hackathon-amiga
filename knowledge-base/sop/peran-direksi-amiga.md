---
sop_id: PERAN-DIREKSI-AMIGA
kategori: peran
tahap: persetujuan, voucher, tindak_lanjut
peran: amiga-director
status_aturan: belum-diputuskan
sumber: brief hal. 5 dan 7 tabel peran, Client Approver di luar aplikasi; app/database.py seed akun dan migrasi akun manajer keuangan; app/schema.sql peran; app/main.py listing, director_approval, dan director_return; app/review.py signature_state, director_approve, dan director_return; app/signing.py DIRECTOR_CONSENT; app/service.py intake dan edit; app/voucher_clean.py render_clean v7; app/static/app.js ROLES, enter, renderDecision, openSign, dan submit persetujuan; app/static/app.css role-director; app/static/index.html dialog persetujuan dan pengembalian; web/components/shell.tsx menu Persetujuan; app/tests/test_signoff.py; output/preparation/acceptance-checklist.md keputusan sebelum acceptance final
---

# Peran Manajer Keuangan AMIGA: menyetujui voucher final

**Tanggung jawab.** Memberi persetujuan akhir sebagai Manajer Keuangan AMIGA. Sesudah Finance Reviewer menyetujui, manajer keuangan menyetujui voucher final atau mengembalikannya ke Finance dengan alasan.

**Boleh**
- Membaca invoice, draf voucher, dan riwayat klien yang ditugaskan.
- Menyetujui draf berstatus "Menunggu manajer keuangan". Tekan "Setujui", centang pernyataan, isi "Password akun Anda", lalu tekan "Setujui".
- Menekan "Kembalikan ke Finance", mengisi "Alasan" minimal 5 karakter, lalu menekan "Kembalikan".
- Mengunduh draf dan voucher final, lalu menandatangani voucher cetak di kotak "Disetujui Oleh".

**Tidak boleh**
- Mengunggah invoice, mengoreksi data, atau menyetujui tahap Finance.
- Menyetujui voucher dari template lama. Voucher itu hanya bisa dikembalikan.
- Membuka data klien yang tidak ditugaskan.

**Layar dan status.** Kode perannya tetap AMIGA_DIRECTOR, dengan label "Manajer Keuangan AMIGA". Akun demo manajer.keuangan@amiga.local, Bagas Wiratama, ditugaskan ke 20 klien, termasuk klien baru buatan PIC. Menu "Persetujuan" memuat voucher yang menunggu keputusannya. Hasilnya AMIGA_APPROVED, di layar "Disetujui manajer keuangan", dan voucher final ber-QR verifikasi. Voucher cetak punya tiga kotak tanda tangan basah: PIC, Finance, dan manajer keuangan.

**Pertanyaan umum.** Siapa yang menyetujui voucher final? Manajer Keuangan AMIGA, sesudah Finance menyetujui. Apakah tagihan langsung dibayar sesudahnya? Tidak. Klien tetap menyetujui dan membayar di luar aplikasi. AMIGA tidak mentransfer dana.

Aturan: persetujuan Manajer Keuangan AMIGA adalah ekstensi PoC di luar brief, menunggu persetujuan AMIGA. Tanda tangan di voucher cetak dibubuhkan basah.
