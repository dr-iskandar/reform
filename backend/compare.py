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
COORD_TOLERANCE = 0.0002
NUMERIC_REL_TOLERANCE = 0.001
NUMERIC_ABS_TOLERANCE = 0.01


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


def _number(value: Any) -> Optional[float]:
    text = _text(value)
    if not text:
        return None

    # Indonesian/Excel-friendly normalization.
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

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%d %b %Y",
        "%d %B %Y",
    ]
    replacements = {
        "januari": "january",
        "februari": "february",
        "maret": "march",
        "mei": "may",
        "juni": "june",
        "juli": "july",
        "agustus": "august",
        "oktober": "october",
        "desember": "december",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # ISO datetime -> date.
    iso_candidate = text.replace("z", "+00:00")
    try:
        return datetime.fromisoformat(iso_candidate).date().isoformat()
    except ValueError:
        pass

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
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


def _resolve_field(requested: str, fields: List[str]) -> Tuple[Optional[str], float]:
    if not fields:
        return None, 0.0

    req_header = _header(requested)
    for field in fields:
        if _header(field) == req_header:
            return field, 1.0

    scored = [
        (SequenceMatcher(None, req_header, _header(field)).ratio(), field)
        for field in fields
        if _header(field)
    ]
    if not scored:
        return None, 0.0

    score, field = max(scored, key=lambda item: item[0])
    return (field, score) if score >= HEADER_THRESHOLD else (None, score)


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

        # First try canonical equality.
        exact = next(
            (
                master_field
                for master_field in master_fields
                if master_field not in used_master
                and _header(master_field) == _header(source_field)
            ),
            None,
        )
        if exact:
            mappings.append(
                {
                    "source_field": source_field,
                    "master_field": exact,
                    "header_score": 1.0,
                }
            )
            used_master.add(exact)
            continue

        candidates = [
            (
                SequenceMatcher(
                    None, _header(source_field), _header(master_field)
                ).ratio(),
                master_field,
            )
            for master_field in master_fields
            if master_field not in used_master and _header(master_field)
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
                }
            )
            used_master.add(master_field)

    return mappings


def _compare_value(field_name: str, source_value: Any, master_value: Any) -> Dict[str, Any]:
    left, right = _text(source_value), _text(master_value)

    if not left and not right:
        return {"same": True, "score": 1.0, "mode": "both_empty"}
    if not left or not right:
        return {"same": False, "score": 0.0, "mode": "missing"}

    if left == right:
        return {"same": True, "score": 1.0, "mode": "exact"}

    left_date, right_date = _date(source_value), _date(master_value)
    if left_date and right_date:
        same = left_date == right_date
        return {"same": same, "score": 1.0 if same else 0.0, "mode": "date"}

    left_num, right_num = _number(source_value), _number(master_value)
    if left_num is not None and right_num is not None:
        diff = abs(left_num - right_num)
        field_key = _header(field_name)
        if any(token in field_key for token in ("latitude", "longitude", "lat", "lon", "lng")):
            tolerance = COORD_TOLERANCE
        else:
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


def _find_master_record(
    source_key: Any,
    master_records: List[Dict[str, Any]],
    master_index: str,
) -> Tuple[Optional[Dict[str, Any]], float, Optional[int], str]:
    key_text = _text(source_key)
    if not key_text:
        return None, 0.0, None, "empty"

    # Exact normalized match first.
    for idx, row in enumerate(master_records):
        if _text(row.get(master_index)) == key_text:
            return row, 1.0, idx, "exact"

    # Then fuzzy matching. Numeric identifiers stay strict.
    source_num = _number(source_key)
    scored: List[Tuple[float, int, Dict[str, Any]]] = []
    for idx, row in enumerate(master_records):
        target = row.get(master_index)
        if source_num is not None:
            target_num = _number(target)
            score = 1.0 if target_num is not None and target_num == source_num else 0.0
        else:
            score = _ratio(source_key, target)
        scored.append((score, idx, row))

    if not scored:
        return None, 0.0, None, "none"

    score, idx, row = max(scored, key=lambda item: item[0])
    if score >= INDEX_THRESHOLD:
        return row, round(score, 4), idx, "fuzzy"
    return None, round(score, 4), None, "not_found"


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
        master, index_score, master_idx, index_mode = _find_master_record(
            source_key, master_records, master_index
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
                        "index_match_score": index_score,
                        "index_match_mode": index_mode,
                        "generated_field": source_field,
                        "master_field": master_field,
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
        result_row["MATCH_SCORE"] = index_score
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
