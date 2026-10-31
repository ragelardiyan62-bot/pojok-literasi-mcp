"""Dashboard web lokal: JSON API + satu halaman HTML."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from . import anti_ai, db as dbmod
from .db import DB, GagalValidasi

STATIC = Path(__file__).parent / "static"


def buat_app(db: DB) -> Starlette:
    def ok(data=None, status: int = 200) -> JSONResponse:
        return JSONResponse(data if data is not None else {"ok": True}, status_code=status)

    def api(fn):
        async def handler(req: Request):
            try:
                body = {}
                if req.method in ("POST", "PATCH", "PUT"):
                    raw = await req.body()
                    body = json.loads(raw) if raw else {}
                return ok(fn(req, body))
            except GagalValidasi as e:
                return ok({"error": str(e)}, 400)
            except (ValueError, KeyError, TypeError) as e:
                return ok({"error": f"Input tidak valid: {e}"}, 400)
        return handler

    pid = lambda r, k="id": int(r.path_params[k])

    async def index(_req: Request) -> Response:
        return FileResponse(STATIC / "index.html")

    routes = [
        Route("/", index),
        Route("/api/meta", api(lambda r, b: {
            "status_buku": dbmod.STATUS_BUKU, "status_ide": dbmod.STATUS_IDE, "jenis": dbmod.JENIS_BAHAN,
            "format": dbmod.FORMAT, "sudut": dbmod.SUDUT, "sumber": dbmod.SUMBER,
            "tema": db.semua_tema(), "lokasi_db": str(db.path)})),
        Route("/api/ringkasan", api(lambda r, b: db.ringkasan())),

        Route("/api/buku", api(lambda r, b: db.daftar_buku(r.query_params.get("status") or None))),
        Route("/api/buku", api(lambda r, b: db.tambah_buku(b["judul"], b.get("penulis", ""),
                                                           b.get("status", "Mau Dibaca"), b.get("genre"))),
              methods=["POST"]),
        Route("/api/buku/{id:int}", api(lambda r, b: {**db.buku(pid(r)), "bahan": db.bahan_buku(pid(r)),
                                                     "ide": db.daftar_ide(buku_id=pid(r))})),
        Route("/api/buku/{id:int}", api(lambda r, b: db.ubah_buku(pid(r), **b)), methods=["PATCH"]),
        Route("/api/buku/{id:int}", api(lambda r, b: db.hapus_buku(pid(r)) or {"ok": True}), methods=["DELETE"]),

        Route("/api/bahan", api(lambda r, b: db.cari_bahan(r.query_params.get("kata", ""),
                                                           r.query_params.get("tema", ""),
                                                           r.query_params.get("jenis", "")))),
        Route("/api/bahan", api(lambda r, b: db.catat_bahan(int(b["buku_id"]), b["isi"], b.get("jenis", "Reaksi"),
                                                            b.get("lokasi", ""), b.get("tema"))),
              methods=["POST"]),
        Route("/api/bahan/{id:int}", api(lambda r, b: db.ubah_bahan(pid(r), **b)), methods=["PATCH"]),
        Route("/api/bahan/{id:int}", api(lambda r, b: db.hapus_bahan(pid(r)) or {"ok": True}), methods=["DELETE"]),

        Route("/api/ide", api(lambda r, b: db.daftar_ide(r.query_params.get("status") or None, batas=500))),
        Route("/api/ide", api(lambda r, b: db.tambah_ide(b["judul"], b.get("buku_id") or None, b.get("sudut", ""),
                                                         b.get("format", "Carousel"), b.get("hook", ""))),
              methods=["POST"]),
        Route("/api/ide/{id:int}", api(lambda r, b: {**db.ide(pid(r)), "versi": db.versi_naskah(pid(r))})),
        Route("/api/ide/{id:int}", api(lambda r, b: db.ubah_ide(pid(r), **b)), methods=["PATCH"]),
        Route("/api/ide/{id:int}", api(lambda r, b: db.hapus_ide(pid(r)) or {"ok": True}), methods=["DELETE"]),
        Route("/api/ide/{id:int}/naskah", api(lambda r, b: db.simpan_naskah(pid(r), b["naskah"], oleh="kamu")),
              methods=["POST"]),
        Route("/api/kalender", api(lambda r, b: db.kalender(r.query_params["bulan"]))),

        Route("/api/pertanyaan", api(lambda r, b: db.daftar_pertanyaan(r.query_params.get("semua") != "1"))),
        Route("/api/pertanyaan", api(lambda r, b: db.catat_pertanyaan(b["isi"], b.get("sumber", "Komentar"))),
              methods=["POST"]),
        Route("/api/pertanyaan/{id:int}", api(lambda r, b: db.tandai_pertanyaan(pid(r), b.get("dijawab", True))
                                              or {"ok": True}), methods=["PATCH"]),

        Route("/api/tugas", api(lambda r, b: db.daftar_tugas())),
        Route("/api/tugas", api(lambda r, b: db.titip_tugas(b["permintaan"])), methods=["POST"]),

        Route("/api/panduan", api(lambda r, b: {"teks": db.panduan_suara()})),
        Route("/api/panduan", api(lambda r, b: db.simpan_panduan_suara(b["teks"]) or {"ok": True}),
              methods=["PUT"]),

        Route("/api/cek", api(lambda r, b: {
            "ringkas": anti_ai.ringkas(t := anti_ai.periksa(b.get("naskah", ""))),
            "temuan": [{"tingkat": x.tingkat, "pesan": x.pesan} for x in t]}), methods=["POST"]),
        Route("/api/template", api(lambda r, b: db.template())),
        Route("/api/template/{format}", api(lambda r, b: db.simpan_template(r.path_params["format"], b["kerangka"])
                                            or {"ok": True}), methods=["PUT"]),
        Route("/api/statistik", api(lambda r, b: db.statistik(r.query_params.get("mulai") or None,
                                                             r.query_params.get("selesai") or None))),
        Route("/api/hook", api(lambda r, b: db.hook_terbukti(20))),
        Route("/api/laporan", api(lambda r, b: db.laporan(r.query_params["mulai"], r.query_params["selesai"]))),
        Route("/api/ekspor", api(lambda r, b: db.ekspor())),
    ]
    return Starlette(routes=routes)


def main() -> None:
    """Jalankan dashboard saja (tanpa MCP), mis. untuk dipakai tanpa Claude Desktop."""
    import os
    import webbrowser

    import uvicorn

    port = int(os.environ.get("POJOK_PORT", "8765"))
    print(f"Dashboard Pojok Literasi: http://localhost:{port}  (Ctrl+C untuk berhenti)")
    webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(buat_app(DB()), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
