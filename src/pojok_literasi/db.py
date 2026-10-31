"""Penyimpanan data Pojok Literasi: satu file SQLite.

Dipakai bersama oleh MCP server (agent) dan dashboard web (kamu).
Semua fungsi mengembalikan dict biasa supaya mudah dipakai dua-duanya.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

STATUS_BUKU = ["Mau Dibaca", "Sedang Dibaca", "Selesai", "Berhenti"]
STATUS_IDE = ["Ide", "Wawancara", "Draft", "Siap", "Posted"]
JENIS_BAHAN = ["Reaksi", "Kutipan", "Cerita Pribadi"]
FORMAT = ["Carousel", "Reels", "Single Post", "Story"]
SUMBER = ["Komentar", "DM", "Story", "Lainnya"]
SUDUT = [
    "Kalimat yang Mengubah Pikiranku", "Yang Aku Tidak Setuju", "Cocok untuk Kamu yang...",
    "Sebelum vs Sesudah Baca", "Detail yang Jarang Dibahas", "Kalau Suka X Baca Ini",
    "Momen Hidupku yang Nyambung", "Ekspektasi vs Kenyataan",
]

PANDUAN_AWAL = """## Siapa aku
(2-3 kalimat tentang kamu dan kenapa bikin Pojok Literasi)

## Gaya bicaraku
- Sapaan ke audiens:
- Kata/frasa khas:
- Cara aku menutup konten:
- Kalimat pendek-pendek, kayak ngobrol

## Contoh tulisan asliku
(tempel 3-5 caption terbaikmu)

