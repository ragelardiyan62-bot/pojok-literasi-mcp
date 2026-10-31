"""MCP server Pojok Literasi untuk Claude Desktop.

Semua tool mengembalikan teks ringkas agar hemat token. Saat dijalankan, server ini
juga menyalakan dashboard web lokal (lihat web.py) supaya kamu tidak perlu
menjalankan apa pun secara terpisah.
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import threading
from typing import Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from . import anti_ai
from .db import DB, GagalValidasi

INSTRUKSI = """Sistem konten Instagram 'Pojok Literasi' (data lokal milik user).
Mulai sesi dengan ringkasan_hari_ini. Kerjakan tugas_menunggu bila ada.
Aturan menulis: panggil konteks_ide (sudah berisi panduan suara) sebelum menulis naskah.
JANGAN pernah mengarang pengalaman/opini user; naskah hanya dari bahan dan jawaban user.
Kalau bahan kurang, wawancarai user (satu pertanyaan per giliran).
simpan_naskah menjalankan cek anti-AI; perbaiki temuan 'merah' bersama user.
Ubah panduan suara HANYA setelah user menyetujui usulanmu.
Setelah konten diposting, catat_performa. Pakai hook_terbukti untuk belajar pola hook yang berhasil.
Kode: buku B-1, ide IDE-1, tugas T-1, bahan #1."""

SUDUT = Literal[
    "Kalimat yang Mengubah Pikiranku", "Yang Aku Tidak Setuju", "Cocok untuk Kamu yang...",
    "Sebelum vs Sesudah Baca", "Detail yang Jarang Dibahas", "Kalau Suka X Baca Ini",
    "Momen Hidupku yang Nyambung", "Ekspektasi vs Kenyataan",
]
STATUS_BUKU = Literal["Mau Dibaca", "Sedang Dibaca", "Selesai", "Berhenti"]
STATUS_IDE = Literal["Ide", "Wawancara", "Draft", "Siap", "Posted"]
FORMAT = Literal["Carousel", "Reels", "Single Post", "Story"]
JENIS = Literal["Reaksi", "Kutipan", "Cerita Pribadi"]

mcp = MCPServer("pojok-literasi", instructions=INSTRUKSI)
_db: DB | None = None


def db() -> DB:
    global _db
    if _db is None:
        _db = DB()
    return _db


def _aman(fn):
    """Ubah error validasi jadi pesan biasa (bukan stack trace) supaya agent bisa memperbaiki."""
    import functools

    @functools.wraps(fn)
    def bungkus(*a, **kw):
        try:
            return fn(*a, **kw)
        except GagalValidasi as e:
            return f"GAGAL: {e}"
    return bungkus


def _f_buku(b: dict) -> str:
    rating = f" ★{b['rating']}" if b.get("rating") else ""
    return f"B-{b['id']} {b['judul']} | {b['penulis'] or '?'} | {b['status']}{rating}"


def _f_bahan(x: dict) -> str:
    lok = f", {x['lokasi']}" if x["lokasi"] else ""
    tema = f" #{' #'.join(x['tema'])}" if x["tema"] else ""
    pakai = " ✓" if x["dipakai"] else ""
    return f"#{x['id']} [{x['jenis']}{lok}{pakai}] {x['isi']}{tema}"


def _f_ide(i: dict) -> str:
    jadwal = f" | {i['jadwal']}" if i.get("jadwal") else ""
    buku = f" | {i['buku_judul']}" if i.get("buku_judul") else ""
    return f"IDE-{i['id']} [{i['status']}] {i['judul']} | {i['sudut'] or '-'} | {i['format']}{buku}{jadwal}"


# ---------------- Ringkasan & tugas ----------------

