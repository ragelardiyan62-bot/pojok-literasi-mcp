"""Klien Notion minimal: hanya endpoint yang dibutuhkan, output diringkas."""

from __future__ import annotations

import os
from typing import Any

import httpx

API = "https://api.notion.com/v1"
VERSI_API = "2022-06-28"


class Konfigurasi:
    def __init__(self) -> None:
        def wajib(nama: str) -> str:
            nilai = os.environ.get(nama, "").strip()
            if not nilai:
                raise RuntimeError(f"Environment variable {nama} belum diisi (lihat README).")
            return nilai

        self.token = wajib("NOTION_TOKEN")
        self.db_buku = wajib("NOTION_DB_BUKU")
        self.db_reaksi = wajib("NOTION_DB_REAKSI")
        self.db_ide = wajib("NOTION_DB_IDE")
        self.db_pertanyaan = wajib("NOTION_DB_PERTANYAAN")
        self.halaman_panduan = wajib("NOTION_PAGE_PANDUAN")


class Notion:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._http = client or httpx.AsyncClient(
            base_url=API,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": VERSI_API,
                "Content-Type": "application/json",
            },
        )

    async def _req(self, metode: str, path: str, json: dict | None = None) -> dict:
        r = await self._http.request(metode, path, json=json)
        if r.status_code >= 400:
            try:
                pesan = r.json().get("message", r.text)
            except ValueError:
                pesan = r.text
            raise RuntimeError(f"Notion {r.status_code}: {pesan}")
        return r.json()

    async def query(self, db: str, filter: dict | None = None, sorts: list | None = None,
                    batas: int = 50) -> list[dict]:
        hasil: list[dict] = []
        body: dict[str, Any] = {"page_size": min(batas, 100)}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        while True:
            data = await self._req("POST", f"/databases/{db}/query", body)
            hasil.extend(data["results"])
            if not data.get("has_more") or len(hasil) >= batas:
                return hasil[:batas]
            body["start_cursor"] = data["next_cursor"]

    async def buat(self, db: str, properti: dict, isi: list[dict] | None = None) -> dict:
        body: dict[str, Any] = {"parent": {"database_id": db}, "properties": properti}
        if isi:
            body["children"] = isi
        return await self._req("POST", "/pages", body)

    async def ubah(self, halaman: str, properti: dict) -> dict:
        return await self._req("PATCH", f"/pages/{halaman}", {"properties": properti})

    async def tambah_blok(self, halaman: str, blok: list[dict]) -> None:
        for i in range(0, len(blok), 100):
            await self._req("PATCH", f"/blocks/{halaman}/children", {"children": blok[i:i + 100]})

    async def hapus_isi(self, halaman: str) -> None:
        data = await self._req("GET", f"/blocks/{halaman}/children?page_size=100")
        for b in data["results"]:
            await self._req("DELETE", f"/blocks/{b['id']}")

    async def teks_halaman(self, halaman: str) -> str:
        baris: list[str] = []
        cursor = None
        while True:
            q = f"/blocks/{halaman}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            data = await self._req("GET", q)
            for b in data["results"]:
                t = b["type"]
                rt = b.get(t, {}).get("rich_text")
                if rt is None:
                    continue
                teks = polos(rt)
                awalan = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
                          "bulleted_list_item": "- ", "numbered_list_item": "1. ",
                          "to_do": "- [ ] ", "quote": "> "}.get(t, "")
                baris.append(awalan + teks)
            if not data.get("has_more"):
                return "\n".join(baris).strip()
            cursor = data["next_cursor"]


# ---------- helper properti ----------

def polos(rich_text: list[dict]) -> str:
    return "".join(x.get("plain_text", "") for x in rich_text)


def p_judul(teks: str) -> dict:
    return {"title": [{"text": {"content": teks[:2000]}}]}


def p_teks(teks: str) -> dict:
    return {"rich_text": [{"text": {"content": teks[:2000]}}]}


def p_pilih(nama: str) -> dict:
    return {"select": {"name": nama}}


def p_status(nama: str) -> dict:
    return {"status": {"name": nama}}


def p_multi(nama: list[str]) -> dict:
    return {"multi_select": [{"name": n} for n in nama]}


def p_relasi(ids: list[str]) -> dict:
    return {"relation": [{"id": i} for i in ids]}


def p_tanggal(iso: str) -> dict:
    return {"date": {"start": iso}}


def ambil(halaman: dict, nama: str) -> Any:
    """Ambil nilai properti sebagai tipe Python sederhana."""
    p = halaman["properties"].get(nama)
    if p is None:
        return None
    t = p["type"]
    v = p[t]
    if t in ("title", "rich_text"):
        return polos(v)
    if t in ("select", "status"):
        return v["name"] if v else None
    if t == "multi_select":
        return [x["name"] for x in v]
    if t == "relation":
        return [x["id"] for x in v]
    if t == "date":
        return v["start"] if v else None
    if t == "unique_id":
        return f"{v['prefix']}-{v['number']}" if v.get("prefix") else v["number"]
    if t == "checkbox":
        return v
    return v


def paragraf(teks: str) -> list[dict]:
    """Ubah teks multi-baris menjadi blok paragraf Notion (maks 2000 char/blok)."""
    blok = []
    for baris in teks.split("\n"):
        while True:
            potong, baris = baris[:2000], baris[2000:]
            blok.append({"object": "block", "type": "paragraph",
                         "paragraph": {"rich_text": [{"text": {"content": potong}}] if potong else []}})
            if not baris:
                break
    return blok
