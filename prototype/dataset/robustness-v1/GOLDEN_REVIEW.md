# Jawaban pembanding ringkas

Data sintetis rekayasa, belum disahkan Finance. Nilai sumber tidak diperbaiki untuk memaksa kalkulasi cocok. Holdout hanya ditampilkan untuk review dataset; belum dinilai sebagai keluaran model.

| Kasus | Nomor invoice | Items | Subtotal | Diskon | Pajak | Total tercetak | Rekening | Status ideal |
|---|---|---|---|---|---|---|---|---|
| amiga.robust.r01.v1 | SIM-2026-0001 | 3 | 117400.00 | 0.00 | 0.00 | 117400.00 | 003900000101 | READY_FOR_REVIEW |
| amiga.robust.r02.v1 | 000042-INV-SIM | 3 | 124000.00 | 0.00 | 0.00 | 124000.00 | 000001230045 | READY_FOR_REVIEW |
| amiga.robust.r03.v1 | SIM-2026-0003 | 3 | 51445.05 | 500.25 | 1250.50 | 52195.30 | 003900000301 | READY_FOR_REVIEW |
| amiga.robust.t01.v1 | SIM-2026-0004 | 20 | 1125250.00 | 0.00 | 0.00 | 1125250.00 | 003900000401 | READY_FOR_REVIEW |
| amiga.robust.t02.v1 | SIM-2026-0005 | 3 | 143800.00 | 0.00 | 0.00 | 143800.00 | 003900000501 | READY_FOR_REVIEW |
| amiga.robust.t03.v1 | SIM-2026-0006 | 3 | 150400.00 | 0.00 | 0.00 | 150400.00 | 003900000601 | READY_FOR_REVIEW |
| amiga.robust.t04.v1 | SIM-2026-0007 | 3 | 157000.00 | 0.00 | 0.00 | 157000.00 | 003900000701 | READY_FOR_REVIEW |
| amiga.robust.t05.v1 | SIM-2026-0008 | 3 | 163600.00 | 0.00 | 0.00 | 163600.00 | null | EXCEPTION |
| amiga.robust.t06.v1 | SIM-2026-0009 | 3 | 170200.00 | 0.00 | 0.00 | 180200.00 | 003900000901 | EXCEPTION |
| amiga.robust.t07.v1 | SIM-2026-0010 | 3 | 176800.00 | 0.00 | 0.00 | 176800.00 | 003900001001 | EXCEPTION |
| amiga.robust.h01.v1 | SIM-2026-0011 | 8 | 483150.00 | 0.00 | 0.00 | 483150.00 | 003900001101 | READY_FOR_REVIEW |
| amiga.robust.h02.v1 | SIM-2026-0012 | 3 | 190000.00 | 0.00 | 0.00 | 190000.00 | null | EXCEPTION |
| amiga.robust.h03.v1 | SIM-2026-0013 | 3 | 196600.00 | 0.00 | 0.00 | 196600.00 | 003900001301 | EXCEPTION |

Rincian semua baris, field dan bukti halaman berada pada cases.jsonl. Angka desimal menggunakan titik dalam JSON; PDF menggunakan format Indonesia. Status ideal memakai konteks master/riwayat dataset serta transkrip authoring, bukan master aplikasi atau keluaran OCR.
