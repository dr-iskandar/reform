# ReForm — Local VLM → Excel → Master Data Comparison

ReForm adalah sample app untuk workflow dokumen berikut:

1. **Membaca softfile** (PDF / image) menggunakan VLM lokal.
2. **Populate hasil ekstraksi menjadi Excel**.
3. **Membandingkan hasil tersebut dengan master data** Excel/CSV.
4. User menentukan **index field** yang dipakai untuk mencari record yang sama.
5. Output berupa **Excel hasil comparison** dengan tambahan kolom:
   - `STATUS`
   - `DIFFERENT_FIELDS`

Status utama:
- `SAME` — record ditemukan di master dan semua common field sama.
- `DIFFERENT` — record ditemukan tetapi minimal satu field berbeda.
- `NOT_FOUND` — nilai index dari hasil VLM tidak ditemukan di master.
- `INDEX_EMPTY` — index field pada hasil VLM kosong.

## Flow

```
Softfile PDF/Image
        |
        v
Local VLM (Ollama)
        |
        v
Structured records
        |
        v
Generated Excel
        |
        | index field
        v
Master Excel / CSV
        |
        v
Comparison Engine
        |
        v
Result Excel
  + STATUS
  + DIFFERENT_FIELDS
        |
        +--> Detail sheet
        +--> Summary sheet
```

Comparison hanya membandingkan field dengan **nama kolom yang sama** antara generated data dan master data. Index field dipakai untuk lookup record dan tidak ikut dinilai sebagai field comparison.

## Local VLM

Default model:

```bash
qwen2.5vl:7b
```

Konfigurasi ada di `.env.example`:

```bash
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5vl:7b
MAX_PAGES=8
```

## Setup

```bash
git clone https://github.com/dr-iskandar/reform.git
cd reform

ollama pull qwen2.5vl:7b
ollama serve
```

Terminal lain:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Buka:

```
http://localhost:8000
```

## Output Excel

### Sheet `Result`
Berisi data hasil VLM dengan tambahan:

| ...generated columns | STATUS | DIFFERENT_FIELDS |
|---|---|---|
| ... | SAME | |
| ... | DIFFERENT | latitude, job_status |
| ... | NOT_FOUND | |

### Sheet `Detail`
Audit per field:

| index_value | field | generated_value | master_value | status |
|---|---|---|---|---|

### Sheet `Summary`
Jumlah SAME, DIFFERENT, NOT_FOUND, INDEX_EMPTY, dan statistik lainnya.

## Catatan MVP

Saat ini matching mengharuskan nama `index_field` sama di generated data dan master. Field yang dibandingkan juga menggunakan nama kolom yang sama.

Next step yang cocok untuk production:
- field mapping jika nama kolom berbeda,
- tolerance per field (mis. koordinat, nominal, tanggal),
- confidence VLM,
- evidence page/bounding box,
- batch banyak softfile,
- review queue untuk hasil berbeda,
- audit trail.
