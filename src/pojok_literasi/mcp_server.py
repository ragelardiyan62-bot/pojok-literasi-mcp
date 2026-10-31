"""MCP server Pojok Literasi: tool tingkat tinggi di atas Notion.

Setiap tool mengembalikan teks ringkas (bukan JSON mentah Notion) supaya hemat token.
"""

from __future__ import annotations

import re
import time
from typing import Literal

from pydantic import BaseModel, Field
from mcp.server.mcpserver import MCPServer

from . import anti_ai
from .notion import (Konfigurasi, Notion, ambil, p_judul, p_multi, p_pilih, p_relasi,
                     p_status, p_tanggal, p_teks, paragraf)

INSTRUKSI = """Server ini mengelola sistem konten Instagram 'Pojok Literasi' di Notion.
Alur kerja:
1. Saat user membaca: catat_reaksi (reaksi/kutipan/cerita pribadi, kata-kata user apa adanya).
2. Cari ide: bahan_buku -> usulkan ide dengan 8 sudut -> simpan_ide.
3. Menulis: pakai prompt 'wawancara' atau tanya user satu per satu. JANGAN mengarang
   pengalaman user. Panggil panduan_suara sekali per sesi sebelum menulis.
4. simpan_naskah otomatis menjalankan cek_anti_ai; perbaiki temuan 'merah' bersama user.
Ide dirujuk dengan kode seperti IDE-12, buku dengan judulnya."""

mcp = MCPServer("pojok-literasi", instructions=INSTRUKSI)

SUDUT = Literal[
    "Kalimat yang Mengubah Pikiranku", "Yang Aku Tidak Setuju", "Cocok untuk Kamu yang...",
    "Sebelum vs Sesudah Baca", "Detail yang Jarang Dibahas", "Kalau Suka X Baca Ini",
    "Momen Hidupku yang Nyambung", "Ekspektasi vs Kenyataan",
]
STATUS_BUKU = Literal["Mau Dibaca", "Sedang Dibaca", "Selesai", "Berhenti"]
STATUS_IDE = Literal["Ide", "Wawancara", "Draft", "Siap", "Posted"]
FORMAT = Literal["Carousel", "Reels", "Single Post", "Story"]
JENIS = Literal["Kutipan", "Reaksi", "Cerita Pribadi"]

_cfg: Konfigurasi | None = None
_notion: Notion | None = None
_cache_panduan: tuple[float, str] | None = None


def _n() -> tuple[Konfigurasi, Notion]:
    global _cfg, _notion
    if _cfg is None:
        _cfg = Konfigurasi()
        _notion = Notion(_cfg.token)
    assert _notion is not None
    return _cfg, _notion


async def _cari_buku(judul: str) -> dict:
    cfg, n = _n()
    hasil = await n.query(cfg.db_buku, {"property": "Judul", "title": {"contains": judul}}, batas=5)
    if not hasil:
        raise ValueError(f"Buku '{judul}' tidak ditemukan. Tambahkan dulu dengan tambah_buku.")
    persis = [h for h in hasil if ambil(h, "Judul").lower() == judul.lower()]
    if len(persis) == 1:
        return persis[0]
    if len(hasil) > 1:
        daftar = ", ".join(ambil(h, "Judul") for h in hasil)
        raise ValueError(f"Judul '{judul}' ambigu: {daftar}. Sebutkan lebih lengkap.")
    return hasil[0]


def _nomor(kode: str | int) -> int:
    m = re.search(r"\d+", str(kode))
    if not m:
        raise ValueError(f"Kode ide '{kode}' tidak valid (contoh: IDE-12).")
    return int(m.group())


async def _cari_ide(kode: str | int) -> dict:
    cfg, n = _n()
    hasil = await n.query(cfg.db_ide, {"property": "Kode", "unique_id": {"equals": _nomor(kode)}}, batas=1)
    if not hasil:
        raise ValueError(f"Ide {kode} tidak ditemukan.")
    return hasil[0]


async def _judul_halaman(ids: list[str]) -> list[str]:
    _, n = _n()
    out = []
    for i in ids:
        h = await n._req("GET", f"/pages/{i}")
        judul = next((ambil(h, k) for k, v in h["properties"].items() if v["type"] == "title"), "")
        out.append(judul)
    return out


# ---------------- Buku ----------------