@mcp.tool()
@_aman
def ringkasan_hari_ini() -> str:
    """Kondisi terkini: buku yang dibaca, pipeline ide, jadwal 7 hari, draft mandek, tugas titipan user."""
    r = db().ringkasan()
    baris = ["Sedang dibaca: " + (", ".join(f"B-{b['id']} {b['judul']}" for b in r["sedang_dibaca"]) or "-"),
             "Ide: " + ", ".join(f"{k} {v}" for k, v in r["ide_per_status"].items()),
             f"Bahan belum dipakai: {r['bahan_belum_dipakai']} | Pertanyaan terbuka: {r['pertanyaan_terbuka']}"]
    if r["jadwal_sepekan"]:
        baris.append("Jadwal 7 hari:\n" + "\n".join(
            f"- {j['jadwal']} IDE-{j['id']} {j['judul']} [{j['status']}]" for j in r["jadwal_sepekan"]))
    if r["draft_mandek"]:
        baris.append("Mandek >7 hari: " + ", ".join(f"IDE-{d['id']} {d['judul']}" for d in r["draft_mandek"]))
    if r["posted_tanpa_angka"]:
        baris.append(f"{r['posted_tanpa_angka']} konten Posted belum ada angka performanya; minta user dari Insight IG.")
    if r["editan_belum_dipelajari"]:
        baris.append(f"Ada {r['editan_belum_dipelajari']} naskah yang kamu edit; jalankan pelajari_editan.")
    if r["tugas_menunggu"]:
        baris.append("TUGAS DARI USER:\n" + "\n".join(f"- T-{t['id']}: {t['permintaan']}" for t in r["tugas_menunggu"]))
    return "\n".join(baris)


@mcp.tool()
@_aman
def selesaikan_tugas(kode_tugas: str, hasil: str) -> str:
    """Tandai tugas titipan user selesai, dengan ringkasan singkat apa yang dikerjakan (tampil di dashboard)."""
    t = db().selesaikan_tugas(int(re.sub(r"\D", "", kode_tugas)), hasil)
    return f"T-{t['id']} selesai."


# ---------------- Buku ----------------

@mcp.tool()
@_aman
def tambah_buku(judul: str, penulis: str = "", status: STATUS_BUKU = "Mau Dibaca",
                genre: list[str] | None = None) -> str:
    """Tambah buku ke rak."""
    return "Ditambahkan: " + _f_buku(db().tambah_buku(judul, penulis, status, genre))


@mcp.tool()
@_aman
def update_buku(buku: str, status: STATUS_BUKU | None = None, rating: int | None = None,
                kesan: str | None = None) -> str:
    """Ubah status/rating(1-5)/kesan singkat. `buku` = kode (B-1) atau judul."""
    b = db().cari_buku(buku)
    return "Diperbarui: " + _f_buku(db().ubah_buku(b["id"], status=status, rating=rating, kesan=kesan))


@mcp.tool()
@_aman
def daftar_buku(status: STATUS_BUKU | None = None) -> str:
    """Daftar buku di rak."""
    hasil = db().daftar_buku(status)
    return "\n".join(_f_buku(b) + f" | {b['jumlah_bahan']} bahan, {b['jumlah_ide']} ide" for b in hasil) or "Rak kosong."


# ---------------- Bahan ----------------

@mcp.tool()
@_aman
def catat_bahan(buku: str, isi: str, jenis: JENIS = "Reaksi", lokasi: str = "",
                tema: list[str] | None = None) -> str:
    """Simpan reaksi/kutipan/cerita pribadi user. Tulis kata-kata user APA ADANYA, jangan dirapikan.
    lokasi = halaman/bab. tema = kata kunci bebas (mis. keluarga, kehilangan)."""
    b = db().cari_buku(buku)
    x = db().catat_bahan(b["id"], isi, jenis, lokasi, tema)
    return f"Tersimpan #{x['id']} untuk {b['judul']}."


@mcp.tool()
@_aman
def bahan_buku(buku: str, hanya_belum_dipakai: bool = False) -> str:
    """Semua bahan mentah satu buku + kesan + ide yang sudah ada. Pakai untuk mencari ide baru."""
    b = db().cari_buku(buku)
    bahan = db().bahan_buku(b["id"], hanya_belum_dipakai)
    ide = db().daftar_ide(buku_id=b["id"])
    out = [_f_buku(b), f"Kesan: {b['kesan'] or '-'}", "Bahan:"]
    out += [_f_bahan(x) for x in bahan] or ["(kosong, ajak user bercerita dulu)"]
    if ide:
        out += ["Ide yang sudah ada (jangan diulang):"] + [_f_ide(i) for i in ide]
    return "\n".join(out)


