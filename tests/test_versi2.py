"""Uji fitur Versi 2: template, performa, hook terbukti, laporan, dan migrasi database lama."""
import sqlite3
from datetime import date

import pytest
from starlette.testclient import TestClient

from pojok_literasi import mcp_server
from pojok_literasi.db import DB
from pojok_literasi.web import buat_app

HARI_INI = date.today().isoformat()


@pytest.fixture
def db(tmp_path):
    d = DB(tmp_path / "uji.db")
    mcp_server._db = d
    yield d
    mcp_server._db = None


def _isi(db):
    b = db.tambah_buku("Laut Bercerita", status="Sedang Dibaca")
    a = db.tambah_ide("Bab 2 dan kakakku", b["id"], "Momen Hidupku yang Nyambung", "Reels", "Aku nangis di KRL")
    c = db.tambah_ide("Ending yang bikin kesel", b["id"], "Yang Aku Tidak Setuju", "Carousel", "Endingnya curang")
    db.tambah_ide("Belum diposting", b["id"], "Ekspektasi vs Kenyataan")
    return a, c


def test_migrasi_database_versi1(tmp_path):
    p = tmp_path / "lama.db"
    c = sqlite3.connect(p)
    c.executescript("""CREATE TABLE ide (id INTEGER PRIMARY KEY, buku_id INTEGER, judul TEXT NOT NULL,
        sudut TEXT NOT NULL DEFAULT '', format TEXT NOT NULL DEFAULT 'Carousel', hook TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Ide', jadwal TEXT, naskah TEXT NOT NULL DEFAULT '',
        dibuat TEXT NOT NULL DEFAULT (datetime('now','localtime')), diubah TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        INSERT INTO ide (judul) VALUES ('ide lama');""")
    c.commit(); c.close()
    d = DB(p)
    i = d.ubah_ide(1, likes=10, simpan=3)
    assert i["judul"] == "ide lama" and i["likes"] == 10
    assert "Reels" in d.template()


def test_performa_dan_hook(db):
    a, c = _isi(db)
    m = mcp_server
    out = m.catat_performa(f"IDE-{a['id']}", likes=100, komentar=10, simpan=20, share=5, jangkauan=1000)
    assert "skor 195" in out and "13.5%" in out  # 100 + 2*10 + 3*25 ; 135/1000
    m.catat_performa(f"IDE-{c['id']}", likes=50, komentar=30)
    assert db.ide(a["id"])["status"] == "Posted" and db.ide(a["id"])["tanggal_posting"] == HARI_INI
    st = db.statistik()
    assert [k["id"] for k in st["konten"]] == [a["id"], c["id"]]
    assert st["per_format"][0]["nama"] == "Reels"
    hooks = m.hook_terbukti()
    assert hooks.index("Aku nangis") < hooks.index("Endingnya curang")
    assert "GAGAL" in m.catat_performa(f"IDE-{a['id']}", likes=-1)
    assert "Hook terbukti" in m.konteks_ide("IDE-3") and "TEMPLATE CAROUSEL" in m.konteks_ide("IDE-3")


def test_laporan_mingguan(db):
    a, _ = _isi(db)
    db.ubah_ide(a["id"], status="Posted")
    lap = mcp_server.laporan_mingguan()
    assert "Diposting: 1" in lap and "Ide baru: 3" in lap
    assert "Belum ada angka: IDE-1" in lap
    mcp_server.catat_performa("IDE-1", likes=5)
    assert "Rata skor per sudut: Momen Hidupku yang Nyambung 5.0 (1)" in mcp_server.laporan_mingguan()
    assert "posted_tanpa_angka" in db.ringkasan()


def test_template(db):
    assert "Slide 1" in mcp_server.template_format("Carousel")
    db.simpan_template("Story", "kerangka baruku")
    assert db.template("Story") == {"Story": "kerangka baruku"}


def test_api_versi2(db):
    a, _ = _isi(db)
    c = TestClient(buat_app(db))
    assert c.patch(f"/api/ide/{a['id']}", json={"likes": 7, "status": "Posted"}).json()["likes"] == 7
    assert c.get("/api/statistik").json()["konten"][0]["skor"] == 7
    assert c.get("/api/hook").json()[0]["hook"] == "Aku nangis di KRL"
    assert c.get(f"/api/laporan?mulai={HARI_INI}&selesai={HARI_INI}").json()["diposting"][0]["id"] == a["id"]
    assert c.put("/api/template/Reels", json={"kerangka": "x"}).status_code == 200
    assert c.get("/api/template").json()["Reels"] == "x"
    assert c.put("/api/template/Ngawur", json={"kerangka": "x"}).status_code == 400
    # mengosongkan jadwal tetap bisa
    c.patch(f"/api/ide/{a['id']}", json={"jadwal": "2026-11-05"})
    assert c.patch(f"/api/ide/{a['id']}", json={"jadwal": ""}).json()["jadwal"] is None