@mcp.tool()
async def tambah_buku(judul: str, penulis: str = "", status: STATUS_BUKU = "Mau Dibaca",
                      genre: list[str] | None = None) -> str:
    """Tambah buku ke rak. Genre bebas, mis. Fiksi, Nonfiksi, Self-Improvement, Sastra Indonesia."""
    cfg, n = _n()
    prop = {"Judul": p_judul(judul), "Status": p_status(status)}
    if penulis:
        prop["Penulis"] = p_teks(penulis)
    if genre:
        prop["Genre"] = p_multi(genre)
    await n.buat(cfg.db_buku, prop)
    return f"Buku '{judul}' ditambahkan ({status})."


@mcp.tool()
async def update_buku(judul: str, status: STATUS_BUKU | None = None, rating: int | None = None,
                      kesan_singkat: str | None = None, tanggal_selesai: str | None = None) -> str:
    """Ubah status/rating(1-5)/kesan singkat/tanggal selesai (YYYY-MM-DD) sebuah buku."""
    _, n = _n()
    b = await _cari_buku(judul)
    prop: dict = {}
    if status:
        prop["Status"] = p_status(status)
    if rating is not None:
        prop["Rating"] = p_pilih(str(max(1, min(5, rating))))
    if kesan_singkat is not None:
        prop["Kesan Singkat"] = p_teks(kesan_singkat)
    if tanggal_selesai:
        prop["Selesai Dibaca"] = p_tanggal(tanggal_selesai)
    if not prop:
        return "Tidak ada yang diubah."
    await n.ubah(b["id"], prop)
    return f"'{ambil(b, 'Judul')}' diperbarui: {', '.join(prop)}."


@mcp.tool()
async def daftar_buku(status: STATUS_BUKU | None = None) -> str:
    """Daftar buku (opsional difilter status)."""
    cfg, n = _n()
    f = {"property": "Status", "status": {"equals": status}} if status else None
    hasil = await n.query(cfg.db_buku, f, batas=100)
    if not hasil:
        return "Rak masih kosong."
    return "\n".join(
        f"- {ambil(h, 'Judul')} | {ambil(h, 'Penulis') or '?'} | {ambil(h, 'Status')}"
        + (f" | ★{ambil(h, 'Rating')}" if ambil(h, "Rating") else "")
        for h in hasil
    )


# ---------------- Reaksi & Kutipan ----------------

@mcp.tool()
async def catat_reaksi(judul_buku: str, isi: str, jenis: JENIS = "Reaksi",
                       halaman_atau_bab: str = "", tema: list[str] | None = None) -> str:
    """Simpan reaksi/kutipan/cerita pribadi saat membaca. Simpan kata-kata user APA ADANYA."""
    cfg, n = _n()
    b = await _cari_buku(judul_buku)
    prop = {"Isi": p_judul(isi), "Jenis": p_pilih(jenis), "Buku": p_relasi([b["id"]])}
    if halaman_atau_bab:
        prop["Halaman/Bab"] = p_teks(halaman_atau_bab)
    if tema:
        prop["Tema"] = p_multi(tema)
    await n.buat(cfg.db_reaksi, prop)
    return f"{jenis} untuk '{ambil(b, 'Judul')}' tersimpan."


@mcp.tool()
async def bahan_buku(judul_buku: str, hanya_belum_dipakai: bool = False) -> str:
    """Semua bahan mentah satu buku (kesan + reaksi + kutipan) dalam format ringkas. Pakai ini untuk mencari ide."""
    cfg, n = _n()
    b = await _cari_buku(judul_buku)
    f: dict = {"property": "Buku", "relation": {"contains": b["id"]}}
    if hanya_belum_dipakai:
        f = {"and": [f, {"property": "Dipakai", "checkbox": {"equals": False}}]}
    reaksi = await n.query(cfg.db_reaksi, f, sorts=[{"timestamp": "created_time", "direction": "ascending"}], batas=100)
    kepala = (f"BUKU: {ambil(b, 'Judul')} - {ambil(b, 'Penulis') or '?'} | {ambil(b, 'Status')}"
              f" | rating {ambil(b, 'Rating') or '-'}\nKesan: {ambil(b, 'Kesan Singkat') or '-'}")
    if not reaksi:
        return kepala + "\n(Belum ada reaksi/kutipan. Ajak user bercerita dulu.)"
    baris = []
    for r in reaksi:
        lok = ambil(r, "Halaman/Bab")
        tanda = " ✓dipakai" if ambil(r, "Dipakai") else ""
        baris.append(f"- [{ambil(r, 'Jenis')}{', ' + lok if lok else ''}{tanda}] {ambil(r, 'Isi')} (id:{r['id'][:8]})")
    return kepala + "\n" + "\n".join(baris)


