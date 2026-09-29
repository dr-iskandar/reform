# ReForm — Local VLM → Excel → Elastic Master Comparison

Workflow:

1. Softfile PDF/image dibaca oleh VLM lokal.
2. Hasil extraction menjadi structured records dan dapat diexport ke Excel.
3. Master data dimuat dari Excel/CSV.
4. User menentukan index field.
5. Comparison engine melakukan **elastic mapping**:
   - nama header tidak perlu identik,
   - index string boleh memiliki typo ringan,
   - tanggal dinormalisasi,
   - angka memakai tolerance,
   - latitude/longitude memakai tolerance kecil,
   - text comparison memakai fuzzy similarity.
6. Output Excel ditambah `MATCHED_MASTER_INDEX`, `MATCH_SCORE`, `STATUS`, dan `DIFFERENT_FIELDS`.

## Contoh field elastic

`TS_NAME`, `TS Name`, dan `ts-name` diperlakukan sebagai field yang sama.

Generated:

| TS Name | Longitude | Job Status |
|---|---:|---|
| Ria Subekti | 106.62358 | Done |

Master:

| TS_NAME | LONGITUDE | JOB_STATUS |
|---|---:|---|
| RIA SUBEKTI | 106.62360 | Done |

Engine akan memetakan header dan melakukan type-aware comparison tanpa mewajibkan string literal yang 100% identik.

## Status

- `SAME`: record ditemukan dan seluruh mapped fields dianggap sama dalam aturan elastic.
- `DIFFERENT`: record ditemukan tetapi ada minimal satu field yang benar-benar berbeda.
- `NOT_FOUND`: tidak ada kandidat master dengan index similarity yang cukup.
- `INDEX_EMPTY`: index hasil VLM kosong.
- `NOT_COMPARABLE`: index field tidak dapat dipetakan ke salah satu file.

## Default threshold

- Header similarity: 72%
- Index fuzzy similarity: 82%
- Text value similarity: 90%
- Coordinate tolerance: 0.0002 degree
- Numeric tolerance: max(0.01, 0.1%)

Nilai ini ada di `backend/compare.py` dan mudah diubah sesuai karakter data riil.

## Local VLM

Default:

```bash
qwen2.5vl:7b
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
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Buka `http://localhost:8000`.

## Excel output

- `Result`: generated data + match/status columns.
- `Detail`: audit per mapped field, termasuk generated/master field, score, dan comparison mode.
- `Summary`: rekap hasil.