@mcp.tool()
@_aman
def cari_bahan(kata: str = "", tema: str = "", jenis: JENIS | Literal[""] = "") -> str:
    """Cari bahan lintas buku berdasar kata atau tema. Berguna untuk konten tematik
    (mis. '5 buku untuk yang lagi patah hati')."""
    hasil = db().cari_bahan(kata, tema, jenis)
    if not hasil:
        return "Tidak ada. Tema yang tersedia: " + (", ".join(db().semua_tema()) or "-")
    return "\n".join(f"{_f_bahan(x)} ({x['buku_judul']})" for x in hasil)


# ---------------- Ide ----------------

class IdeBaru(BaseModel):
    judul: str = Field(description="Judul ide, singkat")
    sudut: SUDUT
    format: FORMAT = "Carousel"
    hook: str = Field("", description="Kalimat pembuka, sebaiknya kutip kata-kata user dari bahan")


@mcp.tool()
@_aman
def simpan_ide(ide: list[IdeBaru], buku: str = "") -> str:
    """Simpan satu/lebih ide konten (status 'Ide'). `buku` boleh kosong untuk ide tematik."""
    buku_id = db().cari_buku(buku)["id"] if buku else None
    hasil = [db().tambah_ide(i.judul, buku_id, i.sudut, i.format, i.hook) for i in ide]
    return "Tersimpan:\n" + "\n".join(_f_ide(i) for i in hasil)


@mcp.tool()
@_aman
def daftar_ide(status: STATUS_IDE | None = None, batas: int = 20) -> str:
    """Daftar ide (terbaru diubah dulu)."""
    return "\n".join(_f_ide(i) for i in db().daftar_ide(status, batas=batas)) or "Belum ada ide."


@mcp.tool()
@_aman
def konteks_ide(kode_ide: str) -> str:
    """SEMUA yang dibutuhkan untuk menulis naskah dalam satu panggilan: detail ide, naskah saat ini,
    bahan buku terkait, dan panduan suara user."""
    i = db().ide(kode_ide)
    out = [_f_ide(i), f"Hook: {i['hook'] or '-'}"]
    if i["buku_id"]:
        b = db().buku(i["buku_id"])
        out += [f"Kesan buku: {b['kesan'] or '-'}", "Bahan buku:"]
        out += [_f_bahan(x) for x in db().bahan_buku(b["id"])] or ["(kosong)"]
    elif i["bahan"]:
        out += ["Bahan terkait:"] + [_f_bahan(x) for x in i["bahan"]]
    out += [f"=== TEMPLATE {i['format'].upper()} ===", db().template(i["format"])[i["format"]],
            "Naskah saat ini:", i["naskah"] or "(belum ada)", "", "=== PANDUAN SUARA ===", db().panduan_suara()]
    hooks = db().hook_terbukti(3)
    if hooks:
        out += ["", "Hook terbukti (performa terbaik, untuk inspirasi pola, jangan disalin):"]
        out += [f"- {h['hook']}" for h in hooks]
    return "\n".join(out)


@mcp.tool()
@_aman
def ubah_ide(kode_ide: str, status: STATUS_IDE | None = None, jadwal: str | None = None,
             judul: str | None = None, hook: str | None = None, format: FORMAT | None = None) -> str:
    """Ubah status/jadwal (YYYY-MM-DD, '' untuk hapus)/judul/hook/format sebuah ide."""
    return "Diperbarui: " + _f_ide(db().ubah_ide(kode_ide, status=status, jadwal=jadwal, judul=judul,
                                                  hook=hook, format=format))


@mcp.tool()
@_aman
def simpan_naskah(kode_ide: str, naskah: str, bahan_dipakai: list[int] | None = None) -> str:
    """Simpan naskah buatanmu (tercatat sebagai versi 'agent'), lalu cek anti-AI otomatis.
    bahan_dipakai = nomor bahan (#) yang dipakai, agar ditandai sudah terpakai."""
    i = db().simpan_naskah(kode_ide, naskah, oleh="agent", bahan_ids=bahan_dipakai)
    return (f"Naskah IDE-{i['id']} tersimpan [{i['status']}]. User bisa mengeditnya di dashboard.\n\n"
            + anti_ai.ringkas(anti_ai.periksa(naskah)))