# ---------------- Ide Konten ----------------

class IdeBaru(BaseModel):
    ide: str = Field(description="Judul ide, singkat")
    sudut: SUDUT
    format: FORMAT = "Carousel"
    hook: str = Field("", description="Kalimat pembuka, sebaiknya dari kata-kata user sendiri")


@mcp.tool()
async def simpan_ide(judul_buku: str, ide: list[IdeBaru]) -> str:
    """Simpan satu atau beberapa ide konten untuk sebuah buku (status awal 'Ide')."""
    cfg, n = _n()
    b = await _cari_buku(judul_buku)
    kode = []
    for i in ide:
        prop = {"Ide": p_judul(i.ide), "Sudut": p_pilih(i.sudut), "Format": p_pilih(i.format),
                "Buku": p_relasi([b["id"]]), "Status": p_status("Ide")}
        if i.hook:
            prop["Hook"] = p_teks(i.hook)
        h = await n.buat(cfg.db_ide, prop)
        kode.append(f"{ambil(h, 'Kode')}: {i.ide}")
    return "Tersimpan:\n" + "\n".join(f"- {k}" for k in kode)


@mcp.tool()
async def daftar_ide(status: STATUS_IDE | None = None, batas: int = 20) -> str:
    """Daftar ide konten (opsional per status), terbaru dulu."""
    cfg, n = _n()
    f = {"property": "Status", "status": {"equals": status}} if status else None
    hasil = await n.query(cfg.db_ide, f, sorts=[{"timestamp": "last_edited_time", "direction": "descending"}],
                          batas=batas)
    if not hasil:
        return "Belum ada ide" + (f" berstatus {status}." if status else ".")
    out = []
    for h in hasil:
        jadwal = ambil(h, "Jadwal Posting")
        out.append(f"- {ambil(h, 'Kode')} [{ambil(h, 'Status')}] {ambil(h, 'Ide')} | {ambil(h, 'Sudut') or '-'}"
                   f" | {ambil(h, 'Format') or '-'}" + (f" | jadwal {jadwal}" if jadwal else ""))
    return "\n".join(out)


@mcp.tool()
async def lihat_ide(kode: str) -> str:
    """Detail satu ide: sudut, hook, buku, bahan terkait, dan naskah yang sudah ada."""
    _, n = _n()
    h = await _cari_ide(kode)
    buku = await _judul_halaman(ambil(h, "Buku") or [])
    bahan = await _judul_halaman(ambil(h, "Bahan") or [])
    naskah = await n.teks_halaman(h["id"])
    bag = [
        f"{ambil(h, 'Kode')} [{ambil(h, 'Status')}] {ambil(h, 'Ide')}",
        f"Buku: {', '.join(buku) or '-'} | Sudut: {ambil(h, 'Sudut') or '-'} | Format: {ambil(h, 'Format') or '-'}",
        f"Hook: {ambil(h, 'Hook') or '-'}",
    ]
    if bahan:
        bag.append("Bahan:\n" + "\n".join(f"- {x}" for x in bahan))
    bag.append("Naskah:\n" + (naskah or "(belum ada)"))
    return "\n".join(bag)


@mcp.tool()
async def simpan_naskah(kode: str, naskah: str, id_bahan_dipakai: list[str] | None = None) -> str:
    """Simpan/ganti naskah sebuah ide, status jadi 'Draft', lalu jalankan cek_anti_ai otomatis.
    id_bahan_dipakai: id (8 karakter pertama juga boleh) reaksi/kutipan dari bahan_buku yang dipakai."""
    cfg, n = _n()
    h = await _cari_ide(kode)
    await n.hapus_isi(h["id"])
    await n.tambah_blok(h["id"], paragraf(naskah))
    prop: dict = {"Status": p_status("Draft")}
    if id_bahan_dipakai:
        ids = await _lengkapi_id_bahan(h, id_bahan_dipakai)
        prop["Bahan"] = p_relasi(list(dict.fromkeys((ambil(h, "Bahan") or []) + ids)))
        for i in ids:
            await n.ubah(i, {"Dipakai": {"checkbox": True}})
    await n.ubah(h["id"], prop)
    return f"Naskah {ambil(h, 'Kode')} tersimpan (Draft).\n\nCek anti-AI:\n" + anti_ai.ringkas(anti_ai.periksa(naskah))


