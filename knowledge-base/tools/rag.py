#!/usr/bin/env python
"""RAG manual SOP AMIGA: kartu dari S3, chunk, embedding Titan, cosine similarity, jawaban bersitasi.

Tidak memakai Knowledge Base. Tiap pertanyaan menjalankan alur ini:
1. Ambil semua kartu .md di akar bucket AWS_BUCKET yang frontmatter-nya punya sop_id. Berkas lain dilewati.
   Dengan --lokal, kartu dibaca dari folder knowledge-base/sop/. Izin S3 student_9 dicabut 14 Okt 2026.
2. Potong tiap kartu per bagian berlabel tebal, lalu gabungkan sampai BATAS_CHUNK karakter.
3. Embedding tiap chunk dengan BEDROCK_EMBED_MODEL_ID. Vektor disimpan di .state/rag/ menurut hash isinya,
   jadi chunk hanya di-embed ulang kalau isinya berubah.
4. Cosine similarity pertanyaan dengan semua chunk. Peringkatnya digabung dengan skor kata (cosine TF-IDF
   potongan huruf) lewat reciprocal rank fusion, lalu ambil JUMLAH_CHUNK teratas.
5. Kartu utuh dari chunk teratas jadi konteks Converse BEDROCK_MODEL_ID, dengan prompt sistem kb.py.
6. Sitasi [sop_id] dicek ke kartu konteks, lalu dicetak sebagai referensi lengkap dengan lokasi S3.

Titan Embeddings tidak tersedia di ap-southeast-1 (list_foundation_models, 13 Okt 2026), jadi dipanggil di
us-east-1. Model jawaban tetap di ap-southeast-1.

Perintah:
  rag.py cari "<pertanyaan>"    retrieval saja, tanpa model jawaban
  rag.py jawab "<pertanyaan>"   jawaban lengkap dengan referensi
  rag.py --lokal jawab "..."    sama, tetapi kartu dari knowledge-base/sop/
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

import kb

CACHE = kb.STATE / "rag"
BATAS_CHUNK = 900
JUMLAH_CHUNK = 5
RRF_K = 60
DIMENSI_TITAN = 1024
REGION_EMBEDDING = "us-east-1"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
LABEL = re.compile(r"\*\*([^*\n]+?)\.?\*\*")
SOP_LOKAL = Path(__file__).resolve().parent.parent / "sop"
# "s3" membaca akar bucket sesuai rancangan awal. "lokal" membaca SOP_LOKAL, dipakai app dan opsi --lokal.
SUMBER_KARTU = "s3"
# Detik kartu disimpan di memori. CLI memakai 0; app mengisinya supaya tiap pertanyaan tidak memuat ulang kartu.
CACHE_KARTU_DETIK = 0
_CACHE_KARTU = None


def uraikan_frontmatter(teks: str) -> tuple[dict, str]:
    """Pisahkan frontmatter `kunci: nilai` dari badan kartu. Tanpa frontmatter, metanya kosong."""
    cocok = FRONTMATTER.match(teks)
    if not cocok:
        return {}, teks
    meta = {}
    for baris in cocok.group(1).splitlines():
        kunci, pemisah, nilai = baris.partition(":")
        if pemisah:
            meta[kunci.strip()] = nilai.strip()
    return meta, teks[cocok.end():]


def sumber_kartu() -> str:
    return "knowledge-base/sop/" if SUMBER_KARTU == "lokal" else f"s3://{kb.env_aktif().bucket}/"


def muat_kartu() -> tuple[list[dict], list[str]]:
    """Semua kartu ber-sop_id dari SUMBER_KARTU. Tanpa cache, dibaca ulang tiap dipanggil. Berkas lain dilaporkan."""
    global _CACHE_KARTU
    if CACHE_KARTU_DETIK and _CACHE_KARTU and time.monotonic() - _CACHE_KARTU[0] < CACHE_KARTU_DETIK:
        return _CACHE_KARTU[1]
    if SUMBER_KARTU == "lokal":
        data = {p.name: p.read_bytes() for p in SOP_LOKAL.glob("*.md")}
    else:
        e = kb.env_aktif()
        s3 = kb.klien("s3")
        kunci = [o["Key"] for halaman in s3.get_paginator("list_objects_v2").paginate(Bucket=e.bucket, Delimiter="/")
                 for o in halaman.get("Contents", []) if o["Key"].lower().endswith(".md")]

        def satu(k: str):
            return k, s3.get_object(Bucket=e.bucket, Key=k)["Body"].read()

        with ThreadPoolExecutor(max_workers=8) as pelaksana:
            data = dict(pelaksana.map(satu, kunci))
    kartu, lewat = [], []
    for k in sorted(data):
        try:
            teks = data[k].decode("utf-8-sig").replace("\r\n", "\n")
        except UnicodeDecodeError:
            lewat.append(k)
            continue
        meta, badan = uraikan_frontmatter(teks)
        if not meta.get("sop_id"):
            lewat.append(k)
            continue
        badan = badan.strip()
        judul = next((b[2:].strip() for b in badan.splitlines() if b.startswith("# ")), meta["sop_id"])
        kartu.append({"sop_id": meta["sop_id"], "kategori": meta.get("kategori"), "kode": meta.get("kode"),
                      "status_aturan": meta.get("status_aturan"), "peran": meta.get("peran"), "judul": judul,
                      "teks": badan, "kunci": k})
    ganda = sorted(s for s, n in Counter(k["sop_id"] for k in kartu).items() if n > 1)
    if ganda:
        raise kb.GalatKB(f"sop_id ganda di {sumber_kartu()}: {', '.join(ganda)}.")
    if not kartu:
        raise kb.GalatKB(f"Tidak ada kartu ber-frontmatter sop_id di {sumber_kartu()}.")
    _CACHE_KARTU = (time.monotonic(), (kartu, lewat))
    return kartu, lewat


def bagian_kartu(badan: str) -> list[tuple[str, str]]:
    """Pecah badan kartu jadi (label, teks). Bagian baru dimulai di baris yang diawali label tebal."""
    baris_kartu = badan.splitlines()
    if baris_kartu and baris_kartu[0].startswith("# "):
        baris_kartu = baris_kartu[1:]
    bagian, label, isi = [], "Pembuka", []
    for baris in baris_kartu:
        cocok = LABEL.match(baris)
        if cocok:
            if "\n".join(isi).strip():
                bagian.append((label, "\n".join(isi).strip()))
            label, isi = cocok.group(1).strip(), []
        isi.append(baris)
    if "\n".join(isi).strip():
        bagian.append((label, "\n".join(isi).strip()))
    return bagian


def potong(kartu: dict) -> list[dict]:
    """Chunk satu kartu. Bagian berurutan digabung sampai BATAS_CHUNK karakter, bagian yang lebih panjang
    dipecah per baris. Tiap chunk diawali sop_id dan judul kartu supaya konteksnya tidak hilang."""
    potongan = []
    for label, teks in bagian_kartu(kartu["teks"]):
        isi = []
        for baris in teks.splitlines():
            if isi and len("\n".join(isi + [baris])) > BATAS_CHUNK:
                potongan.append(([label], "\n".join(isi).strip()))
                isi = []
            isi.append(baris)
        potongan.append(([label], "\n".join(isi).strip()))
    gabung = []
    for label, teks in potongan:
        if not teks:
            continue
        if gabung and len(gabung[-1][1]) + 2 + len(teks) <= BATAS_CHUNK:
            gabung[-1] = (gabung[-1][0] + [l for l in label if l not in gabung[-1][0]], gabung[-1][1] + "\n\n" + teks)
        else:
            gabung.append((label, teks))
    kepala = f"{kartu['sop_id']} | {kartu['judul']}"
    return [{"sop_id": kartu["sop_id"], "judul": kartu["judul"], "kunci": kartu["kunci"], "bagian": label,
             "isi": teks, "teks": f"{kepala}\n{teks}"} for label, teks in gabung]


def wajib_titan(model: str) -> None:
    if not model.startswith("amazon.titan-embed-text"):
        raise kb.GalatKB(f"rag.py hanya mendukung embedding Titan Text, sedangkan BEDROCK_EMBED_MODEL_ID berisi {model}.")


_KLIEN_EMBEDDING: dict = {}


def klien_embedding():
    # Dipakai ulang per sesi: embedding pertanyaan turun dari 1,9 ke 0,7 detik saat koneksi us-east-1 tidak dibuka
    # ulang (diukur 14 Okt 2026).
    kunci = id(kb.sesi())
    if kunci not in _KLIEN_EMBEDDING:
        _KLIEN_EMBEDDING[kunci] = kb.sesi().client("bedrock-runtime", region_name=REGION_EMBEDDING,
                                                   config=kb.KONFIG_KLIEN)
    return _KLIEN_EMBEDDING[kunci]


def embed(runtime, model: str, teks: str) -> tuple[list[float], int]:
    """Satu teks per panggilan, sesuai API Titan. V2 memakai 1024 dimensi yang dinormalisasi."""
    badan = {"inputText": teks}
    if model.startswith("amazon.titan-embed-text-v2"):
        badan.update({"dimensions": DIMENSI_TITAN, "normalize": True})
    respons = runtime.invoke_model(modelId=model, body=json.dumps(badan), contentType="application/json",
                                   accept="application/json")
    hasil = json.loads(respons["body"].read())
    return hasil["embedding"], hasil.get("inputTextTokenCount", 0)


def berkas_cache(model: str) -> Path:
    return CACHE / (re.sub(r"[^A-Za-z0-9_.-]", "_", model) + ".json")


def kunci_cache(model: str, teks: str) -> str:
    return hashlib.sha256(f"{model}|{DIMENSI_TITAN}|{teks}".encode("utf-8")).hexdigest()


def vektor_chunk(runtime, model: str, chunk: list[dict]) -> tuple[list[list[float]], int, int]:
    """Vektor semua chunk. Hanya chunk yang belum ada di cache yang dikirim ke model.
    Hasilnya vektor, jumlah chunk baru, dan token embedding."""
    berkas = berkas_cache(model)
    try:
        cache = kb.baca_json(berkas, {})
    except ValueError:
        cache = {}
    kunci = [kunci_cache(model, c["teks"]) for c in chunk]
    baru = {k: c["teks"] for k, c in zip(kunci, chunk) if k not in cache}
    token = 0
    if baru:
        with ThreadPoolExecutor(max_workers=4) as pelaksana:
            hasil = list(pelaksana.map(lambda item: (item[0], embed(runtime, model, item[1])), baru.items()))
        for k, (vektor, jumlah_token) in hasil:
            cache[k] = [round(x, 6) for x in vektor]
            token += jumlah_token
        CACHE.mkdir(parents=True, exist_ok=True)
        sementara = berkas.with_suffix(".json.tmp")
        sementara.write_text(json.dumps({k: cache[k] for k in kunci}), encoding="utf-8")
        os.replace(sementara, berkas)
    return [cache[k] for k in kunci], len(baru), token


def cosine(a: list[float], b: list[float]) -> float:
    titik = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return titik / norma if norma else 0.0


def ngram(teks: str) -> Counter:
    """Potongan 3 sampai 5 huruf per kata, supaya kata berimbuhan seperti pengunggah dan unggah tetap bertemu."""
    hasil = Counter()
    for kata in re.findall(r"\w+", teks.lower()):
        kata = f" {kata} "
        for n in (3, 4, 5):
            hasil.update(kata[i:i + n] for i in range(len(kata) - n + 1))
    return hasil


def skor_kata(chunk: list[dict], pertanyaan: str) -> list[float]:
    """Cosine TF-IDF potongan huruf antara pertanyaan dan tiap chunk. Tanpa model, dihitung ulang tiap pertanyaan."""
    dokumen = [ngram(c["teks"]) for c in chunk]
    df = Counter(t for d in dokumen for t in d)
    idf = {t: math.log((1 + len(dokumen)) / (1 + n)) + 1 for t, n in df.items()}

    def vektor(c: Counter) -> dict:
        v = {t: (1 + math.log(f)) * idf[t] for t, f in c.items() if t in idf}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norma for t, x in v.items()}

    tanya = vektor(ngram(pertanyaan))
    return [sum(x * d.get(t, 0.0) for t, x in tanya.items()) for d in map(vektor, dokumen)]


def gabung_peringkat(*daftar_skor: list[float]) -> list[float]:
    """Reciprocal rank fusion: tiap daftar skor menyumbang 1 / (RRF_K + peringkat) untuk tiap chunk."""
    total = [0.0] * len(daftar_skor[0])
    for skor in daftar_skor:
        for peringkat, i in enumerate(sorted(range(len(skor)), key=lambda i: -skor[i]), 1):
            total[i] += 1 / (RRF_K + peringkat)
    return total


def _cari(pertanyaan: str, jumlah: int) -> tuple[dict, dict]:
    pertanyaan = (pertanyaan or "").strip()
    if not pertanyaan:
        raise kb.GalatKB("Pertanyaan kosong.")
    if jumlah < 1:
        raise kb.GalatKB("Jumlah chunk minimal 1.")
    e = kb.env_aktif()
    wajib_titan(e.embed_model)
    kartu, lewat = muat_kartu()
    chunk = [c for k in kartu for c in potong(k)]
    runtime = klien_embedding()
    vektor, baru, token = vektor_chunk(runtime, e.embed_model, chunk)
    vektor_tanya, token_tanya = embed(runtime, e.embed_model, pertanyaan)
    kemiripan = [cosine(vektor_tanya, v) for v in vektor]
    kata = skor_kata(chunk, pertanyaan)
    gabungan = gabung_peringkat(kemiripan, kata)
    urut = sorted(range(len(chunk)), key=lambda i: -gabungan[i])[:jumlah]
    hasil = [{"sop_id": chunk[i]["sop_id"], "judul": chunk[i]["judul"], "bagian": chunk[i]["bagian"],
              "skor": round(kemiripan[i], 4), "skor_kata": round(kata[i], 4),
              "lokasi": sumber_kartu() + chunk[i]["kunci"], "isi": chunk[i]["isi"]} for i in urut]
    return ({"pertanyaan": pertanyaan, "embedding": e.embed_model, "region_embedding": REGION_EMBEDDING,
             "sumber_kartu": sumber_kartu(), "kartu_dibaca": len(kartu), "dilewati": lewat, "chunk": len(chunk),
             "chunk_baru": baru, "token_embedding": token + token_tanya, "hasil": hasil},
            {k["sop_id"]: k for k in kartu})


def cari(pertanyaan: str, jumlah: int = JUMLAH_CHUNK) -> dict:
    """Retrieval saja, untuk CLI dan app: chunk teratas beserta skor cosine, skor kata, dan lokasi S3."""
    return _cari(pertanyaan, jumlah)[0]


def jawab(pertanyaan: str, jumlah: int = JUMLAH_CHUNK) -> dict:
    """Jawaban dari kartu hasil retrieval, untuk CLI dan app. Hanya panduan, tidak mengubah data apa pun."""
    hasil, per_id = _cari(pertanyaan, jumlah)
    konteks = list(dict.fromkeys(h["sop_id"] for h in hasil["hasil"]))
    model = kb.panggil_model(kb.SISTEM, kb.susun_prompt([per_id[s] for s in konteks], hasil["pertanyaan"]))
    teks = model["teks"]
    tanpa_sop = teks.startswith(kb.TANPA_SOP[:-1])
    if tanpa_sop:
        teks = kb.TANPA_SOP
    sitasi = kb.periksa_sitasi(teks, konteks)
    referensi = []
    for s in sitasi["sah"]:
        cocok = [h for h in hasil["hasil"] if h["sop_id"] == s]
        referensi.append({"sop_id": s, "judul": per_id[s]["judul"],
                          "bagian": list(dict.fromkeys(b for h in cocok for b in h["bagian"])),
                          "skor": max(h["skor"] for h in cocok), "skor_kata": max(h["skor_kata"] for h in cocok),
                          "lokasi": cocok[0]["lokasi"]})
    peringatan = []
    if model["stop"] != "end_turn":
        peringatan.append(f"stopReason {model['stop']}, jawaban mungkin terpotong")
    if sitasi["ejaan"]:
        peringatan.append(f"sitasi salah ejaan: {', '.join(sitasi['ejaan'])}")
    if sitasi["asing"]:
        peringatan.append(f"sitasi di luar kartu konteks: {', '.join(sitasi['asing'])}")
    if not tanpa_sop and not sitasi["sah"]:
        peringatan.append("jawaban tanpa sitasi kartu")
    hasil.update({"model": kb.env_aktif().model, "konteks": konteks, "jawaban": teks,
                  "dirapikan": teks != model["teks"], "referensi": referensi, "token_masuk": model["token_masuk"],
                  "token_keluar": model["token_keluar"], "latensi_ms": model["latensi_ms"], "stop": model["stop"],
                  "peringatan": peringatan})
    return hasil


def cetak_kepala(h: dict) -> None:
    print(f"RAG MANUAL: embedding {h['embedding']} di {h['region_embedding']}. Peringkat gabungan cosine similarity "
          f"dan skor kata atas {h['chunk']} chunk dari {h['kartu_dibaca']} kartu di {h['sumber_kartu']}.")
    if h["dilewati"]:
        print(f"Dilewati karena tanpa frontmatter sop_id: {', '.join(h['dilewati'])}.")
    if h["chunk_baru"]:
        print(f"Chunk baru di-embed: {h['chunk_baru']}. Sisanya dari cache.")


def perintah_cari(args) -> int:
    h = cari(args.pertanyaan, args.n)
    cetak_kepala(h)
    print()
    for urutan, x in enumerate(h["hasil"], 1):
        print(f"{urutan}. cosine {x['skor']:.4f}, kata {x['skor_kata']:.4f}  {x['sop_id']}  "
              f"bagian {', '.join(x['bagian'])}")
        print("   " + " ".join(x["isi"].split())[:200])
    print(f"\nToken embedding: {h['token_embedding']}.")
    return 0


def perintah_jawab(args) -> int:
    h = jawab(args.pertanyaan, args.n)
    cetak_kepala(h)
    print()
    print(h["jawaban"])
    print("\nReferensi:")
    for urutan, r in enumerate(h["referensi"], 1):
        print(f"{urutan}. [{r['sop_id']}] {r['judul']}")
        print(f"   bagian {', '.join(r['bagian'])}, cosine {r['skor']:.4f}, kata {r['skor_kata']:.4f}, {r['lokasi']}")
    if not h["referensi"]:
        print("-")
    terbaik = {}
    for x in h["hasil"]:
        terbaik.setdefault(x["sop_id"], x["skor"])
    print("\nKonteks yang dikirim, dengan cosine terbaik: " + ", ".join(f"{s} {v:.3f}" for s, v in terbaik.items()))
    print(f"Token: embedding {h['token_embedding']}, model masuk {h['token_masuk']}, keluar {h['token_keluar']}. "
          f"Latensi model {h['latensi_ms']} ms, stopReason {h['stop']}.")
    for p in h["peringatan"]:
        print(f"PERINGATAN: {p}")
    return 1 if h["peringatan"] else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=kb.DOTENV, help="file .env (default .env di folder hackthon)")
    parser.add_argument("--lokal", action="store_true", help="baca kartu dari knowledge-base/sop, bukan akar bucket S3")
    sub = parser.add_subparsers(dest="perintah", required=True)
    for nama, fungsi, bantuan in (("cari", perintah_cari, "chunk teratas dan skornya, tanpa model jawaban"),
                                  ("jawab", perintah_jawab, "jawaban BEDROCK_MODEL_ID dengan referensi kartu")):
        p = sub.add_parser(nama, help=bantuan)
        p.add_argument("pertanyaan")
        p.add_argument("-n", type=int, default=JUMLAH_CHUNK, help=f"jumlah chunk teratas (default {JUMLAH_CHUNK})")
        p.set_defaults(fungsi=fungsi)
    args = parser.parse_args()
    if args.lokal:
        global SUMBER_KARTU
        SUMBER_KARTU = "lokal"
    try:
        kb.muat_env(args.env)
        return args.fungsi(args)
    except kb.GalatKB as error:
        print(f"BERHENTI: {error}")
        return 1
    except ClientError as error:
        permintaan = error.response.get("ResponseMetadata", {}).get("RequestId")
        print(f"AWS menolak: {kb.kode_error(error)}: {kb.pesan_error(error)} (request ID {permintaan})")
        return 1
    except BotoCoreError as error:
        print(f"AWS gagal: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