## Aturan wajib
- Minimal 1 detail pribadi dan 1 opini tegas
- Kalimat pertama langsung ke inti
- Naskah HANYA dari jawabanku/catatanku; AI tidak boleh mengarang pengalaman
"""

SKEMA = """
CREATE TABLE IF NOT EXISTS buku (
    id INTEGER PRIMARY KEY,
    judul TEXT NOT NULL,
    penulis TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Mau Dibaca',
    genre TEXT NOT NULL DEFAULT '[]',
    rating INTEGER,
    kesan TEXT NOT NULL DEFAULT '',
    tanggal_selesai TEXT,
    dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS bahan (
    id INTEGER PRIMARY KEY,
    buku_id INTEGER NOT NULL REFERENCES buku(id) ON DELETE CASCADE,
    jenis TEXT NOT NULL DEFAULT 'Reaksi',
    isi TEXT NOT NULL,
    lokasi TEXT NOT NULL DEFAULT '',
    tema TEXT NOT NULL DEFAULT '[]',
    dipakai INTEGER NOT NULL DEFAULT 0,
    dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS ide (
    id INTEGER PRIMARY KEY,
    buku_id INTEGER REFERENCES buku(id) ON DELETE SET NULL,
    judul TEXT NOT NULL,
    sudut TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT 'Carousel',
    hook TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Ide',
    jadwal TEXT,
    naskah TEXT NOT NULL DEFAULT '',
    dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    diubah TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS ide_bahan (
    ide_id INTEGER NOT NULL REFERENCES ide(id) ON DELETE CASCADE,
    bahan_id INTEGER NOT NULL REFERENCES bahan(id) ON DELETE CASCADE,
    PRIMARY KEY (ide_id, bahan_id)
);
CREATE TABLE IF NOT EXISTS naskah_versi (
    id INTEGER PRIMARY KEY,
    ide_id INTEGER NOT NULL REFERENCES ide(id) ON DELETE CASCADE,
    naskah TEXT NOT NULL,
    oleh TEXT NOT NULL,
    dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS pertanyaan (
    id INTEGER PRIMARY KEY,
    isi TEXT NOT NULL,
    sumber TEXT NOT NULL DEFAULT 'Komentar',
    ide_id INTEGER REFERENCES ide(id) ON DELETE SET NULL,
    dijawab INTEGER NOT NULL DEFAULT 0,
    dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS tugas (
    id INTEGER PRIMARY KEY,
    permintaan TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Menunggu',
    hasil TEXT NOT NULL DEFAULT '',
    dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    selesai TEXT
);
CREATE TABLE IF NOT EXISTS pengaturan (
    kunci TEXT PRIMARY KEY,
    nilai TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS template (
    format TEXT PRIMARY KEY,
    kerangka TEXT NOT NULL
);
"""

# Kolom yang ditambahkan setelah Versi 1 (database lama di-upgrade otomatis).
KOLOM_BARU = {
    "ide": {
        "likes": "INTEGER", "komentar": "INTEGER", "simpan": "INTEGER",
        "share": "INTEGER", "jangkauan": "INTEGER", "tanggal_posting": "TEXT",
    },
}
METRIK = ["likes", "komentar", "simpan", "share", "jangkauan"]

TEMPLATE_AWAL = {
    "Carousel": """Slide 1 (HOOK): kalimat yang bikin berhenti scroll, maks 8 kata
Slide 2: konteks singkat (buku apa, kenapa aku baca)
Slide 3-5: isi utama, satu poin per slide, kalimat pendek
Slide 6: momen/perasaan pribadiku
Slide terakhir: pertanyaan ke audiens + ajakan simpan/share

Caption: 2-4 kalimat pelengkap, tutup dengan pertanyaan""",
    "Reels": """0-3 detik (HOOK): kalimat pembuka langsung ke inti
3-15 detik: cerita singkat / konteks
15-40 detik: isi utama (1-3 poin)
40-60 detik: perasaanku + ajakan komentar

Teks di layar: hook ditulis besar di awal
Caption: 1-2 kalimat + pertanyaan""",
    "Single Post": """Visual: buku + 1 kalimat kuat di gambar
Caption baris 1 (HOOK): terlihat sebelum 'selengkapnya'
Caption isi: cerita pendek pengalamanku
Penutup: pertanyaan ke audiens""",
    "Story": """Story 1: hook / pertanyaan (pakai stiker polling/kuis)
Story 2-3: isi singkat
Story 4: ajakan (stiker pertanyaan / link postingan)""",
}


class GagalValidasi(ValueError):
    pass


def lokasi_default() -> Path:
    if os.environ.get("POJOK_DB"):
        return Path(os.environ["POJOK_DB"]).expanduser()
    return Path.home() / "PojokLiterasi" / "pojok-literasi.db"


def _cek(nilai: str | None, pilihan: list[str], nama: str) -> None:
    if nilai is not None and nilai not in pilihan:
        raise GagalValidasi(f"{nama} '{nilai}' tidak dikenal. Pilihan: {', '.join(pilihan)}")


def _baris(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("genre", "tema"):
        if k in d:
            d[k] = json.loads(d[k])
    for k in ("dipakai", "dijawab"):
        if k in d:
            d[k] = bool(d[k])
    return d


class DB:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else lokasi_default()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA foreign_keys = ON")
        self.c.execute("PRAGMA journal_mode = WAL")  # aman dipakai MCP + web bersamaan
        self.c.executescript(SKEMA)
        self._migrasi()
        self.c.execute("INSERT OR IGNORE INTO pengaturan VALUES ('panduan_suara', ?)", (PANDUAN_AWAL,))
        self.c.executemany("INSERT OR IGNORE INTO template VALUES (?, ?)", TEMPLATE_AWAL.items())
        self.c.commit()

    def _migrasi(self) -> None:
        for tabel, kolom in KOLOM_BARU.items():
            ada = {r[1] for r in self.c.execute(f"PRAGMA table_info({tabel})")}
            for nama, tipe in kolom.items():
                if nama not in ada:
                    self.c.execute(f"ALTER TABLE {tabel} ADD COLUMN {nama} {tipe}")

    def _q(self, sql: str, args: tuple = ()) -> list[dict]:
        return [_baris(r) for r in self.c.execute(sql, args).fetchall()]

    def _satu(self, sql: str, args: tuple = ()) -> dict | None:
        return _baris(self.c.execute(sql, args).fetchone())

    def _tulis(self, sql: str, args: tuple = ()) -> int:
        cur = self.c.execute(sql, args)
        self.c.commit()
        return cur.lastrowid

    # ---------------- Buku ----------------

    def tambah_buku(self, judul: str, penulis: str = "", status: str = "Mau Dibaca",
                    genre: list[str] | None = None) -> dict:
        judul = judul.strip()
        if not judul:
            raise GagalValidasi("Judul tidak boleh kosong.")
        _cek(status, STATUS_BUKU, "Status")
        ada = self._satu("SELECT * FROM buku WHERE lower(judul) = lower(?)", (judul,))
        if ada:
            raise GagalValidasi(f"Buku '{ada['judul']}' sudah ada (B-{ada['id']}).")
        i = self._tulis("INSERT INTO buku (judul, penulis, status, genre) VALUES (?,?,?,?)",
                        (judul, penulis.strip(), status, json.dumps(genre or [])))
        return self.buku(i)

    def buku(self, id: int) -> dict:
        b = self._satu("SELECT * FROM buku WHERE id = ?", (id,))
        if not b:
            raise GagalValidasi(f"Buku B-{id} tidak ditemukan.")
        return b

    def cari_buku(self, kunci: str | int) -> dict:
        """Cari buku dari kode (B-3 / 3) atau judul (boleh sebagian)."""
        s = str(kunci).strip()
        angka = s.upper().removeprefix("B-")
        if angka.isdigit():
            return self.buku(int(angka))
        persis = self._satu("SELECT * FROM buku WHERE lower(judul) = lower(?)", (s,))
        if persis:
            return persis
        hasil = self._q("SELECT * FROM buku WHERE judul LIKE ? ORDER BY id", (f"%{s}%",))
        if not hasil:
            raise GagalValidasi(f"Buku '{s}' tidak ditemukan.")
        if len(hasil) > 1:
            raise GagalValidasi("Judul ambigu: " + ", ".join(f"B-{b['id']} {b['judul']}" for b in hasil))
        return hasil[0]

    def daftar_buku(self, status: str | None = None) -> list[dict]:
        _cek(status, STATUS_BUKU, "Status")
        sql = """SELECT b.*, (SELECT count(*) FROM bahan WHERE buku_id=b.id) AS jumlah_bahan,
                        (SELECT count(*) FROM ide WHERE buku_id=b.id) AS jumlah_ide
                 FROM buku b"""
        if status:
            return self._q(sql + " WHERE status = ? ORDER BY id DESC", (status,))
        return self._q(sql + " ORDER BY id DESC")

    def ubah_buku(self, id: int, **ubah: Any) -> dict:
        boleh = {"judul", "penulis", "status", "genre", "rating", "kesan", "tanggal_selesai"}
        ubah = {k: v for k, v in ubah.items() if k in boleh and v is not None}
        _cek(ubah.get("status"), STATUS_BUKU, "Status")
        if "rating" in ubah:
            ubah["rating"] = max(1, min(5, int(ubah["rating"])))
        if "genre" in ubah:
            ubah["genre"] = json.dumps(ubah["genre"])
        if ubah.get("status") == "Selesai" and "tanggal_selesai" not in ubah:
            if not self.buku(id)["tanggal_selesai"]:
                ubah["tanggal_selesai"] = date.today().isoformat()
        if ubah:
            kolom = ", ".join(f"{k} = ?" for k in ubah)
            self._tulis(f"UPDATE buku SET {kolom} WHERE id = ?", (*ubah.values(), id))
        return self.buku(id)

    def hapus_buku(self, id: int) -> None:
        self.buku(id)
        self._tulis("DELETE FROM buku WHERE id = ?", (id,))

    # ---------------- Bahan (reaksi/kutipan) ----------------

    def catat_bahan(self, buku_id: int, isi: str, jenis: str = "Reaksi", lokasi: str = "",
                    tema: list[str] | None = None) -> dict:
        if not isi.strip():
            raise GagalValidasi("Isi tidak boleh kosong.")
        _cek(jenis, JENIS_BAHAN, "Jenis")
        self.buku(buku_id)
        i = self._tulis("INSERT INTO bahan (buku_id, jenis, isi, lokasi, tema) VALUES (?,?,?,?,?)",
                        (buku_id, jenis, isi.strip(), lokasi.strip(), json.dumps(tema or [])))
        return self._satu("SELECT * FROM bahan WHERE id = ?", (i,))

    def bahan_buku(self, buku_id: int, hanya_belum_dipakai: bool = False) -> list[dict]:
        sql = "SELECT * FROM bahan WHERE buku_id = ?" + (" AND dipakai = 0" if hanya_belum_dipakai else "")
        return self._q(sql + " ORDER BY id", (buku_id,))

    def cari_bahan(self, kata: str = "", tema: str = "", jenis: str = "", batas: int = 50) -> list[dict]:
        syarat, args = [], []
        if kata:
            syarat.append("(x.isi LIKE ? OR x.lokasi LIKE ?)"); args += [f"%{kata}%", f"%{kata}%"]
        if tema:
            syarat.append("x.tema LIKE ?"); args.append(f'%"{tema}"%')
        if jenis:
            _cek(jenis, JENIS_BAHAN, "Jenis")
            syarat.append("x.jenis = ?"); args.append(jenis)
        where = (" WHERE " + " AND ".join(syarat)) if syarat else ""
        return self._q(f"""SELECT x.*, b.judul AS buku_judul FROM bahan x JOIN buku b ON b.id = x.buku_id
                           {where} ORDER BY x.id DESC LIMIT ?""", (*args, batas))

    def semua_tema(self) -> list[str]:
        tema: set[str] = set()
        for r in self.c.execute("SELECT tema FROM bahan"):
            tema.update(json.loads(r[0]))
        return sorted(tema)

    def ubah_bahan(self, id: int, **ubah: Any) -> dict:
        boleh = {"isi", "jenis", "lokasi", "tema", "dipakai"}
        ubah = {k: v for k, v in ubah.items() if k in boleh and v is not None}
        _cek(ubah.get("jenis"), JENIS_BAHAN, "Jenis")
        if "tema" in ubah:
            ubah["tema"] = json.dumps(ubah["tema"])
        if "dipakai" in ubah:
            ubah["dipakai"] = int(bool(ubah["dipakai"]))
        if ubah:
            kolom = ", ".join(f"{k} = ?" for k in ubah)
            self._tulis(f"UPDATE bahan SET {kolom} WHERE id = ?", (*ubah.values(), id))
        b = self._satu("SELECT * FROM bahan WHERE id = ?", (id,))
        if not b:
            raise GagalValidasi(f"Bahan #{id} tidak ditemukan.")
        return b

    def hapus_bahan(self, id: int) -> None:
        self._tulis("DELETE FROM bahan WHERE id = ?", (id,))

    # ---------------- Ide ----------------

    def tambah_ide(self, judul: str, buku_id: int | None = None, sudut: str = "",
                   format: str = "Carousel", hook: str = "") -> dict:
        if not judul.strip():
            raise GagalValidasi("Judul ide tidak boleh kosong.")
        if sudut:
            _cek(sudut, SUDUT, "Sudut")
        _cek(format, FORMAT, "Format")
        if buku_id is not None:
            self.buku(buku_id)
        i = self._tulis("INSERT INTO ide (judul, buku_id, sudut, format, hook) VALUES (?,?,?,?,?)",
                        (judul.strip(), buku_id, sudut, format, hook.strip()))
        return self.ide(i)

    def ide(self, id: int | str) -> dict:
        n = str(id).upper().removeprefix("IDE-").strip()
        if not n.isdigit():
            raise GagalValidasi(f"Kode ide '{id}' tidak valid (contoh: IDE-3).")
        d = self._satu("""SELECT i.*, b.judul AS buku_judul FROM ide i
                          LEFT JOIN buku b ON b.id = i.buku_id WHERE i.id = ?""", (int(n),))
        if not d:
            raise GagalValidasi(f"Ide IDE-{n} tidak ditemukan.")
        d["bahan"] = self._q("""SELECT x.* FROM bahan x JOIN ide_bahan ib ON ib.bahan_id = x.id
                               WHERE ib.ide_id = ? ORDER BY x.id""", (d["id"],))
        return d

    def daftar_ide(self, status: str | None = None, buku_id: int | None = None, batas: int = 100) -> list[dict]:
        _cek(status, STATUS_IDE, "Status")
        syarat, args = [], []
        if status:
            syarat.append("i.status = ?"); args.append(status)
        if buku_id:
            syarat.append("i.buku_id = ?"); args.append(buku_id)
        where = (" WHERE " + " AND ".join(syarat)) if syarat else ""
        return self._q(f"""SELECT i.id, i.judul, i.sudut, i.format, i.hook, i.status, i.jadwal, i.diubah,
                                  i.buku_id, b.judul AS buku_judul, length(i.naskah) > 0 AS ada_naskah
                           FROM ide i LEFT JOIN buku b ON b.id = i.buku_id{where}
                           ORDER BY i.diubah DESC LIMIT ?""", (*args, batas))

    def ubah_ide(self, id: int | str, **ubah: Any) -> dict:
        d = self.ide(id)
        kosongkan_jadwal = ubah.get("jadwal") == ""
        boleh = {"judul", "sudut", "format", "hook", "status", "jadwal", "buku_id", "tanggal_posting", *METRIK}
        ubah = {k: v for k, v in ubah.items() if k in boleh and v is not None and v != ""}
        _cek(ubah.get("status"), STATUS_IDE, "Status")
        for m in METRIK:
            if m in ubah:
                ubah[m] = int(ubah[m])
                if ubah[m] < 0:
                    raise GagalValidasi(f"{m} tidak boleh negatif.")
        if ubah.get("status") == "Posted" and not d.get("tanggal_posting") and "tanggal_posting" not in ubah:
            ubah["tanggal_posting"] = d.get("jadwal") or date.today().isoformat()
        _cek(ubah.get("format"), FORMAT, "Format")
        if ubah.get("sudut"):
            _cek(ubah["sudut"], SUDUT, "Sudut")
        if kosongkan_jadwal:
            self.c.execute("UPDATE ide SET jadwal = NULL WHERE id = ?", (d["id"],))
        if ubah:
            kolom = ", ".join(f"{k} = ?" for k in ubah)
            self.c.execute(f"UPDATE ide SET {kolom}, diubah = datetime('now','localtime') WHERE id = ?",
                           (*ubah.values(), d["id"]))
        self.c.commit()
        return self.ide(d["id"])

    def simpan_naskah(self, id: int | str, naskah: str, oleh: str = "kamu",
                      bahan_ids: list[int] | None = None) -> dict:
        d = self.ide(id)
        if naskah.strip() != d["naskah"].strip():
            self.c.execute("INSERT INTO naskah_versi (ide_id, naskah, oleh) VALUES (?,?,?)",
                           (d["id"], naskah, oleh))
        status = "Draft" if d["status"] in ("Ide", "Wawancara") else d["status"]
        self.c.execute("""UPDATE ide SET naskah = ?, status = ?, diubah = datetime('now','localtime')
                          WHERE id = ?""", (naskah, status, d["id"]))
        for b in bahan_ids or []:
            bh = self._satu("SELECT * FROM bahan WHERE id = ?", (b,))
            if not bh:
                self.c.rollback()
                raise GagalValidasi(f"Bahan #{b} tidak ditemukan.")
            self.c.execute("INSERT OR IGNORE INTO ide_bahan VALUES (?, ?)", (d["id"], b))
            self.c.execute("UPDATE bahan SET dipakai = 1 WHERE id = ?", (b,))
        self.c.commit()
        return self.ide(d["id"])

    def versi_naskah(self, id: int | str) -> list[dict]:
        d = self.ide(id)
        return self._q("SELECT * FROM naskah_versi WHERE ide_id = ? ORDER BY id DESC", (d["id"],))

    def pasangan_editan(self, batas: int = 5) -> list[dict]:
        """Ide yang punya versi tulisan agent DAN versi final yang sudah diedit kamu,
        dan belum dipelajari. Bahan untuk memperbarui panduan suara."""
        sudah = set(json.loads(self._pengaturan("ide_dipelajari", "[]")))
        hasil = []
        for d in self._q("""SELECT id, judul, naskah FROM ide WHERE length(naskah) > 0
                            ORDER BY diubah DESC LIMIT 100"""):
            if d["id"] in sudah:
                continue
            agent = self._satu("""SELECT naskah FROM naskah_versi WHERE ide_id = ? AND oleh = 'agent'
                                  ORDER BY id DESC LIMIT 1""", (d["id"],))
            terakhir = self._satu("SELECT oleh FROM naskah_versi WHERE ide_id = ? ORDER BY id DESC LIMIT 1",
                                  (d["id"],))
            if agent and terakhir and terakhir["oleh"] == "kamu" and agent["naskah"].strip() != d["naskah"].strip():
                hasil.append({"id": d["id"], "judul": d["judul"], "versi_agent": agent["naskah"],
                              "versi_final": d["naskah"]})
            if len(hasil) >= batas:
                break
        return hasil

    def tandai_dipelajari(self, ide_ids: list[int]) -> None:
        sudah = set(json.loads(self._pengaturan("ide_dipelajari", "[]")))
        sudah.update(int(i) for i in ide_ids)
        self._tulis("INSERT OR REPLACE INTO pengaturan VALUES ('ide_dipelajari', ?)", (json.dumps(sorted(sudah)),))

    def _pengaturan(self, kunci: str, default: str) -> str:
        r = self._satu("SELECT nilai FROM pengaturan WHERE kunci = ?", (kunci,))
        return r["nilai"] if r else default

    def hapus_ide(self, id: int | str) -> None:
        d = self.ide(id)
        self._tulis("DELETE FROM ide WHERE id = ?", (d["id"],))

    # ---------------- Pertanyaan audiens ----------------

    def catat_pertanyaan(self, isi: str, sumber: str = "Komentar") -> dict:
        if not isi.strip():
            raise GagalValidasi("Pertanyaan tidak boleh kosong.")
        _cek(sumber, SUMBER, "Sumber")
        i = self._tulis("INSERT INTO pertanyaan (isi, sumber) VALUES (?,?)", (isi.strip(), sumber))
        return self._satu("SELECT * FROM pertanyaan WHERE id = ?", (i,))

    def daftar_pertanyaan(self, hanya_terbuka: bool = True) -> list[dict]:
        sql = "SELECT * FROM pertanyaan" + (" WHERE dijawab = 0" if hanya_terbuka else "")
        return self._q(sql + " ORDER BY id DESC")

    def tandai_pertanyaan(self, id: int, dijawab: bool = True, ide_id: int | None = None) -> None:
        self._tulis("UPDATE pertanyaan SET dijawab = ?, ide_id = coalesce(?, ide_id) WHERE id = ?",
                    (int(dijawab), ide_id, id))

    # ---------------- Tugas untuk agent ----------------

    def titip_tugas(self, permintaan: str) -> dict:
        if not permintaan.strip():
            raise GagalValidasi("Permintaan tidak boleh kosong.")
        i = self._tulis("INSERT INTO tugas (permintaan) VALUES (?)", (permintaan.strip(),))
        return self._satu("SELECT * FROM tugas WHERE id = ?", (i,))

    def daftar_tugas(self, status: str | None = None) -> list[dict]:
        if status:
            return self._q("SELECT * FROM tugas WHERE status = ? ORDER BY id", (status,))
        return self._q("SELECT * FROM tugas ORDER BY id DESC LIMIT 50")

    def selesaikan_tugas(self, id: int, hasil: str) -> dict:
        if not self._satu("SELECT id FROM tugas WHERE id = ?", (id,)):
            raise GagalValidasi(f"Tugas T-{id} tidak ditemukan.")
        self._tulis("""UPDATE tugas SET status = 'Selesai', hasil = ?, selesai = datetime('now','localtime')
                       WHERE id = ?""", (hasil, id))
        return self._satu("SELECT * FROM tugas WHERE id = ?", (id,))

    # ---------------- Pengaturan ----------------

    def panduan_suara(self) -> str:
        return self._satu("SELECT nilai FROM pengaturan WHERE kunci = 'panduan_suara'")["nilai"]

    def simpan_panduan_suara(self, teks: str) -> None:
        self._tulis("INSERT OR REPLACE INTO pengaturan VALUES ('panduan_suara', ?)", (teks,))

    # ---------------- Template ----------------

    def template(self, format: str | None = None) -> dict[str, str]:
        rows = self._q("SELECT * FROM template ORDER BY format")
        semua = {r["format"]: r["kerangka"] for r in rows}
        if format:
            _cek(format, FORMAT, "Format")
            return {format: semua.get(format, "")}
        return semua

    def simpan_template(self, format: str, kerangka: str) -> None:
        _cek(format, FORMAT, "Format")
        self._tulis("INSERT OR REPLACE INTO template VALUES (?, ?)", (format, kerangka))

    # ---------------- Performa ----------------

    @staticmethod
    def _skor(i: dict) -> dict:
        interaksi = sum(i.get(k) or 0 for k in ("likes", "komentar", "simpan", "share"))
        # simpan & share diberi bobot lebih: sinyal terkuat di algoritma Instagram
        bobot = (i.get("likes") or 0) + 2 * (i.get("komentar") or 0) + 3 * ((i.get("simpan") or 0) + (i.get("share") or 0))
        jangkauan = i.get("jangkauan") or 0
        return {**i, "interaksi": interaksi, "skor": bobot,
                "rasio": round(100 * interaksi / jangkauan, 1) if jangkauan else None}

    def performa(self, mulai: str | None = None, selesai: str | None = None) -> list[dict]:
        """Konten Posted yang sudah ada angkanya, diurutkan skor tertinggi."""
        syarat, args = ["i.status = 'Posted'", "coalesce(i.likes, i.komentar, i.simpan, i.share, i.jangkauan) IS NOT NULL"], []
        if mulai:
            syarat.append("i.tanggal_posting >= ?"); args.append(mulai)
        if selesai:
            syarat.append("i.tanggal_posting <= ?"); args.append(selesai)
        rows = self._q(f"""SELECT i.id, i.judul, i.sudut, i.format, i.hook, i.tanggal_posting,
                                  i.likes, i.komentar, i.simpan, i.share, i.jangkauan, b.judul AS buku_judul
                           FROM ide i LEFT JOIN buku b ON b.id = i.buku_id
                           WHERE {' AND '.join(syarat)}""", tuple(args))
        return sorted((self._skor(r) for r in rows), key=lambda r: r["skor"], reverse=True)

    def statistik(self, mulai: str | None = None, selesai: str | None = None) -> dict:
        data = self.performa(mulai, selesai)

        def kelompok(kunci: str) -> list[dict]:
            g: dict[str, list[dict]] = {}
            for r in data:
                g.setdefault(r[kunci] or "-", []).append(r)
            hasil = [{"nama": k, "jumlah": len(v), "rata_skor": round(sum(x["skor"] for x in v) / len(v), 1)}
                     for k, v in g.items()]
            return sorted(hasil, key=lambda x: x["rata_skor"], reverse=True)

        return {"konten": data, "per_sudut": kelompok("sudut"), "per_format": kelompok("format")}

    def hook_terbukti(self, batas: int = 10) -> list[dict]:
        """Hook dari konten Posted dengan skor tertinggi."""
        return [r for r in self.performa() if (r["hook"] or "").strip()][:batas]

    def laporan(self, mulai: str, selesai: str) -> dict:
        rentang = (mulai, selesai + " 23:59:59")
        hitung = lambda sql: self._satu(sql, rentang)["n"]
        return {
            "mulai": mulai, "selesai": selesai,
            "diposting": self._q("""SELECT id, judul, sudut, format, tanggal_posting FROM ide
                                    WHERE status = 'Posted' AND tanggal_posting BETWEEN ? AND ?
                                    ORDER BY tanggal_posting""", (mulai, selesai)),
            "statistik": self.statistik(mulai, selesai),
            "bahan_baru": hitung("SELECT count(*) AS n FROM bahan WHERE dibuat BETWEEN ? AND ?"),
            "ide_baru": hitung("SELECT count(*) AS n FROM ide WHERE dibuat BETWEEN ? AND ?"),
            "pertanyaan_baru": hitung("SELECT count(*) AS n FROM pertanyaan WHERE dibuat BETWEEN ? AND ?"),
            "buku_selesai": self._q("SELECT id, judul FROM buku WHERE tanggal_selesai BETWEEN ? AND ?",
                                    (mulai, selesai)),
            "belum_ada_angka": self._q("""SELECT id, judul FROM ide WHERE status = 'Posted'
                                          AND coalesce(likes, komentar, simpan, share, jangkauan) IS NULL"""),
            "jadwal_pekan_depan": self._q("""SELECT id, judul, jadwal, status FROM ide WHERE jadwal > ?
                                             AND jadwal <= date(?, '+7 day') ORDER BY jadwal""",
                                          (selesai, selesai)),
        }

    # ---------------- Ringkasan ----------------

    def ringkasan(self) -> dict:
        hari_ini = date.today()
        sepekan = (hari_ini + timedelta(days=7)).isoformat()
        per_status = {s: 0 for s in STATUS_IDE}
        for r in self._q("SELECT status, count(*) AS n FROM ide GROUP BY status"):
            per_status[r["status"]] = r["n"]
        return {
            "sedang_dibaca": self._q("SELECT id, judul, penulis FROM buku WHERE status = 'Sedang Dibaca'"),
            "ide_per_status": per_status,
            "jadwal_sepekan": self._q("""SELECT i.id, i.judul, i.jadwal, i.status, i.format FROM ide i
                                         WHERE jadwal BETWEEN ? AND ? ORDER BY jadwal""",
                                      (hari_ini.isoformat(), sepekan)),
            "draft_mandek": self._q("""SELECT id, judul, diubah FROM ide WHERE status IN ('Draft','Wawancara')
                                       AND diubah < ? ORDER BY diubah""",
                                    ((datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)),
            "pertanyaan_terbuka": self._satu("SELECT count(*) AS n FROM pertanyaan WHERE dijawab = 0")["n"],
            "tugas_menunggu": self._q("SELECT id, permintaan FROM tugas WHERE status = 'Menunggu' ORDER BY id"),
            "bahan_belum_dipakai": self._satu("SELECT count(*) AS n FROM bahan WHERE dipakai = 0")["n"],
            "editan_belum_dipelajari": len(self.pasangan_editan(batas=20)),
            "posted_tanpa_angka": self._satu("""SELECT count(*) AS n FROM ide WHERE status = 'Posted'
                AND coalesce(likes, komentar, simpan, share, jangkauan) IS NULL""")["n"],
        }

    def kalender(self, bulan: str) -> list[dict]:
        """bulan format YYYY-MM."""
        return self._q("""SELECT i.id, i.judul, i.jadwal, i.status, i.format, b.judul AS buku_judul
                          FROM ide i LEFT JOIN buku b ON b.id = i.buku_id
                          WHERE i.jadwal LIKE ? ORDER BY i.jadwal""", (f"{bulan}-%",))

    def ekspor(self) -> dict:
        tabel = ["buku", "bahan", "ide", "ide_bahan", "naskah_versi", "pertanyaan", "tugas", "pengaturan", "template"]
        return {t: [dict(r) for r in self.c.execute(f"SELECT * FROM {t}")] for t in tabel}
