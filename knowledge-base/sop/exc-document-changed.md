---
sop_id: EXC-DOCUMENT_CHANGED
kategori: exception
kode: DOCUMENT_CHANGED
tahap: ekstraksi, persetujuan, audit
peran: pic-klien, finance-reviewer
status_aturan: poc-teknis
sumber: app/service.py process_next; app/review.py approve; app/database.py transaction; app/static/app.js loadDetail, renderHistory, dan submit persetujuan; database-design-draft documents; arsitektur §8
---

# DOCUMENT_CHANGED: file PDF tersimpan berubah sejak diunggah

**Ringkasnya.** Sidik digital file PDF di penyimpanan tidak sama lagi dengan saat diunggah. Sistem berhenti supaya data tidak diambil atau disetujui dari dokumen yang berubah. Kalau terdeteksi saat ekstraksi, request masuk EXCEPTION dan tampil "Perlu perhatian". Kalau terdeteksi saat persetujuan, status tidak berubah dan riwayat tidak bertambah.

**Pesan di layar.** Saat ekstraksi, antrean menulis "Dokumen perlu diperiksa admin". Layar review menampilkan "Proses sudah berhenti" dengan keterangan "Pemeriksaan keutuhan dokumen belum lolos. Teruskan ID request ke admin sebelum melanjutkan." Riwayat mencatat "Ekstraksi dihentikan". Saat Finance menyetujui, dialog persetujuan menampilkan "Dokumen asli berubah; persetujuan diblokir." Layar tidak menampilkan kode ini.

**Istilah lain.** file berubah, dokumen rusak, hash tidak cocok, integritas dokumen.

**Langkah penanganan**
1. Hentikan pekerjaan pada request ini.
2. Laporkan segera ke Tech Lead sebagai masalah integritas dokumen.
3. Catat nama file dari subjudul layar review, lalu tanggal dan nama pengunggah dari tab "Riwayat perubahan".

**Dilarang.** Melanjutkan review atau mengunggah file pengganti sebelum penyebabnya diperiksa.

**Selesai kalau.** Penyebab perubahan file sudah diperiksa tim teknis, dan keputusannya dicatat di luar aplikasi.

**Pertanyaan umum.** Seberapa sering ini terjadi? Seharusnya hampir tidak pernah, karena file asli disimpan privat dan tidak boleh diubah. Karena itu setiap kejadian perlu diperiksa.

Aturan: batasan teknis PoC.
