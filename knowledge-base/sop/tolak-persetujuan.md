---
sop_id: TOLAK-PERSETUJUAN
kategori: penolakan
tahap: persetujuan
peran: finance-reviewer, pic-klien
status_aturan: poc-teknis
sumber: app/review.py assess dan approve; app/main.py approve; app/static/app.js renderDecision, updateSave, updateApproval, updateSignSubmit, loadDetail, toast, dan submit persetujuan; app/static/index.html bar aksi dan dialog persetujuan; app/tests/test_review.py; app/tests/test_signoff.py
---

# Persetujuan review ditolak: arti pesan dan tindakannya

**Ringkasnya.** Persetujuan tidak tersimpan, jadi status dan voucher tidak berubah. Kalau syarat belum terpenuhi, "Setujui" nonaktif. Alasannya tertulis di bar aksi dan tab "Voucher & persetujuan". Di dialog persetujuan, "Setujui" nonaktif sampai pernyataan dicentang, password diisi, dan "Catatan review" minimal 5 karakter.

Alasan yang bisa muncul:
- "Persetujuan review hanya tersedia untuk Finance Reviewer." Akunmu PIC. Server menolak dengan FORBIDDEN.
- "Pengunggah tidak dapat menyetujui invoice sendiri. Gunakan reviewer lain." Server menolak dengan SELF_APPROVAL_FORBIDDEN.
- "PIC Intake belum mengajukan invoice ini ke Finance." Server menolak dengan NOT_SUBMITTED. Minta PIC klien itu mengajukan.
- "Lengkapi isian wajib sebelum menyetujui" lalu nama isiannya. Server menolak dengan UNRESOLVED_EXCEPTION. Kendala lain, misalnya total tidak cocok, tidak menahan persetujuan.
- "Pilih jenis potongan pajak sebelum menyetujui." Pajak belum dipilih.
- "Invoice belum tersedia untuk persetujuan review." Ekstraksi belum selesai atau gagal.

Pesan sesudah "Setujui" ditekan:
- VERSION_CONFLICT, "Versi berubah. Muat ulang sebelum menyetujui." Ada koreksi baru dari sesi lain. Dialog tertutup dan versi terbaru dimuat.
- DOCUMENT_CHANGED, "Dokumen asli berubah; persetujuan diblokir." Hentikan dan laporkan ke Tech Lead.
- TAX_ADJUSTMENT_CONFIRMATION_REQUIRED: centang konfirmasi tambahan PPN di dialog.
- Penolakan password dan pernyataan punya kartu sendiri. SOURCE_REVIEW_REQUIRED, REASON_REQUIRED, dan INVALID_TRANSITION jarang terlihat.

**Pertanyaan umum.** Kenapa tombolnya hilang? Ada koreksi yang belum disimpan, dan bar aksi menulis "Simpan koreksi dulu sebelum menyetujui". Simpan, atau kembalikan isian ke nilai semula.
