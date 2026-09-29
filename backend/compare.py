from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _similarity(a: Any, b: Any) -> float:
    aa, bb = _clean(a), _clean(b)
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    return SequenceMatcher(None, aa, bb).ratio()


def _shared_fields(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    ignored = {"_page"}
    return sorted((set(a) & set(b)) - ignored)


def _best_target(
    source: Dict[str, Any],
    targets: List[Dict[str, Any]],
    match_key: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], float, Optional[int]]:
    if not targets:
        return None, 0.0, None

    if match_key and _clean(source.get(match_key)):
        source_key = source.get(match_key)
        scored = [
            (_similarity(source_key, row.get(match_key)), idx, row)
            for idx, row in enumerate(targets)
        ]
    else:
        scored = []
        for idx, row in enumerate(targets):
            fields = _shared_fields(source, row)
            score = (
                sum(_similarity(source.get(f), row.get(f)) for f in fields) / len(fields)
                if fields
                else 0.0
            )
            scored.append((score, idx, row))

    score, idx, row = max(scored, key=lambda x: x[0])
    return row, score, idx


def compare_records(
    source_records: List[Dict[str, Any]],
    target_records: List[Dict[str, Any]],
    match_key: Optional[str] = None,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    matched_records = 0

    for source_idx, source in enumerate(source_records):
        target, record_score, target_idx = _best_target(source, target_records, match_key)
        if target is not None:
            matched_records += 1

        fields = sorted((set(source) | set(target or {})) - {"_page"})
        for field in fields:
            left = source.get(field)
            right = (target or {}).get(field)
            sim = _similarity(left, right)

            if _clean(left) == "" and _clean(right) == "":
                status = "empty"
            elif _clean(left) == "" or _clean(right) == "":
                status = "missing"
            elif sim == 1.0:
                status = "match"
            elif sim >= 0.92:
                status = "near_match"
            else:
                status = "mismatch"

            rows.append(
                {
                    "source_row": source_idx + 1,
                    "target_row": (target_idx + 1) if target_idx is not None else None,
                    "record_similarity": round(record_score, 4),
                    "field": field,
                    "source_value": left,
                    "target_value": right,
                    "field_similarity": round(sim, 4),
                    "status": status,
                }
            )

    summary = {
        "source_records": len(source_records),
        "target_records": len(target_records),
        "matched_records": matched_records,
        "field_match": sum(r["status"] == "match" for r in rows),
        "field_near_match": sum(r["status"] == "near_match" for r in rows),
        "field_mismatch": sum(r["status"] == "mismatch" for r in rows),
        "field_missing": sum(r["status"] == "missing" for r in rows),
    }
    return {"summary": summary, "rows": rows}
