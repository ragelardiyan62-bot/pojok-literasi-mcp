"""Uji alur tool dengan Notion tiruan (tanpa jaringan)."""
import asyncio
import json

import httpx

from pojok_literasi_mcp import server
from pojok_literasi_mcp.notion import Notion

BUKU_ID = "b" * 32
IDE_ID = "i" * 32
REAKSI_ID = "abcd1234" + "r" * 24


def _rt(t):
    return [{"plain_text": t}]


def halaman_buku():
    return {"id": BUKU_ID, "properties": {
        "Judul": {"type": "title", "title": _rt("Laut Bercerita")},
        "Penulis": {"type": "rich_text", "rich_text": _rt("Leila S. Chudori")},
        "Status": {"type": "status", "status": {"name": "Selesai"}},
        "Rating": {"type": "select", "select": None},
        "Kesan Singkat": {"type": "rich_text", "rich_text": []}}}


def halaman_ide():
    return {"id": IDE_ID, "properties": {
        "Ide": {"type": "title", "title": _rt("Bab 2 dan kakakku")},
        "Kode": {"type": "unique_id", "unique_id": {"prefix": "IDE", "number": 3}},
        "Status": {"type": "status", "status": {"name": "Ide"}},
        "Sudut": {"type": "select", "select": {"name": "Momen Hidupku yang Nyambung"}},
        "Format": {"type": "select", "select": {"name": "Reels"}},
        "Hook": {"type": "rich_text", "rich_text": []},
        "Jadwal Posting": {"type": "date", "date": None},
        "Buku": {"type": "relation", "relation": [{"id": BUKU_ID}]},
        "Bahan": {"type": "relation", "relation": []}}}


def halaman_reaksi():
    return {"id": REAKSI_ID, "properties": {
        "Isi": {"type": "title", "title": _rt("inget kakakku")},
        "Jenis": {"type": "select", "select": {"name": "Reaksi"}},
        "Halaman/Bab": {"type": "rich_text", "rich_text": _rt("Bab 2")},
        "Dipakai": {"type": "checkbox", "checkbox": False}}}


def pasang(log):
    def handler(req: httpx.Request):
        body = json.loads(req.content) if req.content else None
        log.append((req.method, req.url.path, body))
        p = req.url.path
        if p.endswith("/query"):
            db = p.split("/")[3]
            res = {"buku": [halaman_buku()], "ide": [halaman_ide()], "reaksi": [halaman_reaksi()]}[db]
            return httpx.Response(200, json={"results": res, "has_more": False})
        if req.method == "POST" and p == "/v1/pages":
            return httpx.Response(200, json=halaman_ide())
        if req.method == "GET" and "/children" in p:
            return httpx.Response(200, json={"results": [
                {"id": "x", "type": "paragraph", "paragraph": {"rich_text": _rt("naskah lama")}}], "has_more": False})
        if req.method == "GET" and p.startswith("/v1/pages/"):
            return httpx.Response(200, json=halaman_buku())
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(base_url="https://api.notion.com/v1", transport=httpx.MockTransport(handler))
    cfg = type("C", (), dict(token="t", db_buku="buku", db_reaksi="reaksi", db_ide="ide",
                             db_pertanyaan="tanya", halaman_panduan="panduan"))()
    server._cfg, server._notion = cfg, Notion("t", client)


def test_alur_lengkap():
    log = []
    pasang(log)

    async def jalan():
        out = await server.bahan_buku("Laut Bercerita")
        assert "inget kakakku" in out and "id:abcd1234" in out
        out = await server.simpan_ide("Laut Bercerita", [server.IdeBaru(
            ide="Bab 2 dan kakakku", sudut="Momen Hidupku yang Nyambung", format="Reels", hook="Aku nangis")])
        assert "IDE-3" in out
        out = await server.lihat_ide("IDE-3")
        assert "Laut Bercerita" in out and "naskah lama" in out
        out = await server.simpan_naskah("IDE-3", "Aku baca ini pas di kereta. Jujur aku kesel.", ["abcd1234"])
        assert "Draft" in out and "LOLOS" in out

    asyncio.run(jalan())
    # unique_id filter memakai angka
    assert any(b and b.get("filter", {}).get("unique_id") == {"equals": 3} for _, _, b in log)
    # reaksi yang dipakai ditandai
    assert ("PATCH", f"/v1/pages/{REAKSI_ID}", {"properties": {"Dipakai": {"checkbox": True}}}) in log
