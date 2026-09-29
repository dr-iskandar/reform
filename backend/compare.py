from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


INDEX_THRESHOLD = 0.82
HEADER_THRESHOLD = 0.72
VALUE_THRESHOLD = 0.90
COMPOSITE_THRESHOLD = 0.78
COORD_TOLERANCE = 0.0002
TIME_TOLERANCE_SECONDS = 60
NUMERIC_REL_TOLERANCE = 0.001
NUMERIC_ABS_TOLERANCE = 0.01


SEMANTIC_ALIASES = {
    "latitude": {"latitude", "lat", "gpslat", "gpslatitude"},
    "longitude": {"longitude", "long", "lon", "lng", "gpslon", "gpslong", "gpslongitude"},
    "date": {"date", "tanggal", "visitdate", "visittanggal", "tanggalvisit", "tanggalvisiting"},
    "time": {"time", "waktu", "hour", "hours", "visittime", "visithour", "visithours", "jam", "jamvisit"},
    "status": {"status", "jobstatus", "visitstatus", "workstatus"},
    "ts_name": {"tsname", "namats", "surveyor", "technician", "teknisi", "petugas"},
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    return re.sub(r"\s+", " ", text)


def _header(value: Any) -> str:
    """Canonical header: TS_NAME, 'TS Name', 'ts-name' => tsname."""
    return re.sub(r"[^a-z0-9]+", "", _text(value))


def _semantic_key(field_name: Any) -> Optional[str]:
    key = _header(field_name)
    if not key:
        return None

    for semantic, aliases in SEMANTIC_ALIASES.items():
        if key in aliases:
            return semantic

    # Conservative contains rules for common spreadsheet headers.
    if "latitude" in key or key.endswith("lat"):
        return "latitude"
    if "longitude" in key or key.endswith("lng") or key.endswith("lon"):
        return "longitude"
    if "visitdate" in key or key.endswith("date") or key.startswith("tanggal"):
        return "date"
    if "visithour" in key or "visittime" in key or key.endswith("time") or key.endswith("hours"):
        return "time"
    if key.endswith("status"):
        return "status"

    return None


def _number(value: Any) -> Optional[float]:
    text = _text(value)
    if not text:
        return None

    compact = text.replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", compact):
        compact = compact.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d+(,\d+)", compact):
        compact = compact.replace(",", ".")

    try:
        number = float(compact)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def _date(value: Any) -> Optional[str]:
    text = _text(value)
    if not text:
        return None

    replacements = {
        "januari": "january",
        "februari": "february",
        "maret": "march",
        "april": "april",
        "mei": "may",
        "juni": "june",
        "juli": "july",
        "agustus": "august",
        "september": "september",
        "oktober": "october",
        "november": "november",
        "desember": "december",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    try:
        return datetime.fromisoformat(text.replace("z", "+00:00")).date().isoformat()
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _time_seconds(value: Any) -> Optional[int]:
    text = _text(value)
    if not text:
        return None

    # ISO datetime.
    try:
        parsed = datetime.fromisoformat(text.replace("z", "+00:00"))
        return parsed.hour * 3600 + parsed.minute * 60 + parsed.second
    except ValueError:
        pass

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.hour * 3600 + parsed.minute * 60 + parsed.second
        except ValueError:
            continue
    return None


def _ratio(a: Any, b: Any) -> float:
    aa, bb = _text(a), _text(b)
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    return SequenceMatcher(None, aa, bb).ratio()


def _coordinate_variants(value: Any, semantic: str) -> List[float]:
    number = _number(value)
    if number is None:
        return []

    limit = 90.0 if semantic == "latitude" else 180.0
    raw = _text(value)
    has_decimal_mark = "." in raw or "," in raw

    # If a decimal mark is already present, trust that representation.
    if has_decimal_mark and abs(number) <= limit:
        return [number]

    variants: List[float] = []
    for power in range(0, 10):
        candidate = number / (10 ** power)
        if abs(candidate) <= limit:
            variants.append(candidate)

    # Remove duplicates while preserving order.
    deduped: List[float] = []
    for candidate in variants:
        if not any(abs(candidate - seen) < 1e-12 for seen in deduped):
            deduped.append(candidate)
    return deduped


def _coordinate_comparison(semantic: str, left: Any, right: Any) -> Dict[str, Any]:
    left_values = _coordinate_variants(left, semantic)
    right_values = _coordinate_variants(right, semantic)
    if not left_values or not right_values:
        return {"same": False, "score": 0.0, "mode": "coordinate_parse_failed"}

    best = None
    for lv in left_values:
        for rv in right_values:
            diff = abs(lv - rv)
            if best is None or diff < best[0]:
                best = (diff, lv, rv)

    assert best is not None
    diff, lv, rv = best
    same = diff <= COORD_TOLERANCE

    if same:
        score = max(0.95, 1.0 - (diff / max(COORD_TOLERANCE, 1e-12)) * 0.05)
    else:
        score = max(0.0, 1.0 - diff / 0.05)

    return {
        "same": same,
        "score": round(score, 4),
        "mode": "coordinate_normalized",
        "difference": diff,
        "tolerance": COORD_TOLERANCE,
        "normalized_generated": lv,
        "normalized_master": rv,
    }


def _resolve_field(requested: str, fields: List[str]) -> Tuple[Optional[str], float]:
    if not fields:
        return None, 0.0

    requested_header = _header(requested)
    requested_semantic = _semantic_key(requested)

    for field in fields:
        if _header(field) == requested_header:
            return field, 1.0

    if requested_semantic:
        semantic_matches = [f for f in fields if _semantic_key(f) == requested_semantic]
        if semantic_matches:
            return semantic_matches[0], 0.98

    scored = [
        (SequenceMatcher(None, requested_header, _header(field)).ratio(), field)
        for field in fields
        if _header(field)
    ]
    if not scored:
        return None, 0.0

    score, field = max(scored, key=lambda item: item[0])
    return (field, score) if score >= HEADER_THRESHOLD else (None, score)


def _field_mapping_score(source_field: str, master_field: str) -> float:
    source_header = _header(source_field)
    master_header = _header(master_field)

    if source_header == master_header:
        return 1.0

    source_semantic = _semantic_key(source_field)
    master_semantic = _semantic_key(master_field)
    if source_semantic and source_semantic == master_semantic:
        return 0.98

    return SequenceMatcher(None, source_header, master_header).ratio()


def _map_fields(
    source_fields: List[str],
    master_fields: List[str],
    source_index: str,
    master_index: str,
) -> List[Dict[str, Any]]:
    mappings: List[Dict[str, Any]] = []
    used_master = {master_index}

    for source_field in source_fields:
        if source_field == source_index:
            continue

        candidates = [
            (_field_mapping_score(source_field, master_field), master_field)
            for master_field in master_fields
            if master_field not in used_master
        ]
        if not candidates:
            continue

        score, master_field = max(candidates, key=lambda item: item[0])
        if score >= HEADER_THRESHOLD:
            mappings.append(
                {
                    "source_field": source_field,
                    "master_field": master_field,
                    "header_score": round(score, 4),
                    "semantic": _semantic_key(source_field) or _semantic_key(master_field),
                }
            )
            used_master.add(master_field)

    return mappings


def _compare_value(
    field_name: str,
    source_value: Any,
    master_value: Any,
    master_field_name: Optional[str] = None,
) -> Dict[str, Any]:
    left, right = _text(source_value), _text(master_value)

    if not left and not right:
        return {"same": True, "score": 1.0, "mode": "both_empty"}
    if not left or not right:
        return {"same": False, "score": 0.0, "mode": "missing"}
    if left == right:
        return {"same": True, "score": 1.0, "mode": "exact"}

    semantic = _semantic_key(field_name) or _semantic_key(master_field_name or "")

    if semantic in {"latitude", "longitude"}:
        return _coordinate_comparison(semantic, source_value, master_value)

    if semantic == "date":
        left_date, right_date = _date(source_value), _date(master_value)
        if left_date and right_date:
            same = left_date == right_date
            return {
                "same": same,
                "score": 1.0 if same else 0.0,
                "mode": "date_normalized",
                "normalized_generated": left_date,
                "normalized_master": right_date,
            }

    if semantic == "time":
        left_time, right_time = _time_seconds(source_value), _time_seconds(master_value)
        if left_time is not None and right_time is not None:
            diff = abs(left_time - right_time)
            same = diff <= TIME_TOLERANCE_SECONDS
            score = 1.0 if same else max(0.0, 1.0 - diff / 3600.0)
            return {
                "same": same,
                "score": round(score, 4),
                "mode": "time_tolerance",
                "difference_seconds": diff,
                "tolerance_seconds": TIME_TOLERANCE_SECONDS,
            }

    left_num, right_num = _number(source_value), _number(master_value)
    if left_num is not None and right_num is not None:
        diff = abs(left_num - right_num)
        tolerance = max(
            NUMERIC_ABS_TOLERANCE,
            max(abs(left_num), abs(right_num)) * NUMERIC_REL_TOLERANCE,
        )
        same = diff <= tolerance
        score = 1.0 if same else max(0.0, 1.0 - diff / max(abs(right_num), 1.0))
        return {
            "same": same,
            "score": round(score, 4),
            "mode": "numeric_tolerance",
            "difference": diff,
            "tolerance": tolerance,
        }

    score = _ratio(source_value, master_value)
    return {
        "same": score >= VALUE_THRESHOLD,
        "score": round(score, 4),
        "mode": "fuzzy_text",
    }


def _index_similarity(
    source_index: str,
    master_index: str,
    source_value: Any,
    master_value: Any,
) -> Tuple[float, str]:
    semantic = _semantic_key(source_index) or _semantic_key(master_index)

    if semantic in {"latitude", "longitude"}:
        comparison = _coordinate_comparison(semantic, source_value, master_value)
        return comparison["score"], comparison["mode"]

    if semantic == "date":
        left, right = _date(source_value), _date(master_value)
        if left and right:
            return (1.0 if left == right else 0.0), "date_normalized"

    if semantic == "time":
        left, right = _time_seconds(source_value), _time_seconds(master_value)
        if left is not None and right is not None:
            diff = abs(left - right)
            if diff <= TIME_TOLERANCE_SECONDS:
                return 1.0, "time_tolerance"
            return max(0.0, 1.0 - diff / 3600.0), "time_distance"

    source_num = _number(source_value)
    master_num = _number(master_value)
    if source_num is not None and master_num is not None:
        return (1.0 if source_num == master_num else 0.0), "numeric_exact"

    return _ratio(source_value, master_value), "fuzzy_text"


def _composite_score(
    source: Dict[str, Any],
    master: Dict[str, Any],
    field_mappings: List[Dict[str, Any]],
) -> Tuple[float, int]:
    weighted = 0.0
    total_weight = 0.0
    comparable = 0

    for mapping in field_mappings:
        source_field = mapping["source_field"]
        master_field = mapping["master_field"]
        left = source.get(source_field)
        right = master.get(master_field)
        if not _text(left) or not _text(right):
            continue

        comparison = _compare_value(source_field, left, right, master_field)
        semantic = mapping.get("semantic")

        if semantic in {"latitude", "longitude", "ts_name"}:
            weight = 2.0
        elif semantic == "date":
            weight = 1.5
        elif semantic == "time":
            weight = 1.0
        else:
            weight = 0.75

        weighted += comparison["score"] * weight
        total_weight += weight
        comparable += 1

    if total_weight == 0:
        return 0.0, 0
    return round(weighted / total_weight, 4), comparable


def _find_master_record(
    source: Dict[str, Any],
    source_index: str,
    master_records: List[Dict[str, Any]],
    master_index: str,
    field_mappings: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], float, Optional[int], str]:
    source_key = source.get(source_index)
    if not _text(source_key):
        return None, 0.0, None, "empty"

    index_candidates: List[Tuple[float, int, Dict[str, Any], str]] = []
    for idx, row in enumerate(master_records):
        score, mode = _index_similarity(
            source_index,
            master_index,
            source_key,
            row.get(master_index),
        )
        index_candidates.append((score, idx, row, mode))

    if index_candidates:
        score, idx, row, mode = max(index_candidates, key=lambda item: item[0])
        if score >= INDEX_THRESHOLD:
            return row, round(score, 4), idx, mode

    # Fallback: use multiple mapped fields if a single index is dirty/malformed.
    composite_candidates: List[Tuple[float, int, Dict[str, Any], int]] = []
    for idx, row in enumerate(master_records):
        score, comparable = _composite_score(source, row, field_mappings)
        composite_candidates.append((score, idx, row, comparable))

    if composite_candidates:
        score, idx, row, comparable = max(composite_candidates, key=lambda item: item[0])
        if comparable >= 2 and score >= COMPOSITE_THRESHOLD:
            return row, round(score, 4), idx, "composite_fallback"

    best_index_score = max((c[0] for c in index_candidates), default=0.0)
    return None, round(best_index_score, 4), None, "not_found"


def compare_records(
    source_records: List[Dict[str, Any]],
    master_records: List[Dict[str, Any]],
    index_field: str,
) -> Dict[str, Any]:
    if not source_records:
        return {
            "summary": {"generated_rows": 0, "master_rows": len(master_records)},
            "rows": [],
            "details": [],
            "warnings": ["Generated data kosong."],
        }
    if not master_records:
        return {
            "summary": {"generated_rows": len(source_records), "master_rows": 0},
            "rows": [],
            "details": [],
            "warnings": ["Master data kosong."],
        }
    if not index_field.strip():
        return {
            "summary": {"generated_rows": len(source_records), "master_rows": len(master_records)},
            "rows": [],
            "details": [],
            "warnings": ["Index field belum ditentukan."],
        }

    source_fields = sorted(
        {str(key) for row in source_records for key in row.keys() if key != "_page"}
    )
    master_fields = sorted(
        {str(key) for row in master_records for key in row.keys() if key != "_page"}
    )

    source_index, source_index_score = _resolve_field(index_field, source_fields)
    master_index, master_index_score = _resolve_field(index_field, master_fields)

    warnings: List[str] = []
    if not source_index or not master_index:
        warnings.append(
            "Index field tidak dapat dipetakan dengan cukup yakin. "
            f"Generated candidate={source_index or '-'} ({source_index_score:.0%}), "
            f"Master candidate={master_index or '-'} ({master_index_score:.0%})."
        )
        return {
            "requested_index_field": index_field,
            "resolved_source_index": source_index,
            "resolved_master_index": master_index,
            "summary": {
                "generated_rows": len(source_records),
                "master_rows": len(master_records),
                "same": 0,
                "different": 0,
                "not_found": len(source_records),
            },
            "rows": [
                {
                    **{k: v for k, v in row.items() if k != "_page"},
                    "MATCH_MODE": "not_comparable",
                    "STATUS": "NOT_COMPARABLE",
                    "DIFFERENT_FIELDS": "",
                }
                for row in source_records
            ],
            "details": [],
            "warnings": warnings,
        }

    field_mappings = _map_fields(
        source_fields, master_fields, source_index, master_index
    )
    if not field_mappings:
        warnings.append(
            "Tidak ada field pembanding yang dapat dipetakan secara elastic selain index."
        )

    result_rows: List[Dict[str, Any]] = []
    detail_rows: List[Dict[str, Any]] = []

    for source_number, source in enumerate(source_records, start=1):
        source_key = source.get(source_index)
        master, match_score, master_idx, match_mode = _find_master_record(
            source,
            source_index,
            master_records,
            master_index,
            field_mappings,
        )

        different_fields: List[str] = []

        if not _text(source_key):
            status = "INDEX_EMPTY"
        elif master is None:
            status = "NOT_FOUND"
        elif not field_mappings:
            status = "SAME"
        else:
            for mapping in field_mappings:
                source_field = mapping["source_field"]
                master_field = mapping["master_field"]
                comparison = _compare_value(
                    source_field,
                    source.get(source_field),
                    master.get(master_field),
                    master_field,
                )

                if not comparison["same"]:
                    different_fields.append(source_field)

                detail_rows.append(
                    {
                        "source_row": source_number,
                        "master_row": (master_idx + 1) if master_idx is not None else None,
                        "index_requested": index_field,
                        "source_index_field": source_index,
                        "master_index_field": master_index,
                        "index_value_generated": source_key,
                        "index_value_master": master.get(master_index),
                        "record_match_score": match_score,
                        "record_match_mode": match_mode,
                        "generated_field": source_field,
                        "master_field": master_field,
                        "semantic": mapping.get("semantic"),
                        "header_match_score": mapping["header_score"],
                        "generated_value": source.get(source_field),
                        "master_value": master.get(master_field),
                        "value_match_score": comparison["score"],
                        "comparison_mode": comparison["mode"],
                        "status": "SAME" if comparison["same"] else "DIFFERENT",
                    }
                )

            status = "SAME" if not different_fields else "DIFFERENT"

        result_row = {k: v for k, v in source.items() if k != "_page"}
        result_row["MATCHED_MASTER_INDEX"] = (
            master.get(master_index) if master is not None else None
        )
        result_row["MATCH_SCORE"] = match_score
        result_row["MATCH_MODE"] = match_mode
        result_row["STATUS"] = status
        result_row["DIFFERENT_FIELDS"] = ", ".join(different_fields)
        result_rows.append(result_row)

    summary = {
        "generated_rows": len(source_records),
        "master_rows": len(master_records),
        "same": sum(r["STATUS"] == "SAME" for r in result_rows),
        "different": sum(r["STATUS"] == "DIFFERENT" for r in result_rows),
        "not_found": sum(r["STATUS"] == "NOT_FOUND" for r in result_rows),
        "index_empty": sum(r["STATUS"] == "INDEX_EMPTY" for r in result_rows),
        "mapped_fields": len(field_mappings),
        "source_index": source_index,
        "master_index": master_index,
    }

    return {
        "requested_index_field": index_field,
        "resolved_source_index": source_index,
        "resolved_master_index": master_index,
        "field_mappings": field_mappings,
        "summary": summary,
        "rows": result_rows,
        "details": detail_rows,
        "warnings": warnings,
    }
