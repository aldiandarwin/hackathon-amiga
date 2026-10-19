# Invoice robustness v1 — kontrak evaluasi

Keputusan yang dibantu: menentukan sampel mana yang layak memakai slot OCR live dan menunjukkan kesalahan ekstraksi/validasi secara terpisah. Scope yang disetujui: 10–15 invoice sintetis, jawaban pembanding, pemeriksaan lokal dan laporan. Versi ini memilih 13 kasus: 3 regression, 7 targeted dan 3 holdout. Tidak ada perubahan prompt, model, aplikasi, master produksi, ledger, atau panggilan API.

## Sumber dan batas

- VERIFIED: kontrak `amiga_ocr/contracts.py`, validasi `validation.py`, prompt PDF yang sudah ada, dan checklist AC-02/03/04/09/10/11/21.
- VERIFIED: tiga smoke live sebelumnya hanya PDF digital satu halaman. Tidak ada bukti kegagalan scan aktual; kasus sulit baru adalah hipotesis batas sintetis, bukan insiden produksi.
- Jawaban dibuat dari spesifikasi dokumen, bukan dari keluaran model. Angka pajak/diskon hanya nominal tercetak untuk menguji aritmetika, bukan penerapan tarif/peraturan pajak.
- Status jawaban: ENGINEERING_FIXTURE_NOT_FINANCE_APPROVED. Finance/Product Owner bertanggung jawab mengesahkan aturan/ambang bisnis sebelum acceptance produksi. Persetujuan itu tidak menghalangi pembuatan paket pengujian lokal ini.
- Semua nama/rekening/riwayat palsu. Holdout memakai keluarga dokumen berbeda; tidak dipakai untuk tuning atau baseline sekarang. Pembuat dataset melihat label saat authoring/QA sehingga ini bukan holdout buta independen.

## Kriteria sebelum menjalankan baseline

1. Struktur JSON tepat; identifier string persis termasuk nol depan; angka dibandingkan sebagai Decimal, null tidak menjadi nol.
2. Setiap line item ada, berurutan, nilainya sesuai. Baris hilang/tambahan dihitung sebagai error.
3. Evidence mengarah ke dokumen dan halaman asli serta nilai sumber yang benar. PDF digital dapat diverifikasi dengan text layer; scan memakai anotasi authoring yang sudah diperiksa visual, bukan OCR hasil model sebagai bukti dirinya sendiri.
4. Status dan pasangan kode/status blocking sesuai jawaban. Total salah atau rekening tidak tersedia tidak boleh lolos review.
5. Setiap error kritis menggagalkan kasus. Kasus hilang, duplikat ID, metadata model/prompt hilang, hash input berbeda dan execution error tidak boleh diam-diam dikeluarkan dari denominator.
6. Laporan harus membedakan kesalahan output, evidence, validasi dan eksekusi; penyebab model/OCR/pemetaan tidak dapat dipastikan tanpa trace intermediate.
7. Tidak ada klaim kualitas OCR ketika tidak ada output provider aktual. Baseline lokal memasukkan jawaban ideal ke validator lama untuk memeriksa aturan; ini bukan baseline OCR.

## Artefak dan reproduksi

- 13 PDF terpisah, satu paket review PDF, JSONL dataset, manifest hanya input, jawaban pembanding dan transkrip halaman.
- Builder menolak menimpa dataset yang dibekukan; versi baru diperlukan jika isi sumber/jawaban harus diubah.
- Hash dataset, input, kode validator/grader, prompt, model referensi, tanggal UTC dan versi library disimpan pada laporan.
- Runner lokal memblokir socket dan tidak mengimpor/memanggil klien jaringan. Ledger hanya dibaca dengan SQLite read-only sebelum/sesudah.
- Baseline: 10 kasus development (regression + targeted). Tiga holdout tetap NOT_RUN.
- Kalibrasi grader memakai output dengan cacat yang sengaja disisipkan; dilabeli MUTATION_CONTROL, bukan hasil model atau candidate improvement.
- Output provider tersimpan dapat dinilai kemudian dengan mode grade; tidak menyediakan opsi panggilan API.

Penerimaan paket: semua PDF <=5 MB/5 halaman; digital text lengkap; scan tanpa text layer; 18 halaman invoice ter-render dan terlihat sesuai spesifikasi; JSONL strict lulus; semua hasil/gap tetap dilaporkan meski baseline gagal; tidak ada biaya baru.
