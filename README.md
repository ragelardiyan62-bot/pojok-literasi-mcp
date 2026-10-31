# Pojok Literasi MCP

MCP server untuk mengelola sistem konten Instagram **Pojok Literasi** dari Claude Desktop.
Datanya disimpan di Notion, dan agent cukup memanggil *tool* yang spesifik, tidak perlu computer use.
Hasil setiap tool berupa teks ringkas (bukan JSON mentah Notion) agar hemat token.

## Tools

| Tool | Fungsi |
|---|---|
| `tambah_buku`, `update_buku`, `daftar_buku` | Rak buku |
| `catat_reaksi` | Simpan kutipan, reaksi, atau cerita pribadi saat membaca |
| `bahan_buku` | Semua bahan mentah satu buku dalam format ringkas |
| `simpan_ide`, `daftar_ide`, `lihat_ide` | Ide konten (8 sudut) |
| `simpan_naskah` | Simpan naskah, status jadi Draft, lalu cek anti-AI otomatis |
| `ubah_status_ide` | Ide → Wawancara → Draft → Siap → Posted, plus jadwal posting |
| `catat_pertanyaan`, `pertanyaan_terbuka` | Pertanyaan dari audiens |
| `panduan_suara` | Panduan gaya bahasamu (di-cache 10 menit) |
| `cek_anti_ai` | Deteksi ciri tulisan AI, **berjalan lokal tanpa token LLM** |

Prompt: **`wawancara`**. AI mewawancaraimu dulu, lalu menyusun naskah hanya dari jawabanmu.

## Struktur Notion

Sudah dibuat di halaman **Pojok Literasi**:
- **Buku**
- **Reaksi & Kutipan** (terhubung ke Buku)
- **Ide Konten** (terhubung ke Buku, Reaksi, dan Pertanyaan)
- **Pertanyaan Audiens**
- Halaman **Panduan Suara**: isi dengan gaya bahasamu sendiri

## Instalasi (sekali saja)

### 1. Buat integrasi Notion
1. Buka https://www.notion.so/profile/integrations, pilih **New integration** (tipe *Internal*), lalu salin token-nya (`ntn_...`).
2. Di Notion, buka halaman **Pojok Literasi**, klik `•••`, pilih **Connections**, lalu tambahkan integrasi tadi.
   Semua database di bawah halaman itu otomatis ikut bisa diakses.

### 2. Pasang uv dan clone repo
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

git clone https://github.com/<username>/pojok-literasi-mcp.git
```

### 3. Daftarkan ke Claude Desktop
Buka **Settings → Developer → Edit Config** (`claude_desktop_config.json`), lalu tambahkan:

```json
{
  "mcpServers": {
    "pojok-literasi": {
      "command": "uv",
      "args": ["--directory", "/PATH/KE/pojok-literasi-mcp", "run", "pojok-literasi-mcp"],
      "env": {
        "NOTION_TOKEN": "ntn_xxx",
        "NOTION_DB_BUKU": "9ced8d08d5f1447397d16688a265e467",
        "NOTION_DB_REAKSI": "ad96488e30f14718b8715f8769dc81f7",
        "NOTION_DB_IDE": "94228d2a8e5b4c01962f71fe766008ca",
        "NOTION_DB_PERTANYAAN": "170a915a966a436a934442fcfc1e298a",
        "NOTION_PAGE_PANDUAN": "40aed62316e781e28e41c957e48fce74"
      }
    }
  }
}
```
Di Windows, tulis path dengan `\\`, misalnya `C:\\Users\\kamu\\pojok-literasi-mcp`.
Kalau Claude Desktop tidak menemukan `uv`, ganti `"command"` dengan path lengkapnya (cek dengan `which uv` atau `where uv`).

Setelah itu restart Claude Desktop. Tools di atas akan muncul di ikon 🔨.

> Kalau kamu juga mengaktifkan konektor Notion bawaan Claude, sebaiknya matikan saja untuk chat konten
> supaya agent memakai tool yang ringkas ini dan tidak menghabiskan token.

## Contoh pemakaian di Claude Desktop

- "Aku mulai baca *Laut Bercerita* karya Leila S. Chudori."
- "Catat reaksi: bab 2 bikin aku inget kakakku waktu kuliah di Jogja."
- "Dari bahan *Laut Bercerita*, kasih 5 ide konten, simpan yang aku pilih."
- Gunakan prompt **wawancara** dengan kode `IDE-3`.
- "Ide apa saja yang masih Draft?"

## Pengembangan

```bash
uv sync
uv run pytest
```
