from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List


def _clean(value: Any) -> str:
    """Normalize values so harmless Excel/string formatting does not create false differences."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""

    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"\s+", " ", text)

    # Normalize simple numeric strings: 106.0 == 106
    try:
        number = float(text.replace(",", "."))
        if math.isfinite(number):
            if number.is_integer():
                return str(int(number))
            return ("%.12f" % number).rstrip("0").rstrip(".")
    except ValueError:
        pass

    return text


def compare_records(
    source_records: List[Dict[str, Any]],
    master_records: List[Dict[str, Any]],
    index_field: str,
) -> Dict[str, Any]:
    if not index_field:
        raise ValueError("Index field wajib ditentukan.")

    source_fields = {
        key for row in source_records for key in row.keys() if key != "_page"
    }
    master_fields = {
        key for row in master_records for key in row.keys() if key != "_page"
    }

    if index_field not in source_fields:
        raise ValueError(f"Index field '{index_field}' tidak ditemukan di file hasil VLM/OCR.")
    if index_field not in master_fields:
        raise ValueError(f"Index field '{index_field}' tidak ditemukan di master data.")

    compare_fields = sorted((source_fields & master_fields) - {index_field})
    if not compare_fields:
        raise ValueError(
            "Tidak ada field dengan nama yang sama untuk dibandingkan selain index field."
        )

    master_map: Dict[str, Dict[str, Any]] = {}
    duplicate_master_keys: List[str] = []
    for row in master_records:
        key = _clean(row.get(index_field))
        if not key:
            continue
        if key in master_map:
            duplicate_master_keys.append(str(row.get(index_field)))
        else:
            master_map[key] = row

    result_rows: List[Dict[str, Any]] = []
    detail_rows: List[Dict[str, Any]] = []

    for source_number, source in enumerate(source_records, start=1):
        source_key_raw = source.get(index_field)
        source_key = _clean(source_key_raw)
        master = master_map.get(source_key)

        different_fields: List[str] = []

        if not source_key:
            status = "INDEX_EMPTY"
        elif master is None:
            status = "NOT_FOUND"
        else:
            for field in compare_fields:
                source_value = source.get(field)
                master_value = master.get(field)
                same = _clean(source_value) == _clean(master_value)
                if not same:
                    different_fields.append(field)

                detail_rows.append(
                    {
                        "source_row": source_number,
                        "index_field": index_field,
                        "index_value": source_key_raw,
                        "field": field,
                        "generated_value": source_value,
                        "master_value": master_value,
                        "status": "SAME" if same else "DIFFERENT",
                    }
                )

            status = "SAME" if not different_fields else "DIFFERENT"

        result_row = {k: v for k, v in source.items() if k != "_page"}
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
        "compared_fields": len(compare_fields),
        "duplicate_master_index": len(duplicate_master_keys),
    }

    return {
        "index_field": index_field,
        "compare_fields": compare_fields,
        "summary": summary,
        "rows": result_rows,
        "details": detail_rows,
        "duplicate_master_keys": duplicate_master_keys[:50],
    }
