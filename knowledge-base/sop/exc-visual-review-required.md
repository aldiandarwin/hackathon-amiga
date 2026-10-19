---
sop_id: EXC-VISUAL_REVIEW_REQUIRED
kategori: exception
kode: VISUAL_REVIEW_REQUIRED
tahap: review
peran: finance-reviewer
status_aturan: demo-rules.v1
sumber: app/service.py snapshot; app/review.py SOURCE_CHECKS; app/settings.py batas PDF; app/static/index.html panel dokumen; app/README.md batas tahap
---

# VISUAL_REVIEW_REQUIRED: nilai harus dicocokkan manual dengan gambar dokumen

**Ringkasnya.** PDF berisi halaman scan tanpa lapisan teks. Sistem meminta manusia mencocokkan setiap nilai dengan gambar halaman. Statusnya NOT_CHECKED, jadi request tetap "Perlu perhatian".

**Pesan di layar.** "Foto atau scan ini tidak punya lapisan teks. Cocokkan nilai dengan gambar dokumen."

**Istilah lain.** cek visual, review manual, invoice scan, foto invoice.

**Langkah penanganan**
1. Buka gambar halaman di panel "Invoice asli". Kalau kurang jelas, pakai "Buka PDF".
2. Cocokkan semua isian dengan gambar: vendor, nomor, tanggal, baris barang, total, dan rekening.
3. Koreksi yang salah. Tulis di "Alasan koreksi" bahwa pengecekan dilakukan secara visual, beserta halamannya.

**Dilarang.** Melewati isian yang tidak bertanda. Pada scan, isian tanpa tanda pun belum tentu benar.

**Selesai kalau.** Semua isian sudah dicocokkan dengan gambar. Di PoC saat ini, tanda ini tidak hilang lewat koreksi. Reviewer mengonfirmasi pemeriksaan visual itu saat menyetujui, dan tanda ini tidak menghalangi persetujuan.

**Bedanya dengan.** OCR_INCOMPLETE menandai halaman yang tidak terbaca. Kartu ini mengatur cara memeriksanya.

**Pertanyaan umum.** Foto invoice dari ponsel boleh diunggah? Boleh, sebagai JPG atau PNG maksimal 5 MB, atau PDF maksimal 5 halaman. Foto tidak punya lapisan teks, jadi siapkan waktu untuk cek visual penuh.

Aturan: demo-rules.v1.
