---
sop_id: EXC-NPWP_MISMATCH
kategori: exception
kode: NPWP_MISMATCH
tahap: validasi, review
peran: finance-reviewer, pic-klien
status_aturan: demo-rules.v1
sumber: prototype/amiga_ocr/validation.py validate_invoice; app/service.py context; app/database.py seed vendor; app/schema.sql vendors.npwp
---

# NPWP_MISMATCH: NPWP vendor di dokumen berbeda dari master vendor

**Ringkasnya.** NPWP yang terbaca dari invoice tidak sama dengan NPWP vendor di master data. Ini bisa berarti salah vendor atau penagih yang tidak berhak. Request masuk EXCEPTION. Seperti rekening yang beda, approval tidak tertahan, tapi Finance wajib memastikannya dulu.

**Pesan di layar.** "NPWP vendor dicocokkan dengan master vendor."

**Istilah lain.** NPWP beda, NPWP tidak cocok, NPWP vendor salah.

**Langkah penanganan**
1. Bandingkan isian NPWP vendor dengan dokumen asli di halaman yang ditunjuk kutipan sumber.
2. Kalau AI salah baca, Finance Reviewer menyalin NPWP persis dari dokumen, mengisi alasan koreksi, lalu menyimpan.
3. Kalau dokumen memang mencetak NPWP lain, hubungi PIC klien untuk memastikan vendor yang benar.

**Dilarang.** Mengganti NPWP supaya cocok dengan master. Menyetujui invoice dengan NPWP beda tanpa konfirmasi.

**Selesai kalau.** NPWP sesuai dokumen dan cocok dengan master, lalu NPWP_MATCH muncul.

**Bedanya dengan.** NPWP_CHECK hanya peringatan saat NPWP tidak terlihat atau jumlah digitnya salah. NPWP_MISMATCH berarti NPWP terbaca jelas tetapi beda dengan master.

**Pertanyaan umum.** Vendor ganti NPWP, boleh langsung diproses? Jangan. Minta bukti dari vendor, lalu Finance memutuskan dan menulis buktinya di "Catatan review". Di PoC master belum bisa diubah.

Aturan: demo-rules.v1.