async def _lengkapi_id_bahan(ide: dict, potongan: list[str]) -> list[str]:
    """Terima id penuh atau 8 karakter pertama; cocokkan dengan reaksi milik buku ide ini."""
    cfg, n = _n()
    penuh = [p for p in potongan if len(p.replace("-", "")) == 32]
    pendek = [p for p in potongan if p not in penuh]
    if pendek:
        kandidat: list[dict] = []
        for buku_id in ambil(ide, "Buku") or []:
            kandidat += await n.query(cfg.db_reaksi, {"property": "Buku", "relation": {"contains": buku_id}}, batas=100)
        for p in pendek:
            cocok = [k["id"] for k in kandidat if k["id"].startswith(p)]
            if not cocok:
                raise ValueError(f"Bahan dengan id '{p}' tidak ditemukan pada buku ide ini.")
            penuh.append(cocok[0])
    return penuh


@mcp.tool()
async def ubah_status_ide(kode: str, status: STATUS_IDE, jadwal_posting: str | None = None) -> str:
    """Pindahkan ide di pipeline. jadwal_posting format YYYY-MM-DD (opsional)."""
    _, n = _n()
    h = await _cari_ide(kode)
    prop = {"Status": p_status(status)}
    if jadwal_posting:
        prop["Jadwal Posting"] = p_tanggal(jadwal_posting)
    await n.ubah(h["id"], prop)
    return f"{ambil(h, 'Kode')} -> {status}" + (f", jadwal {jadwal_posting}" if jadwal_posting else "")


# ---------------- Pertanyaan audiens ----------------

@mcp.tool()
async def catat_pertanyaan(pertanyaan: str, sumber: Literal["Komentar", "DM", "Story"] = "Komentar") -> str:
    """Catat pertanyaan/request dari audiens."""
    cfg, n = _n()
    await n.buat(cfg.db_pertanyaan, {"Pertanyaan": p_judul(pertanyaan), "Sumber": p_pilih(sumber)})
    return "Pertanyaan tersimpan."


@mcp.tool()
async def pertanyaan_terbuka() -> str:
    """Pertanyaan audiens yang belum dijawab jadi konten."""
    cfg, n = _n()
    hasil = await n.query(cfg.db_pertanyaan, {"property": "Sudah Dijawab", "checkbox": {"equals": False}}, batas=50)
    if not hasil:
        return "Tidak ada pertanyaan terbuka."
    return "\n".join(f"- [{ambil(h, 'Sumber') or '?'}] {ambil(h, 'Pertanyaan')}" for h in hasil)


# ---------------- Gaya & kualitas ----------------

@mcp.tool()
async def panduan_suara() -> str:
    """Panduan gaya bahasa user. Baca SEKALI per sesi sebelum menulis naskah."""
    global _cache_panduan
    if _cache_panduan and time.time() - _cache_panduan[0] < 600:
        return _cache_panduan[1]
    cfg, n = _n()
    teks = await n.teks_halaman(cfg.halaman_panduan)
    _cache_panduan = (time.time(), teks)
    return teks


@mcp.tool()
def cek_anti_ai(naskah: str) -> str:
    """Periksa naskah dari ciri tulisan AI (frasa klise, tanpa detail pribadi, dll). Lokal, tanpa token LLM."""
    return anti_ai.ringkas(anti_ai.periksa(naskah))


@mcp.prompt()
def wawancara(kode_ide: str) -> str:
    """Mode wawancara: AI menggali cerita user untuk satu ide, lalu menyusun naskah dari jawabannya."""
    return (
        f"Kita akan menulis naskah untuk ide {kode_ide}.\n"
        f"1. Panggil lihat_ide('{kode_ide}') dan panduan_suara().\n"
        "2. Panggil bahan_buku untuk buku terkait.\n"
        "3. Wawancarai aku SATU pertanyaan per giliran (maks 5), gali pengalaman, opini, "
        "dan momen spesifik. Jangan menulis naskah dulu.\n"
        "4. Susun naskah HANYA dari jawabanku + bahan yang ada. Pertahankan kata-kataku. "
        "Jangan mengarang pengalaman.\n"
        "5. simpan_naskah, lalu bahas temuan cek anti-AI denganku."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
