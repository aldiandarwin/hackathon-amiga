---
sop_id: ALUR-INTAKE
kategori: alur
tahap: intake
peran: pic-klien, intake-support, finance-reviewer
status_aturan: brief-v2.0
sumber: brief hal. 5, 7, dan 8; BRD 3 dan 6.1; app/batches.py; app/service.py inspect_pdf dan intake; web/app/unggah/page.tsx; web/lib/upload.ts; app/settings.py:26-28; arsitektur §3 dan §6; output/preparation/api-contract-draft.md intake dan multiple upload; output/arsip/app/EXECUTION_BATCH.md; app/README.md multiple upload
---

# Intake: mengunggah invoice ke AMIGA

**Tujuan.** Memasukkan PDF invoice vendor ke sistem supaya diproses dan masuk antrean.

**Siapa.** PIC Klien, atau Intake Support/Backup berdasarkan delegasi resmi yang masih prosedur target. Di PoC, hanya PIC yang bisa mengunggah. Pengunggah tidak boleh menyetujui invoicenya sendiri.

**Prasyarat.** Tiap PDF berisi satu invoice, maksimal 5 halaman dan 5 MB, tanpa kata sandi. Satu batch berisi 1 sampai 5 file untuk klien yang sama. Lampiran pendukung belum didukung.

**Langkah**
1. Buka menu "Unggah invoice".
2. Pilih klien di kolom Klien, kecuali PIC hanya punya satu klien. Klien belum ada? Daftarkan lewat "+ Klien baru", dan klien itu langsung terpilih.
3. Pilih "Jenis pajak". Hapus centang "Penerima punya NPWP/NIK" kalau vendor tidak punya.
4. Tarik atau pilih 1 sampai 5 file. File yang diberi catatan akan ditolak.
5. Prosedur target: catat jenis permintaan, saluran, dan tanggal diterima.
6. Tekan "Unggah invoice". File dikirim satu per satu.

**Hasil.** Progres tiap file tampil di halaman unggah, misalnya Siap direview, "Ditolak", atau "Belum terkirim". File baru masuk antrean dengan status "Menunggu proses" lalu "Sedang diproses". Sesudah terbaca AI, invoice tampil "Belum diajukan" sampai PIC mengajukannya. File duplikat tidak masuk antrean lagi. Barisnya menunjuk request lama beserta statusnya.

**Kontrol.** File asli disimpan privat dan tidak bisa diubah. Tiap file diperiksa terpisah, jadi satu file ditolak tidak menggagalkan file lain. File baru dikirim ke layanan AI dan melewati pencatat biaya.

**Pertanyaan umum.** Kenapa ada catatan invoice yang sama sudah pernah diunggah? File dengan isi persis sama sudah pernah diunggah ke klien itu, termasuk yang gagal diproses. Sistem memakai request lama tanpa memproses ulang.