# ---------------- Pertanyaan audiens ----------------

@mcp.tool()
@_aman
def catat_pertanyaan(pertanyaan: str, sumber: Literal["Komentar", "DM", "Story", "Lainnya"] = "Komentar") -> str:
    """Catat pertanyaan/request audiens."""
    return f"Tersimpan Q-{db().catat_pertanyaan(pertanyaan, sumber)['id']}."


@mcp.tool()
@_aman
def pertanyaan_terbuka() -> str:
    """Pertanyaan audiens yang belum dijadikan konten."""
    return "\n".join(f"Q-{q['id']} [{q['sumber']}] {q['isi']}" for q in db().daftar_pertanyaan()) or "Tidak ada."


@mcp.tool()
@_aman
def jawab_pertanyaan(kode_pertanyaan: str, kode_ide: str = "") -> str:
    """Tandai pertanyaan sudah dijawab, opsional dikaitkan ke ide konten yang menjawabnya."""
    ide_id = db().ide(kode_ide)["id"] if kode_ide else None
    db().tandai_pertanyaan(int(re.sub(r"\D", "", kode_pertanyaan)), True, ide_id)
    return "Ditandai terjawab."


# ---------------- Gaya bahasa ----------------

@mcp.tool()
@_aman
def panduan_suara() -> str:
    """Panduan gaya bahasa user (sudah termasuk di konteks_ide)."""
    return db().panduan_suara()


@mcp.tool()
@_aman
def perbarui_panduan_suara(teks_lengkap: str) -> str:
    """Ganti seluruh panduan suara. HANYA setelah user menyetujui usulan perubahannya."""
    db().simpan_panduan_suara(teks_lengkap)
    return "Panduan suara diperbarui."


def _diff_ringkas(a: str, b: str) -> str:
    pecah = lambda s: [k.strip() for k in re.split(r"(?<=[.!?])\s+|\n+", s) if k.strip()]
    baris = [d for d in difflib.ndiff(pecah(a), pecah(b)) if d[:1] in "-+"]
    return "\n".join(baris) or "(hanya beda spasi)"


@mcp.tool()
@_aman
def pelajari_editan(batas: int = 3) -> str:
    """Bandingkan naskah tulisanmu (agent) dengan versi final yang sudah diedit user.
    '-' = kalimatmu yang dibuang/diubah user, '+' = versi user. Simpulkan pola gaya user,
    usulkan tambahan ke panduan suara, minta persetujuan, lalu perbarui_panduan_suara
    dan tandai_dipelajari."""
    pasangan = db().pasangan_editan(batas)
    if not pasangan:
        return "Belum ada editan baru untuk dipelajari."
    return "\n\n".join(f"== IDE-{p['id']} {p['judul']} ==\n{_diff_ringkas(p['versi_agent'], p['versi_final'])}"
                       for p in pasangan)


@mcp.tool()
@_aman
def tandai_dipelajari(kode_ide: list[str]) -> str:
    """Tandai editan yang sudah dipelajari supaya tidak muncul lagi."""
    db().tandai_dipelajari([db().ide(k)["id"] for k in kode_ide])
    return "Ditandai."


# ---------------- Template & performa ----------------

@mcp.tool()
@_aman
def template_format(format: FORMAT | None = None) -> str:
    """Kerangka naskah per format (sudah termasuk di konteks_ide)."""
    return "\n\n".join(f"== {k} ==\n{v}" for k, v in db().template(format).items())


