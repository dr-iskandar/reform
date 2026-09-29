# ReForm — Local VLM Document Comparator

MVP untuk membaca softcopy dokumen menggunakan **Vision Language Model lokal**, mengubah isi dokumen menjadi data terstruktur, lalu membandingkannya dengan:

1. **Master data** dalam CSV/XLSX, atau
2. **Dokumen lain** (PDF / image) yang juga diekstrak oleh VLM.

Semua inference VLM berjalan lewat **Ollama lokal**. Dokumen tidak perlu dikirim ke cloud.

## Flow

```
Document A (PDF/Image)
        |
        v
Local VLM via Ollama
        |
        v
Structured JSON
        |
        +----------------------+
        |                      |
        v                      v
Master CSV/XLSX          Document B
                               |
                               v
                         Local VLM
                               |
                               v
                         Structured JSON
        |                      |
        +----------+-----------+
                   v
             Comparison Engine
                   |
                   v
       Match / Near match / Mismatch
                   |
                   v
              Export Excel
```

## Model

Default:

```bash
qwen2.5vl:7b
```

Model dapat diganti melalui environment variable, misalnya:

```bash
export OLLAMA_MODEL=gemma3:4b
```

Untuk dokumen, tabel, tulisan kecil, dan OCR-like extraction, gunakan model vision yang cukup kuat dan sesuaikan dengan GPU/RAM yang tersedia.

## Setup

Pastikan Ollama sudah terpasang dan berjalan.

```bash
ollama pull qwen2.5vl:7b
ollama serve
```

Buat virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Jalankan aplikasi:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Buka:

```
http://localhost:8000
```

## Cara pakai

- Upload **Dokumen Sumber**.
- Opsional isi **Schema / field hint**, misalnya:
  `kota, kecamatan, kelurahan, latitude, longitude, tanggal, ts_name`.
- Klik **Extract dengan VLM**.
- Upload file pembanding:
  - CSV/XLSX = dianggap sebagai master data.
  - PDF/JPG/PNG = dianggap sebagai Document B dan diekstrak oleh VLM.
- Opsional isi **Match key**, misalnya `id`, `ts_name`, atau nomor dokumen.
- Klik **Compare**.
- Hasil dapat diexport menjadi Excel.

## Status comparison

- `match`: nilai sama.
- `near_match`: nilai sangat mirip.
- `mismatch`: nilai berbeda.
- `missing`: salah satu sisi kosong.
- `empty`: kedua sisi kosong.

## Struktur

```
backend/
  main.py        FastAPI endpoints
  vlm.py         Ollama + VLM extraction
  document.py    PDF/image rendering
  compare.py     matching & comparison engine

static/
  index.html
  app.js
  styles.css
```

## Scope MVP

Saat ini input dokumen vision mendukung PDF dan image. Master data mendukung CSV dan XLSX.

Tahap selanjutnya yang masuk akal untuk production:
- schema extraction per jenis dokumen,
- confidence/evidence per field,
- bounding box / source page evidence,
- field mapping master-data vs dokumen,
- batch processing banyak file,
- review queue untuk field confidence rendah,
- audit trail hasil VLM,
- database master data,
- rule engine untuk toleransi numeric/date,
- model fallback atau OCR+VLM hybrid.
