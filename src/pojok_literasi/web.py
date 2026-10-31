"""Dashboard web lokal: JSON API + satu halaman HTML."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import time
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from . import anti_ai, db as dbmod
from .db import DB, GagalValidasi
from datetime import date

STATIC = Path(__file__).parent / "static"
LOKAL = {"127.0.0.1", "::1", "localhost", "testclient"}
PENGATURAN_BOLEH = {"handle_ig"}

HALAMAN_MASUK = """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Masuk · Pojok Literasi</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f4ee;color:#2b2620;
font:16px system-ui,sans-serif}form{background:#fff;padding:28px;border-radius:14px;width:min(320px,90vw);
box-shadow:0 2px 12px rgba(0,0,0,.08)}h1{font-size:20px;color:#9a4a2b;margin:0 0 16px}input{width:100%;
box-sizing:border-box;font-size:22px;letter-spacing:6px;text-align:center;padding:10px;border:1px solid #e6dfd3;
border-radius:8px}button{width:100%;margin-top:12px;padding:12px;border:0;border-radius:8px;background:#9a4a2b;
color:#fff;font-size:16px;font-weight:600}p{color:#b3362b;font-size:14px;min-height:1em}
@media(prefers-color-scheme:dark){body{background:#1b1916;color:#ece6dc}form{background:#24211d}
input{background:#1b1916;color:#ece6dc;border-color:#3a352e}}</style></head><body>
<form method="post" action="/masuk"><h1>📚 Pojok Literasi</h1><input name="pin" type="password"
inputmode="numeric" autocomplete="current-password" placeholder="PIN" autofocus required><p>{pesan}</p>
<button>Masuk</button></form></body></html>"""


def ip_lan() -> str | None:
    """Alamat IP komputer ini di jaringan WiFi (tanpa mengirim data ke internet)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def pin_dari_env() -> str | None:
    pin = os.environ.get("POJOK_PIN", "").strip()
    if pin and len(pin) < 6:
        raise SystemExit("POJOK_PIN minimal 6 karakter.")
    return pin or None


class PenjagaPIN(BaseHTTPMiddleware):
    """Akses dari komputer sendiri selalu boleh. Akses dari perangkat lain (HP) wajib PIN."""

    def __init__(self, app, pin: str | None):
        super().__init__(app)
        self.pin = pin
        self.rahasia = secrets.token_bytes(32)
        self.gagal: dict[str, list[float]] = {}

    def token(self) -> str:
        return hmac.new(self.rahasia, (self.pin or "").encode(), hashlib.sha256).hexdigest()

    async def dispatch(self, req: Request, call_next):
        host = req.client.host if req.client else ""
        if host in LOKAL:
            return await call_next(req)
        if not self.pin:
            return Response("Akses dari perangkat lain belum diaktifkan.", status_code=403)
        if req.url.path == "/masuk":
            if req.method == "GET":
                return HTMLResponse(HALAMAN_MASUK.replace("{pesan}", ""))
            sekarang = time.time()
            riwayat = [t for t in self.gagal.get(host, []) if sekarang - t < 300]
            if len(riwayat) >= 5:
                return HTMLResponse(HALAMAN_MASUK.replace("{pesan}", "Terlalu banyak percobaan. Tunggu 5 menit."), 429)
            pin = (await req.form()).get("pin", "")
            if hmac.compare_digest(str(pin).encode(), self.pin.encode()):
                self.gagal.pop(host, None)
                res = RedirectResponse("/", status_code=303)
                res.set_cookie("pojok_sesi", self.token(), max_age=60 * 60 * 24 * 30, httponly=True, samesite="strict")
                return res
            self.gagal[host] = riwayat + [sekarang]
            return HTMLResponse(HALAMAN_MASUK.replace("{pesan}", "PIN salah."), 401)
        if hmac.compare_digest(req.cookies.get("pojok_sesi", ""), self.token()):
            return await call_next(req)
        if req.url.path.startswith("/api/"):
            return JSONResponse({"error": "Perlu masuk dengan PIN."}, status_code=401)
        return RedirectResponse("/masuk", status_code=303)


def buat_app(db: DB, pin: str | None = None) -> Starlette:
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

        Route("/api/momen", api(lambda r, b: db.daftar_momen())),
        Route("/api/momen", api(lambda r, b: db.tambah_momen(b["tanggal"], b["nama"], b.get("catatan", ""))),
              methods=["POST"]),
        Route("/api/momen/{id:int}", api(lambda r, b: db.hapus_momen(pid(r)) or {"ok": True}), methods=["DELETE"]),
        Route("/api/momen/rentang", api(lambda r, b: db.momen_antara(date.fromisoformat(r.query_params["mulai"]),
                                                                     date.fromisoformat(r.query_params["selesai"])))),
        Route("/api/bahan/{id:int}", api(lambda r, b: db.bahan(pid(r)))),
        Route("/api/pengaturan", api(lambda r, b: {k: db.pengaturan(k) for k in PENGATURAN_BOLEH})),
        Route("/api/pengaturan", api(lambda r, b: [db.simpan_pengaturan(k, str(v)) for k, v in b.items()
                                                   if k in PENGATURAN_BOLEH] and {"ok": True}), methods=["PUT"]),
        Route("/api/akses", api(lambda r, b: {
            "hp_aktif": bool(pin), "ip": ip_lan(), "port": r.url.port or 80,
            "dari_hp": (r.client.host if r.client else "") not in LOKAL})),
    ]
    return Starlette(routes=routes, middleware=[Middleware(PenjagaPIN, pin=pin)])


def host_server(pin: str | None) -> str:
    """Kalau PIN diatur, dashboard bisa dibuka dari HP di WiFi yang sama."""
    return "0.0.0.0" if pin else "127.0.0.1"


def main() -> None:
    """Jalankan dashboard saja (tanpa MCP), mis. untuk dipakai tanpa Claude Desktop."""
    import webbrowser

    import uvicorn

    port = int(os.environ.get("POJOK_PORT", "8765"))
    pin = pin_dari_env()
    print(f"Dashboard Pojok Literasi: http://localhost:{port}  (Ctrl+C untuk berhenti)")
    if pin and ip_lan():
        print(f"Dari HP (WiFi yang sama): http://{ip_lan()}:{port}")
    webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(buat_app(DB(), pin), host=host_server(pin), port=port, log_level="warning")


if __name__ == "__main__":
    main()