@mcp.tool()
@_aman
def catat_performa(kode_ide: str, likes: int | None = None, komentar: int | None = None,
                   simpan: int | None = None, share: int | None = None, jangkauan: int | None = None,
                   tanggal_posting: str | None = None) -> str:
    """Catat angka dari Insight Instagram untuk konten yang sudah diposting. Status otomatis jadi Posted."""
    i = db().ubah_ide(kode_ide, status="Posted", likes=likes, komentar=komentar, simpan=simpan,
                      share=share, jangkauan=jangkauan, tanggal_posting=tanggal_posting)
    s = db()._skor(i)
    rasio = f", rasio interaksi {s['rasio']}%" if s["rasio"] is not None else ""
    return f"IDE-{i['id']} tercatat: skor {s['skor']}{rasio}."


@mcp.tool()
@_aman
def hook_terbukti(batas: int = 10) -> str:
    """Hook dari konten dengan performa terbaik. Pakai untuk mempelajari POLA hook yang berhasil."""
    h = db().hook_terbukti(batas)
    return "\n".join(f"- [{x['sudut'] or '-'} | {x['format']} | skor {x['skor']}] {x['hook']}" for x in h) \
        or "Belum ada data. Isi angka performa konten yang sudah Posted dulu."


@mcp.tool()
@_aman
def laporan_mingguan(tanggal_akhir: str | None = None) -> str:
    """Laporan 7 hari terakhir (atau 7 hari sampai tanggal_akhir YYYY-MM-DD): yang diposting,
    performa per sudut/format, produktivitas, dan jadwal pekan depan."""
    from datetime import date, timedelta
    akhir = date.fromisoformat(tanggal_akhir) if tanggal_akhir else date.today()
    L = db().laporan((akhir - timedelta(days=6)).isoformat(), akhir.isoformat())
    st = L["statistik"]
    out = [f"LAPORAN {L['mulai']} s/d {L['selesai']}",
           f"Diposting: {len(L['diposting'])} | Ide baru: {L['ide_baru']} | Bahan baru: {L['bahan_baru']}"
           f" | Pertanyaan baru: {L['pertanyaan_baru']}"
           + (f" | Buku selesai: {', '.join(b['judul'] for b in L['buku_selesai'])}" if L["buku_selesai"] else "")]
    if st["konten"]:
        out.append("Performa (skor = likes + 2*komentar + 3*(simpan+share)):")
        out += [f"- IDE-{k['id']} {k['judul']} | {k['sudut'] or '-'} | {k['format']} | skor {k['skor']}"
                + (f" | {k['rasio']}%" if k["rasio"] is not None else "") for k in st["konten"]]
        out.append("Rata skor per sudut: " + ", ".join(f"{g['nama']} {g['rata_skor']} ({g['jumlah']})" for g in st["per_sudut"]))
        out.append("Rata skor per format: " + ", ".join(f"{g['nama']} {g['rata_skor']} ({g['jumlah']})" for g in st["per_format"]))
    if L["belum_ada_angka"]:
        out.append("Belum ada angka: " + ", ".join(f"IDE-{x['id']} {x['judul']}" for x in L["belum_ada_angka"]))
    out.append("Jadwal pekan depan: " + (", ".join(f"{x['jadwal']} IDE-{x['id']} {x['judul']} [{x['status']}]"
                                                   for x in L["jadwal_pekan_depan"]) or "kosong"))
    return "\n".join(out)


@mcp.tool()
def cek_anti_ai(naskah: str) -> str:
    """Periksa ciri tulisan AI. Berjalan lokal tanpa memakai token model."""
    return anti_ai.ringkas(anti_ai.periksa(naskah))


@mcp.tool()
def alamat_dashboard() -> str:
    """URL dashboard web untuk user."""
    return f"http://localhost:{_port()}"


# ---------------- Prompts (alur siap pakai) ----------------

@mcp.prompt()
def mulai_hari() -> str:
    """Cek kondisi hari ini dan kerjakan tugas titipan."""
    return ("Panggil ringkasan_hari_ini. Kerjakan tugas dari user satu per satu (tanya kalau kurang jelas), "
            "lalu selesaikan_tugas. Setelah itu sarankan 1-3 hal paling penting untuk dikerjakan hari ini.")


