# Pojok Literasi

Sistem konten Instagram **Pojok Literasi** yang dibuat dari nol untuk dipakai bersama
oleh **kamu** (lewat dashboard web) dan **agent AI-mu** (lewat MCP di Claude Desktop).

- **Data milikmu sendiri**: satu file SQLite di komputermu. Tanpa Notion, tanpa akun pihak lain.
- **Hemat token**: agent memanggil tool yang ringkas, bukan computer use.
- **Satu kali pasang**: saat Claude Desktop dibuka, dashboard ikut menyala otomatis di
  http://localhost:8765

```
Claude Desktop ──MCP──► pojok-literasi ──► ~/PojokLiterasi/pojok-literasi.db
                              │
Browser (kamu) ◄──────────────┘  dashboard http://localhost:8765
```

## Fitur (Versi 1)

**Untuk kamu, di dashboard:**
| Fitur | Keterangan |
|---|---|
| Tangkap cepat | Kotak di atas setiap halaman. Pilih buku, ketik reaksi atau kutipan, lalu Enter |
| Rak buku | Status baca, rating, kesan singkat, beserta semua bahan dan ide per buku |
| Bank bahan | Reaksi, kutipan, dan cerita pribadi. Bisa dicari per kata, tema, atau jenis |
| Ide & Naskah | Papan kanban Ide → Wawancara → Draft → Siap → Posted, dengan 8 sudut konten |
| Editor naskah | Cek anti-AI langsung saat mengetik, hitung kata, dan riwayat versi (🤖 agent vs ✍️ kamu) |
| Kalender | Jadwal posting per bulan |
| Audiens | Pertanyaan dari komentar, DM, dan Story |
| Agent | Titip tugas untuk agent dan lihat hasilnya |
| Panduan Suara | Gaya bahasamu, dibaca agent setiap kali menulis |

**Untuk agent, lewat MCP:**
| Tool | Fungsi |
|---|---|
| `ringkasan_hari_ini` | Kondisi terkini + tugas titipan, cukup satu panggilan |
| `konteks_ide` | Ide, bahan buku, naskah, dan panduan suara sekaligus |
| `catat_bahan`, `bahan_buku`, `cari_bahan` | Bahan mentah |
| `simpan_ide`, `daftar_ide`, `ubah_ide` | Ide konten |
| `simpan_naskah` | Simpan sebagai versi "agent" + cek anti-AI otomatis |
| `pelajari_editan` | Bandingkan naskah agent dengan editanmu (hanya kalimat yang berubah) |
| `perbarui_panduan_suara`, `tandai_dipelajari` | Gaya tulisan makin mirip kamu |
| `selesaikan_tugas` | Menutup tugas yang kamu titipkan |
| `tambah_buku`, `update_buku`, `daftar_buku` | Rak buku |
| `catat_pertanyaan`, `pertanyaan_terbuka`, `jawab_pertanyaan` | Pertanyaan audiens |
| `cek_anti_ai` | Berjalan lokal, tanpa token |

**Prompt siap pakai.** Di kotak chat Claude Desktop, klik **+** lalu pilih **pojok-literasi**:
- `mulai_hari`: ringkasan kondisi + mengerjakan tugas titipan
- `cari_ide`: ide konten dari satu buku dengan 8 sudut
- `wawancara`: agent bertanya dulu, lalu menulis naskah hanya dari jawabanmu
- `belajar_gaya`: agent mempelajari editanmu dan mengusulkan pembaruan panduan suara

## Alur kerja harian

1. **Saat membaca**: catat reaksi lewat *Tangkap cepat* di dashboard, atau bilang ke Claude
   *"catat: bab 3 bikin aku kesel sama Biru Laut"*.
2. **Cari ide**: di Claude, jalankan prompt `cari_ide` lalu pilih ide yang kamu suka.
3. **Menulis**: jalankan prompt `wawancara` untuk ide yang dipilih. Agent bertanya, kamu bercerita, agent menyusun.
4. **Edit**: rapikan naskah di editor dashboard sampai cek anti-AI berwarna hijau.
5. **Belajar**: sesekali jalankan `belajar_gaya`, supaya draft berikutnya makin mirip gayamu.
6. **Jadwalkan**: atur tanggal posting di editor, lalu pantau di Kalender.

## Instalasi (sekali saja)

### 1. Pasang uv
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```
```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone repo
```bash
git clone https://github.com/ragelardiyan62-bot/pojok-literasi-mcp.git
```

### 3. Daftarkan ke Claude Desktop
Buka **Settings → Developer → Edit Config** (`claude_desktop_config.json`), lalu tambahkan:

```json
{
  "mcpServers": {
    "pojok-literasi": {
      "command": "uv",
      "args": ["--directory", "/PATH/KE/pojok-literasi-mcp", "run", "pojok-literasi-mcp"]
    }
  }
}
```
- Di Windows, tulis path dengan `\\`, misalnya `C:\\Users\\kamu\\pojok-literasi-mcp`.
- Kalau Claude Desktop tidak menemukan `uv`, isi `"command"` dengan path lengkapnya (`which uv` / `where uv`).

Setelah itu restart Claude Desktop, lalu buka http://localhost:8765.

### Pengaturan opsional (`"env"` di config)
| Variabel | Default | Fungsi |
|---|---|---|
| `POJOK_DB` | `~/PojokLiterasi/pojok-literasi.db` | Lokasi file data |
| `POJOK_PORT` | `8765` | Port dashboard |
| `POJOK_WEB` | `1` | Isi `0` untuk tidak menyalakan dashboard otomatis |

Dashboard juga bisa dijalankan tanpa Claude Desktop:
```bash
uv run pojok-literasi-web
```

## Backup
Semua data ada di **satu file**, `~/PojokLiterasi/pojok-literasi.db`. Salin file itu ke Google Drive
atau flashdisk secara berkala. Ekspor JSON juga tersedia di http://localhost:8765/api/ekspor

## Pengembangan
```bash
uv sync
uv run pytest
```
