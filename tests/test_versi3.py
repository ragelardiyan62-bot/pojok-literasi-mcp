"""Uji Versi 3: kalender momen, kartu kutipan, pengaturan, dan akses HP dengan PIN."""
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from pojok_literasi import mcp_server
from pojok_literasi.db import DB, GagalValidasi
from pojok_literasi.web import buat_app

HP = ("192.168.1.9", 50000)


@pytest.fixture
def db(tmp_path):
    d = DB(tmp_path / "uji.db")
    mcp_server._db = d
    yield d
    mcp_server._db = None


def test_momen_bawaan_dan_rentang(db):
    nama = {m["nama"] for m in db.daftar_momen()}
    assert {"Hari Buku Nasional", "Hari Aksara Internasional", "Hari Buku Sedunia"} <= nama
    # rentang lintas tahun: 20 Des - 10 Jan
    m = db.momen_antara(date(2026, 12, 20), date(2027, 1, 10))
    assert [x["tanggal_jatuh"] for x in m] == ["2026-12-22", "2026-12-31"]
    besok = (date.today() + timedelta(days=1)).isoformat()
    db.tambah_momen(besok, "Rilis film adaptasi")
    assert "Rilis film adaptasi (1 hari lagi)" not in mcp_server.momen_mendatang(5)  # format: tanggal (n hari lagi) nama
    assert f"{besok} (1 hari lagi) Rilis film adaptasi" in mcp_server.momen_mendatang(5)
    assert any(x["nama"] == "Rilis film adaptasi" for x in db.ringkasan()["momen_mendatang"])


def test_momen_validasi_dan_tidak_diisi_ulang(db, tmp_path):
    for salah in ["17-05", "2026-13-01", "02-30", ""]:
        with pytest.raises(GagalValidasi):
            db.tambah_momen(salah, "x")
    with pytest.raises(GagalValidasi):
        db.tambah_momen("05-17", "Hari Buku Nasional")  # duplikat
    hapus = next(m for m in db.daftar_momen() if m["nama"] == "Akhir tahun")
    db.hapus_momen(hapus["id"])
    d2 = DB(db.path)  # buka ulang: momen yang dihapus tidak muncul lagi
    assert "Akhir tahun" not in {m["nama"] for m in d2.daftar_momen()}


def test_kartu_kutipan_tool(db):
    b = db.tambah_buku("Laut Bercerita", "Leila S. Chudori")
    k = db.catat_bahan(b["id"], "Matilah engkau mati", "Kutipan")
    r = db.catat_bahan(b["id"], "aku nangis", "Reaksi")
    out = mcp_server.buat_kartu_kutipan(k["id"], "senja", "1:1")
    assert f"#kartu?bahan={k['id']}&tema=senja&ukuran=1%3A1" in out and "catatan" not in out
    assert "bukan Kutipan" in mcp_server.buat_kartu_kutipan(r["id"])
    assert "GAGAL" in mcp_server.buat_kartu_kutipan(999)
    assert db.cari_bahan(jenis="Kutipan")[0]["buku_penulis"] == "Leila S. Chudori"


def test_pengaturan_hanya_kunci_yang_boleh(db):
    c = TestClient(buat_app(db))
    c.put("/api/pengaturan", json={"handle_ig": "@pojokliterasi", "panduan_suara": "dibajak"})
    assert c.get("/api/pengaturan").json() == {"handle_ig": "@pojokliterasi"}
    assert db.panduan_suara() != "dibajak"


def test_hp_tanpa_pin_ditolak(db):
    c = TestClient(buat_app(db), client=HP)
    assert c.get("/api/ringkasan").status_code == 403


def test_hp_dengan_pin(db):
    app = buat_app(db, pin="rahasia123")
    lokal = TestClient(app)
    assert lokal.get("/api/akses").json()["hp_aktif"] is True
    hp = TestClient(app, client=HP)
    r = hp.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/masuk"
    assert hp.get("/api/ringkasan").status_code == 401
    assert hp.post("/masuk", data={"pin": "salah"}).status_code == 401
    r = hp.post("/masuk", data={"pin": "rahasia123"}, follow_redirects=False)
    assert r.status_code == 303 and "pojok_sesi" in r.cookies
    assert hp.get("/api/ringkasan").status_code == 200
    assert hp.get("/api/akses").json()["dari_hp"] is True


def test_hp_batas_percobaan(db):
    hp = TestClient(buat_app(db, pin="rahasia123"), client=HP)
    for _ in range(5):
        assert hp.post("/masuk", data={"pin": "salah"}).status_code == 401
    assert hp.post("/masuk", data={"pin": "rahasia123"}).status_code == 429
