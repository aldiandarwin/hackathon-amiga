"""Lint dan build korpus SOP AMIGA untuk Amazon Bedrock Knowledge Base.

Membaca kartu di sop/, memeriksa aturan korpus, lalu menulis dist/ berisi .md tanpa
front matter plus sidecar .md.metadata.json. Exit code adalah vonis: satu cacat
berarti dist/ tidak ditulis sama sekali.

Pemakaian (dari folder hackthon):
    .venv/Scripts/python.exe knowledge-base/tools/bangun_korpus.py            # ketat, tulis dist
    .venv/Scripts/python.exe knowledge-base/tools/bangun_korpus.py --parsial  # cakupan dan panjang jadi peringatan
    .venv/Scripts/python.exe knowledge-base/tools/bangun_korpus.py --cek      # lint saja
    .venv/Scripts/python.exe knowledge-base/tools/bangun_korpus.py --daftar-kode
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
HACKTHON = KB.parent
SOP = KB / "sop"
DIST = KB / "dist"
STATE = KB / ".state"
KOSAKATA = KB / "kosakata.json"
EVAL = KB / "eval"

# Batas karakter badan kartu. Dikalibrasi dari eksperimen kartu sintetis di pilot.
# Cohere Embed Multilingual v3 menerima maksimal 512 token dan memotong sisanya diam-diam.
ANGGARAN_KARAKTER = 1800

KATEGORI = {
    "fondasi": ("FON", ["Ringkasnya", "Pertanyaan umum"]),
    "alur": ("ALUR", ["Tujuan", "Siapa", "Prasyarat", "Langkah", "Hasil", "Kontrol", "Pertanyaan umum"]),
    "peran": ("PERAN", ["Tanggung jawab", "Boleh", "Tidak boleh", "Layar dan status", "Pertanyaan umum"]),
    "layar": ("LAYAR", ["Bagian layar", "Arti tampilan", "Pertanyaan umum"]),
    "exception": ("EXC", ["Ringkasnya", "Pesan di layar", "Istilah lain", "Langkah penanganan",
                          "Dilarang", "Selesai kalau", "Pertanyaan umum"]),
    "penolakan": ("TOLAK", ["Ringkasnya", "Pertanyaan umum"]),
    "kontrol": ("KTL", ["Aturan", "Alasan", "Cara sistem menegakkan", "Pertanyaan umum"]),
}
TAHAP = {"intake", "antrean", "ekstraksi", "validasi", "review", "persetujuan", "voucher",
         "serah_terima", "tindak_lanjut", "audit"}
PERAN = {"pic-klien", "intake-support", "robot-admin", "finance-reviewer", "service-lead",
         "system-admin", "amiga-director"}
STATUS_ATURAN = {"brief-v2.0", "demo-rules.v1", "poc-teknis", "belum-diputuskan"}
KEY_WAJIB = ("sop_id", "kategori", "status_aturan", "sumber")
KEY_LIST = {"tahap", "peran"}
KEY_SEMUA = set(KEY_WAJIB) | KEY_LIST | {"kode"}
KELAS_WAJIB_DISEBUT = {"penolakan", "lolos", "status"}
FRASA_TERLARANG = ("lihat di atas", "seperti dijelaskan sebelumnya", "lihat kartu sebelumnya", "di atas ini")
BATAS_METADATA_BYTE = 1024

POLA_KODE = re.compile(r"(?<![A-Za-z0-9_])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![A-Za-z0-9_])")
POLA_KUTIP = re.compile(r"\"([^\"\n]+)\"|“([^”\n]+)”")
POLA_SQL_KODE = re.compile(r"error_code\s*=\s*'([A-Z][A-Z0-9_]+)'")
POLA_KATA = re.compile(r"\w+", re.UNICODE)


def norm(teks: str) -> str:
    return " ".join(html.unescape(teks).split())


def berkas_sumber_kode() -> list[Path]:
    app = sorted((HACKTHON / "app").glob("*.py"))
    proto = sorted(p for p in (HACKTHON / "prototype" / "amiga_ocr").glob("*.py") if p.name != "fixtures.py")
    return app + proto


def berkas_teks_layar() -> list[Path]:
    static = HACKTHON / "app" / "static"
    return berkas_sumber_kode() + sorted(static.glob("*.js")) + sorted(static.glob("*.html"))


def kode_dari_ast() -> dict[str, set[str]]:
    """Kode yang bisa dikeluarkan app, dikumpulkan per berkas lewat ast plus regex SQL."""
    hasil: dict[str, set[str]] = {}

    def konstanta(node) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.IfExp):
            return konstanta(node.body) + konstanta(node.orelse)
        return []

    def nama_fungsi(node) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    for path in berkas_sumber_kode():
        teks = path.read_text(encoding="utf-8")
        temuan: set[str] = set()
        for node in ast.walk(ast.parse(teks, filename=str(path))):
            if isinstance(node, ast.Call) and node.args:
                fungsi = nama_fungsi(node.func)
                if fungsi in ("check", "AppError"):
                    temuan.update(konstanta(node.args[0]))
                elif (fungsi == "append" and isinstance(node.func, ast.Attribute)
                      and isinstance(node.func.value, ast.Name) and node.func.value.id == "reasons"):
                    temuan.update(konstanta(node.args[0]))
            elif isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "code" for t in node.targets):
                    temuan.update(konstanta(node.value))
            elif isinstance(node, ast.Dict):
                for kunci, nilai in zip(node.keys, node.values):
                    if isinstance(kunci, ast.Constant) and kunci.value == "code":
                        temuan.update(konstanta(nilai))
        temuan.update(POLA_SQL_KODE.findall(teks))
        temuan = {k for k in temuan if re.fullmatch(r"[A-Z][A-Z0-9_]+", k)}
        if temuan:
            hasil[str(path.relative_to(HACKTHON)).replace("\\", "/")] = temuan
    return hasil


def baca_kartu(path: Path, galat: list[str]):
    nama = path.name
    teks = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not teks.startswith("---\n"):
        galat.append(f"{nama}: tidak diawali front matter '---'")
        return None, None
    akhir = teks.find("\n---\n", 4)
    if akhir < 0:
        galat.append(f"{nama}: front matter tidak ditutup '---'")
        return None, None
    meta: dict[str, object] = {}
    for baris in teks[4:akhir].split("\n"):
        if not baris.strip():
            continue
        kunci, pemisah, nilai = baris.partition(":")
        kunci, nilai = kunci.strip(), nilai.strip()
        if not pemisah or not kunci:
            galat.append(f"{nama}: baris front matter tidak valid: {baris!r}")
            continue
        if kunci not in KEY_SEMUA:
            galat.append(f"{nama}: key front matter tidak dikenal: {kunci}")
            continue
        if kunci in meta:
            galat.append(f"{nama}: key front matter ganda: {kunci}")
            continue
        meta[kunci] = [v.strip() for v in nilai.split(",") if v.strip()] if kunci in KEY_LIST else nilai
    badan = teks[akhir + 5:].strip("\n") + "\n"
    return meta, badan


def periksa_kartu(path, meta, badan, kosakata, korpus_layar, galat, peringatan, parsial):
    nama = path.name
    for kunci in KEY_WAJIB:
        if not meta.get(kunci):
            galat.append(f"{nama}: key wajib kosong atau hilang: {kunci}")
    sop_id = str(meta.get("sop_id", ""))
    kategori = str(meta.get("kategori", ""))
    if kategori not in KATEGORI:
        galat.append(f"{nama}: kategori tidak dikenal: {kategori!r}")
        return
    awalan, label_wajib = KATEGORI[kategori]
    if not re.fullmatch(rf"{awalan}-[A-Z0-9_-]+", sop_id):
        galat.append(f"{nama}: sop_id {sop_id!r} harus berawalan {awalan}- dan huruf besar")
    if nama != sop_id.lower().replace("_", "-") + ".md":
        galat.append(f"{nama}: nama file harus {sop_id.lower().replace('_', '-')}.md")
    kode = meta.get("kode")
    if kategori == "exception":
        if not kode:
            galat.append(f"{nama}: kartu exception wajib punya key kode")
        elif kosakata.get(kode, {}).get("kelas") != "exception":
            galat.append(f"{nama}: kode {kode} bukan kelas exception di kosakata.json")
        elif sop_id != f"EXC-{kode}":
            galat.append(f"{nama}: sop_id harus EXC-{kode}")
    elif kode:
        galat.append(f"{nama}: key kode hanya untuk kartu exception")
    for nilai in meta.get("tahap", []):
        if nilai not in TAHAP:
            galat.append(f"{nama}: tahap tidak dikenal: {nilai}")
    for nilai in meta.get("peran", []):
        if nilai not in PERAN:
            galat.append(f"{nama}: peran tidak dikenal: {nilai}")
    if meta.get("status_aturan") and meta["status_aturan"] not in STATUS_ATURAN:
        galat.append(f"{nama}: status_aturan tidak dikenal: {meta['status_aturan']}")

    baris = badan.split("\n")
    judul = [b for b in baris if b.startswith("# ")]
    pertama = next((b for b in baris if b.strip()), "")
    if len(judul) != 1 or not pertama.startswith("# "):
        galat.append(f"{nama}: badan harus diawali tepat satu judul H1")
    for label in label_wajib:
        if not re.search(r"^\*\*" + re.escape(label) + r"\.?\*\*", badan, re.M):
            galat.append(f"{nama}: label wajib tidak ditemukan: **{label}**")
    if "—" in badan or "–" in badan:
        galat.append(f"{nama}: mengandung em-dash atau en-dash")
    for b in baris:
        if b.startswith("#") and ";" in b:
            galat.append(f"{nama}: heading memakai titik koma: {b}")
    kecil = badan.lower()
    for frasa in FRASA_TERLARANG:
        if frasa in kecil:
            galat.append(f"{nama}: rujukan tidak berdiri sendiri: '{frasa}'")
    for token in sorted(set(POLA_KODE.findall(badan))):
        if token not in kosakata:
            galat.append(f"{nama}: token kode tidak ada di kosakata.json: {token}")
    for lurus, keriting in POLA_KUTIP.findall(badan):
        kutipan = norm(lurus or keriting)
        if kutipan and kutipan not in korpus_layar:
            galat.append(f"{nama}: teks berkutip tidak ditemukan verbatim di app: \"{kutipan}\"")
    if len(badan) > ANGGARAN_KARAKTER:
        pesan = f"{nama}: {len(badan)} karakter, di atas anggaran {ANGGARAN_KARAKTER}"
        (peringatan if parsial else galat).append(pesan)


def n_gram(teks: str, n: int) -> set[tuple[str, ...]]:
    kata = POLA_KATA.findall(teks.lower())
    return {tuple(kata[i:i + n]) for i in range(len(kata) - n + 1)}


def periksa_kebocoran_eval(kartu, korpus_layar, galat) -> int:
    """Kalimat dari set uji di eval/*.json tidak boleh masuk kartu, supaya skor uji tidak mengukur hafalan.

    Seluruh kartu dicek per 6 kata. Baris "Istilah lain" dicek per 4 kata, karena sinonim di sana gampang tersalin
    dari soal: kebocoran 957b817 hanya 4 kata. Cek 4 kata di seluruh kartu ikut menandai baris "Pertanyaan umum"
    yang wajar, jadi dibatasi ke baris itu.
    """
    pertanyaan = [q["teks"] for p in sorted(EVAL.glob("*.json"))
                  for q in json.loads(p.read_text(encoding="utf-8")).get("pertanyaan", [])]
    if not pertanyaan:
        galat.append(f"penjaga bocor: tidak ada pertanyaan di {EVAL.name}/*.json")
        return 0
    for n, awalan in ((6, ""), (4, "**Istilah lain")):
        gram_eval = set().union(*(n_gram(t, n) for t in pertanyaan)) - n_gram(korpus_layar, n)
        for path, _, badan in kartu:
            teks = "\n".join(b for b in badan.split("\n") if b.startswith(awalan))
            for gram in sorted(gram_eval & n_gram(teks, n))[:3]:
                galat.append(f"{path.name}: rangkaian {n} kata dari set uji muncul di kartu: {' '.join(gram)}")
    return len(pertanyaan)


def sidecar(meta, versi):
    atribut = {"sop_id": meta["sop_id"], "kategori": meta["kategori"]}
    if meta.get("kode"):
        atribut["kode"] = meta["kode"]
    atribut["status_aturan"] = meta["status_aturan"]
    atribut["versi_kartu"] = versi
    ukuran = sum(len(k.encode("utf-8")) + len(v.encode("utf-8")) for k, v in atribut.items())
    isi = {"metadataAttributes": {
        k: {"value": {"type": "STRING", "stringValue": v}, "includeForEmbedding": False}
        for k, v in atribut.items()}}
    return json.dumps(isi, ensure_ascii=False, indent=2) + "\n", ukuran


def tulis_jika_berubah(path: Path, isi: str) -> bool:
    data = isi.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--parsial", action="store_true", help="cakupan dan panjang jadi peringatan")
    parser.add_argument("--cek", action="store_true", help="lint saja, tidak menulis dist")
    parser.add_argument("--sumber", type=Path, default=SOP, help="folder kartu (default sop/)")
    parser.add_argument("--daftar-kode", action="store_true", help="cetak kode hasil ast lalu keluar")
    args = parser.parse_args()

    kode_sumber = kode_dari_ast()
    if args.daftar_kode:
        for berkas, kode in kode_sumber.items():
            print(f"{berkas}: {', '.join(sorted(kode))}")
        return 0

    galat: list[str] = []
    peringatan: list[str] = []
    kosakata = json.loads(KOSAKATA.read_text(encoding="utf-8"))["kode"]
    teks_sumber = "\n".join(p.read_text(encoding="utf-8") for p in berkas_teks_layar())
    teks_sumber += "\n" + (HACKTHON / "app" / "schema.sql").read_text(encoding="utf-8")
    teks_dokumen = "\n".join(p.read_text(encoding="utf-8") for p in sorted((HACKTHON / "output").rglob("*.md")))
    korpus_layar = norm("\n".join(p.read_text(encoding="utf-8") for p in berkas_teks_layar()))

    semua_kode_sumber = set().union(*kode_sumber.values()) if kode_sumber else set()
    for kode in sorted(semua_kode_sumber - set(kosakata)):
        asal = [b for b, k in kode_sumber.items() if kode in k]
        galat.append(f"drift: kode {kode} dari {', '.join(asal)} belum diklasifikasi di kosakata.json")
    for kode, info in sorted(kosakata.items()):
        rujukan = teks_sumber if info.get("sumber") == "kode" else teks_dokumen
        if kode not in rujukan:
            galat.append(f"kosakata: {kode} bersumber '{info.get('sumber')}' tapi tidak ditemukan di sumbernya")

    kartu = []
    for path in sorted(args.sumber.glob("*.md")):
        meta, badan = baca_kartu(path, galat)
        if meta is None:
            continue
        periksa_kartu(path, meta, badan, kosakata, korpus_layar, galat, peringatan, args.parsial)
        kartu.append((path, meta, badan))
    if not kartu:
        galat.append(f"tidak ada kartu di {args.sumber}")
    id_terpakai: dict[str, str] = {}
    for path, meta, _ in kartu:
        if meta.get("sop_id") in id_terpakai:
            galat.append(f"{path.name}: sop_id ganda dengan {id_terpakai[meta['sop_id']]}")
        id_terpakai[str(meta.get("sop_id"))] = path.name

    gabungan = "\n".join(badan for _, _, badan in kartu)
    tercakup = {meta.get("kode") for _, meta, _ in kartu if meta.get("kategori") == "exception"}
    tanpa_kartu, tanpa_sebutan = [], []
    for kode, info in sorted(kosakata.items()):
        kelas = info.get("kelas")
        if kelas == "exception" and kode not in tercakup:
            tanpa_kartu.append(kode)
        elif kelas in KELAS_WAJIB_DISEBUT and not re.search(rf"(?<![A-Z0-9_]){kode}(?![A-Z0-9_])", gabungan):
            tanpa_sebutan.append(kode)
    if args.parsial:
        if tanpa_kartu or tanpa_sebutan:
            peringatan.append(f"cakupan: {len(tanpa_kartu)} kode exception belum punya kartu, "
                              f"{len(tanpa_sebutan)} kode lain belum disebut")
    else:
        galat.extend(f"cakupan: kode exception {k} belum punya kartu EXC" for k in tanpa_kartu)
        galat.extend(f"cakupan: kode {kosakata[k]['kelas']} {k} belum disebut di kartu mana pun"
                     for k in tanpa_sebutan)
    jumlah_soal = periksa_kebocoran_eval(kartu, korpus_layar, galat)

    keluaran: dict[str, str] = {}
    versi_kartu: dict[str, str] = {}
    for path, meta, badan in kartu:
        if galat:
            break
        versi = hashlib.sha256(badan.encode("utf-8")).hexdigest()[:8]
        isi_sidecar, ukuran = sidecar(meta, versi)
        if ukuran >= BATAS_METADATA_BYTE:
            galat.append(f"{path.name}: metadata kustom {ukuran} byte, batas {BATAS_METADATA_BYTE}")
        keluaran[path.name] = badan
        keluaran[path.name + ".metadata.json"] = isi_sidecar
        versi_kartu[str(meta["sop_id"])] = versi

    if DIST.exists():
        asing = sorted(p.name for p in DIST.iterdir() if p.name not in keluaran)
        if asing and not galat:
            galat.append("dist/ berisi file yang tidak dihasilkan build ini. Hapus dulu dengan persetujuan "
                         f"Aldian: {', '.join(asing)}")

    for pesan in peringatan:
        print(f"PERINGATAN  {pesan}")
    for pesan in galat:
        print(f"GALAT       {pesan}")
    panjang = [len(b) for _, _, b in kartu]
    if panjang:
        print(f"{len(kartu)} kartu, karakter min {min(panjang)}, median {int(statistics.median(panjang))}, "
              f"maks {max(panjang)}, anggaran {ANGGARAN_KARAKTER}")
    print(f"Penjaga bocor membaca {jumlah_soal} soal dari {EVAL.name}/*.json")
    if galat:
        print(f"VONIS: GAGAL, {len(galat)} galat. dist/ tidak ditulis.")
        return 1
    if args.cek:
        print("VONIS: LOLOS (cek saja, dist/ tidak ditulis)")
        return 0

    DIST.mkdir(exist_ok=True)
    berubah = [n for n, isi in sorted(keluaran.items()) if tulis_jika_berubah(DIST / n, isi)]
    pengaduk = hashlib.sha256()
    for n in sorted(keluaran):
        pengaduk.update(n.encode("utf-8") + b"\0" + keluaran[n].encode("utf-8") + b"\0")
    STATE.mkdir(exist_ok=True)
    catatan = {"korpus": pengaduk.hexdigest()[:16], "mode": "parsial" if args.parsial else "ketat",
               "waktu": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kartu": versi_kartu}
    (STATE / "build.json").write_text(json.dumps(catatan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"VONIS: LOLOS. Mode {catatan['mode']}, korpus {catatan['korpus']}, {len(berubah)} file dist berubah.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
