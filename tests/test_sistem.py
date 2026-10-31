"""Uji database, MCP tool, dan API dashboard dengan database sementara."""
import asyncio

import pytest
from starlette.testclient import TestClient

from pojok_literasi import mcp_server
from pojok_literasi.db import DB, GagalValidasi
from pojok_literasi.web import buat_app


@pytest.fixture
def db(tmp_path):
    d = DB(tmp_path / "uji.db")
    mcp_server._db = d
    yield d
    mcp_server._db = None


def test_alur_agent_lengkap(db):
    m = mcp_server
    assert "Ditambahkan: B-1" in m.tambah_buku("Laut Bercerita", "Leila S. Chudori", "Sedang Dibaca")
    assert "GAGAL" in m.tambah_buku("laut bercerita")  # duplikat
    m.catat_bahan("Laut", "Bab 2 bikin aku inget kakakku", "Reaksi", "Bab 2", ["keluarga"])
    m.catat_bahan("B-1", "Matilah engkau mati", "Kutipan")
    out = m.bahan_buku("Laut Bercerita")
    assert "#1 [Reaksi, Bab 2]" in out and "#keluarga" in out
    assert "Laut Bercerita" in m.cari_bahan(tema="keluarga")

    out = m.simpan_ide([m.IdeBaru(judul="Bab 2 dan kakakku", sudut="Momen Hidupku yang Nyambung", format="Reels")],
                       buku="B-1")
    assert "IDE-1 [Ide]" in out
    konteks = m.konteks_ide("IDE-1")
    assert "PANDUAN SUARA" in konteks and "inget kakakku" in konteks

    out = m.simpan_naskah("IDE-1", "Di era digital ini, mari kita selami buku ini.", [1])
    assert "PERLU REVISI" in out and "[Draft]" in out
    assert "✓" in m.bahan_buku("B-1", hanya_belum_dipakai=False)

    # user mengedit di dashboard -> agent bisa belajar
    db.simpan_naskah(1, "Aku baca bab 2 di kereta. Jujur aku nangis.", oleh="kamu")
    diff = m.pelajari_editan()
    assert "- Di era digital ini" in diff and "+ Jujur aku nangis." in diff
    m.tandai_dipelajari(["IDE-1"])
    assert "Belum ada" in m.pelajari_editan()

    db.titip_tugas("Buatkan 3 ide dari Laut Bercerita")
    assert "T-1: Buatkan 3 ide" in m.ringkasan_hari_ini()
    m.selesaikan_tugas("T-1", "3 ide disimpan")
    assert "TUGAS" not in m.ringkasan_hari_ini()

    assert "Diperbarui" in m.ubah_ide("IDE-1", status="Siap", jadwal="2026-11-03")
    assert "GAGAL" in m.ubah_ide("IDE-99", status="Siap")
    m.catat_pertanyaan("Buku buat yang lagi burnout?", "DM")
    assert "Q-1 [DM]" in m.pertanyaan_terbuka()
    m.jawab_pertanyaan("Q-1", "IDE-1")
    assert m.pertanyaan_terbuka() == "Tidak ada."


def test_tool_terdaftar():
    async def daftar():
        return [t.name for t in await mcp_server.mcp.list_tools()], [p.name for p in await mcp_server.mcp.list_prompts()]
    tools, prompts = asyncio.run(daftar())
    assert {"ringkasan_hari_ini", "konteks_ide", "pelajari_editan", "cek_anti_ai"} <= set(tools)
    assert {"mulai_hari", "cari_ide", "wawancara", "belajar_gaya", "susun_panduan_suara", "evaluasi_mingguan"} == set(prompts)


def test_validasi(db):
    with pytest.raises(GagalValidasi):
        db.tambah_buku("")
    with pytest.raises(GagalValidasi):
        db.tambah_ide("x", sudut="Sudut Ngawur")


def test_api_dashboard(db):
    c = TestClient(buat_app(db))
    assert "Pojok Literasi" in c.get("/").text
    b = c.post("/api/buku", json={"judul": "Cantik Itu Luka", "status": "Sedang Dibaca", "genre": ["Fiksi"]}).json()
    assert c.post("/api/bahan", json={"buku_id": b["id"], "isi": "kaget di bab 1"}).status_code == 200
    i = c.post("/api/ide", json={"judul": "Ekspektasi", "buku_id": b["id"], "sudut": "Ekspektasi vs Kenyataan"}).json()
    r = c.post(f"/api/ide/{i['id']}/naskah", json={"naskah": "Aku kira berat, ternyata lucu."}).json()
    assert r["status"] == "Draft"
    assert c.patch(f"/api/ide/{i['id']}", json={"status": "Posted", "jadwal": "2026-11-01"}).json()["status"] == "Posted"
    assert c.get("/api/kalender?bulan=2026-11").json()[0]["judul"] == "Ekspektasi"
    assert c.get(f"/api/ide/{i['id']}").json()["versi"][0]["oleh"] == "kamu"
    assert c.post("/api/buku", json={"judul": ""}).status_code == 400
    assert c.post("/api/cek", json={"naskah": "Mari kita selami"}).json()["temuan"]
    ring = c.get("/api/ringkasan").json()
    assert ring["ide_per_status"]["Posted"] == 1
    assert c.put("/api/panduan", json={"teks": "gayaku santai"}).status_code == 200
    assert c.get("/api/panduan").json()["teks"] == "gayaku santai"
