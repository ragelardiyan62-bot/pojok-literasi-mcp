"""Pemeriksa naskah 'terdengar seperti AI' berbasis aturan.

Berjalan lokal tanpa LLM, jadi tidak memakan token model sama sekali.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (pola regex, alasan). Pola dicocokkan tanpa membedakan huruf besar/kecil.
FRASA_TERLARANG: list[tuple[str, str]] = [
    (r"\bdi era (digital|modern|sekarang) ini\b", "pembuka klise khas AI"),
    (r"\bmari kita (selami|jelajahi|bahas bersama)\b", "ajakan klise khas AI"),
    (r"\bmenyelami\b", "kata favorit AI"),
    (r"\bpermata tersembunyi\b", "frasa klise terjemahan 'hidden gem'"),
    (r"\bperjalanan (emosional|yang penuh makna)\b", "frasa klise"),
    (r"\bdalam lanskap\b", "kata favorit AI"),
    (r"\btak terlupakan\b", "pujian generik"),
    (r"\bmemikat hati\b", "pujian generik"),
    (r"\bpada akhirnya,", "penutup klise"),
    (r"\bkesimpulannya,", "penutup klise"),
    (r"^\s*jadi,", "penutup/pembuka 'Jadi,' yang terasa template"),
    (r"\bsecara keseluruhan\b", "penutup klise"),
    (r"\bbukan sekadar\b.*\bmelainkan\b", "struktur 'bukan sekadar... melainkan' khas AI"),
    (r"\bhal ini (menunjukkan|membuktikan)\b", "nada laporan, bukan ngobrol"),
    (r"\bsangat (direkomendasikan|layak dibaca)\b", "rekomendasi generik tanpa alasan"),
]

PENANDA_PRIBADI = re.compile(
    r"\b(aku|saya|gue|gw|ku|kemarin|waktu itu|pas lagi|minggu lalu|tahun lalu|dulu)\b",
    re.IGNORECASE,
)
PENANDA_OPINI = re.compile(
    r"\b(menurutku|menurut aku|menurut saya|jujur|nggak setuju|ga setuju|tidak setuju|"
    r"kesel|kecewa|overrated|underrated|sebel|bingung)\b",
    re.IGNORECASE,
)
PEMBUKA_BASA_BASI = re.compile(
    r"^\s*(halo|hai|hi)\b.*(teman|semua|guys)|^\s*(kali ini|pada kesempatan ini)",
    re.IGNORECASE,
)


@dataclass
class Temuan:
    tingkat: str  # "merah" = wajib diganti, "kuning" = pertimbangkan
    pesan: str


def periksa(naskah: str) -> list[Temuan]:
    temuan: list[Temuan] = []
    teks = naskah.strip()

    for baris in teks.splitlines():
        for pola, alasan in FRASA_TERLARANG:
            m = re.search(pola, baris, re.IGNORECASE)
            if m:
                temuan.append(Temuan("merah", f'"{m.group(0).strip()}": {alasan}'))

    em_dash = teks.count("—")
    if em_dash >= 2:
        temuan.append(Temuan("kuning", f"{em_dash} tanda pisah panjang (—); ganti dengan koma/titik"))

    tidak_hanya = len(re.findall(r"\btidak hanya\b", teks, re.IGNORECASE))
    if tidak_hanya >= 2:
        temuan.append(Temuan("kuning", f"'tidak hanya ... tetapi juga' dipakai {tidak_hanya}x"))

    baris_pertama = next((b for b in teks.splitlines() if b.strip()), "")
    if PEMBUKA_BASA_BASI.search(baris_pertama):
        temuan.append(Temuan("kuning", "kalimat pertama basa-basi; langsung ke inti/hook"))

    if not PENANDA_PRIBADI.search(teks):
        temuan.append(Temuan("merah", "tidak ada detail pribadi (aku/kapan/di mana)"))
    if not PENANDA_OPINI.search(teks):
        temuan.append(Temuan("kuning", "tidak terlihat opini pribadi yang tegas"))

    kalimat = [k for k in re.split(r"[.!?]+\s", teks) if k.strip()]
    if kalimat:
        rata = sum(len(k.split()) for k in kalimat) / len(kalimat)
        if rata > 22:
            temuan.append(Temuan("kuning", f"kalimat rata-rata {rata:.0f} kata; terlalu panjang untuk gaya ngobrol"))

    return temuan


def ringkas(temuan: list[Temuan]) -> str:
    if not temuan:
        return "LOLOS: tidak ada ciri tulisan AI yang terdeteksi."
    merah = sum(1 for t in temuan if t.tingkat == "merah")
    kepala = "PERLU REVISI" if merah else "CUKUP, tapi bisa lebih baik"
    isi = "\n".join(f"- [{t.tingkat}] {t.pesan}" for t in temuan)
    return f"{kepala} ({merah} merah, {len(temuan) - merah} kuning)\n{isi}"
