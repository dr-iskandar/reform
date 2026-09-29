# ReForm — Local VLM → Excel → Domain-aware Elastic Comparison

ReForm membaca softfile memakai VLM lokal, menghasilkan data Excel, lalu merekonsiliasi hasil tersebut dengan master Excel/CSV.

## Flow

```
PDF / image
    ↓
Local VLM
    ↓
Generated records / Excel
    ↓
Index + semantic normalization
    ↓
Master Excel / CSV
    ↓
Domain-aware comparison
    ↓
Result Excel
```

## Elastic comparison

Engine sekarang tidak hanya melakukan fuzzy string matching.

### 1. Semantic header mapping

Contoh berikut dipetakan sebagai field yang sama:

- `date` ↔ `Visit Date`
- `time` ↔ `Visit Hours`
- `longitude` ↔ `Longitude`
- `latitude` ↔ `Latitude`
- `status` ↔ `Job Status`
- `TS_NAME` ↔ `TS Name`

### 2. Coordinate normalization

Kasus spreadsheet seperti:

```
Generated latitude : -6.3279018
Master Latitude    : -63279018
```

akan dicoba sebagai coordinate scale variants. Engine dapat menemukan bahwa master sebenarnya merepresentasikan `-6.3279018`.

Hal yang sama berlaku untuk longitude:

```
106.6235806 ↔ 1066235806
```

Coordinate tolerance default: `0.0002°`.

### 3. Date normalization

```
04 juli 2026
2026-07-04
2026-07-04T00:00:00
```

dipahami sebagai tanggal yang sama.

### 4. Time tolerance

```
19:46:29 ↔ 19:46:00
```

dianggap sama jika selisihnya <= 60 detik.

### 5. Composite fallback

Jika single index gagal karena data master kotor, engine mencoba mencari kandidat menggunakan kombinasi mapped fields.

Contoh:

```
longitude + date + time
```

Jika minimal dua field memberi confidence yang cukup, record masih dapat dipasangkan.

## Output

Sheet `Result` menambahkan:

- `MATCHED_MASTER_INDEX`
- `MATCH_SCORE`
- `MATCH_MODE`
- `STATUS`
- `DIFFERENT_FIELDS`

`MATCH_MODE` dapat berupa:

- `coordinate_normalized`
- `fuzzy_text`
- `numeric_exact`
- `date_normalized`
- `time_tolerance`
- `composite_fallback`
- `not_found`

Sheet `Detail` berisi audit mapping dan perbandingan tiap field. Sheet `Summary` berisi rekap.

## Threshold default

- Header similarity: 72%
- Index fuzzy similarity: 82%
- Composite match: 78%
- Text value similarity: 90%
- Coordinate tolerance: 0.0002°
- Time tolerance: 60 detik
- Numeric tolerance: max(0.01, 0.1%)

## Local VLM

Default:

```bash
qwen2.5vl:7b
```

## Menjalankan

```bash
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Buka `http://localhost:8000`.