@mcp.prompt()
def cari_ide(buku: str) -> str:
    """Cari ide konten dari satu buku memakai 8 sudut."""
    return (f"Panggil bahan_buku('{buku}'). Usulkan 6-8 ide memakai 8 sudut konten, masing-masing dengan hook "
            "yang mengutip kata-kataku dari bahan. Kalau bahan kurang untuk suatu sudut, tanyakan padaku dulu. "
            "Tunjukkan daftarnya, biarkan aku memilih, lalu simpan_ide hanya yang kupilih.")


@mcp.prompt()
def wawancara(kode_ide: str) -> str:
    """Gali cerita user untuk satu ide, lalu tulis naskah dari jawabannya."""
    return (f"Panggil konteks_ide('{kode_ide}') dan ubah_ide statusnya ke Wawancara. "
            "Wawancarai aku SATU pertanyaan per giliran (maks 5) untuk menggali momen spesifik, opini, dan "
            "perasaanku. Simpan jawaban pentingku dengan catat_bahan (kata-kataku apa adanya). "
            "Lalu susun naskah HANYA dari jawabanku dan bahan, ikuti panduan suara, dan simpan_naskah. "
            "Bahas temuan anti-AI denganku.")


@mcp.prompt()
def belajar_gaya() -> str:
    """Pelajari editan user agar naskah berikutnya makin mirip gayanya."""
    return ("Panggil pelajari_editan dan panduan_suara. Simpulkan pola: kata yang kubuang, kata yang kutambah, "
            "panjang kalimat, nada. Usulkan perubahan konkret untuk panduan suara (tunjukkan bagian yang "
            "berubah saja). Setelah aku setuju, perbarui_panduan_suara lalu tandai_dipelajari.")


@mcp.prompt()
def susun_panduan_suara() -> str:
    """Susun panduan suara dari caption Instagram lama yang ditempel user."""
    return ("Aku akan menempelkan beberapa caption Instagram Pojok Literasi yang sudah pernah diposting. "
            "Kalau belum kutempel, minta dulu 5-10 caption (campur yang ramai dan yang biasa, dan yang kutulis sendiri, "
            "bukan dibantu AI). Panggil panduan_suara untuk melihat formatnya. Analisis: sapaan, kata khas, panjang "
            "kalimat, cara membuka dan menutup, nada, emoji. Isi panduan dengan format yang sama, pakai 3 caption "
            "terbaik sebagai 'Contoh tulisan asliku', tambahkan kata yang tidak pernah kupakai ke daftar terlarang. "
            "Tunjukkan draftnya, simpan dengan perbarui_panduan_suara HANYA setelah aku setuju.")


@mcp.prompt()
def evaluasi_mingguan() -> str:
    """Evaluasi pekan ini dan rencana pekan depan."""
    return ("Panggil laporan_mingguan dan hook_terbukti. Kalau ada konten Posted tanpa angka, minta angkanya "
            "dariku (likes, komentar, simpan, share, jangkauan dari Insight IG) lalu catat_performa. Jelaskan "
            "singkat: apa yang berhasil, apa yang tidak, dan kenapa (lihat sudut, format, hook). Lalu usulkan "
            "3 ide untuk pekan depan dari bahan yang belum dipakai (bahan_buku / cari_bahan), dengan sudut dan "
            "format yang terbukti berhasil. Simpan yang kupilih dengan simpan_ide dan atur jadwalnya.")


# ---------------- Menjalankan ----------------

def _port() -> int:
    return int(os.environ.get("POJOK_PORT", "8765"))


def _nyalakan_dashboard() -> None:
    if os.environ.get("POJOK_WEB", "1") == "0":
        return
    import socket

    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", _port())) == 0:
            return  # sudah jalan (mis. jendela Claude lain)

    def jalan():
        import uvicorn
        from .web import buat_app
        try:
            uvicorn.run(buat_app(db()), host="127.0.0.1", port=_port(), log_level="warning", access_log=False)
        except BaseException as e:  # jangan sampai mematikan MCP
            print(f"Dashboard gagal jalan: {e}", file=sys.stderr)

    threading.Thread(target=jalan, daemon=True).start()


def main() -> None:
    _nyalakan_dashboard()
    mcp.run()


if __name__ == "__main__":
    main()
