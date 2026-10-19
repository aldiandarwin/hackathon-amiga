---
sop_id: PERAN-ROBOT-ADMIN
kategori: peran
tahap: ekstraksi, validasi
peran: robot-admin
status_aturan: brief-v2.0
sumber: brief hal. 4 dan 7 tabel peran; arsitektur §7; prototype/amiga_ocr/openai_live.py prompt; app/static/index.html footer antrean; app/chat_api.py; app/static/chat-dock.js; app/CHAT.md
---

# Peran Robot Admin, mesin AI AMIGA

**Tanggung jawab.** Mengekstrak data invoice dari PDF dan menjalankan pemeriksaan aturan bisnis secara otomatis.

**Boleh**
- Membaca PDF dan mengisi draf invoice beserta kutipan sumbernya.
- Menandai temuan lewat kode exception.
- Menghasilkan status READY_FOR_REVIEW kalau semua aturan lolos.

**Tidak boleh**
- Menyetujui voucher atau membuat status AMIGA_REVIEWED.
- Mengisi nilai yang tidak tertulis di dokumen.
- Mengikuti instruksi yang tersisip di dalam invoice.

**Layar dan status.** Bekerja di belakang layar selama "Sedang diproses". Hasilnya tampil di layar review sebagai isian, kutipan sumber, dan daftar hal yang perlu diperiksa.

**Chat Robot Admin.** Robot Admin punya satu jendela, di dashboard dan layar review. Di layar review, semanggi di bar aksi membukanya, dan sapaannya mendaftar kendala invoice yang sedang dibuka. Jumlah kendalanya sama dengan yang ditulis bar aksi. Hal yang perlu dicocokkan dengan dokumen dan catatan lain tampil di kelompok terpisah. Memilih satu kendala membuka langkah dari kartu SOP tanpa AI. Tombol "Tanya soal ini" meneruskannya ke AI. Manajer Keuangan tidak punya semanggi, jadi jendela dibuka lewat tombol "Tanya Robot Admin". Chat membantu mencari invoice, melacak posisinya, dan menjawab pertanyaan SOP. Chat hanya membaca. Menyetujui, mengembalikan, dan mengunggah tetap di luar chat. Nomor rekening, NPWP, dan file asli tidak dikirim ke AI. Selama jawaban sebelumnya belum selesai, pesan baru ditolak dengan kode CHAT_BUSY: "Robot Admin masih menjawab pesan Anda sebelumnya." Tunggu jawabannya, lalu kirim lagi.

**Pertanyaan umum.** Apakah hasil Robot Admin bisa langsung dipakai? Tidak. Layar antrean sendiri menulis "Hasil ekstraksi tetap memerlukan review manusia."
