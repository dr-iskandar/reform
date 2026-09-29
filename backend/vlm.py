from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Dict, List

import requests

from .document import file_bytes_to_png_pages


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")
MAX_PAGES = int(os.getenv("MAX_PAGES", "8"))


SYSTEM_PROMPT = """You are a document understanding engine.
Read the provided page image and extract structured factual data.
Do not invent missing values. Preserve identifiers, names, dates, coordinates,
codes, numbers, and labels as faithfully as possible.

Return JSON only using this shape:
{
  "document_type": "short type",
  "records": [
    {
      "fields": {
        "field_name": "value or null"
      }
    }
  ]
}

Rules:
- Prefer the labels visible in the document as field names, normalized to snake_case.
- If the page contains a table, produce one record per meaningful row.
- If it is a form/photo with metadata, usually produce one record.
- Ignore decorative text unless it is useful for comparison.
- Do not add markdown fences.
"""


def ollama_health() -> Dict[str, Any]:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        data = response.json()
        names = [m.get("name", "") for m in data.get("models", [])]
        return {
            "ok": True,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "installed_models": names,
            "model_available": any(
                n == OLLAMA_MODEL or n.startswith(OLLAMA_MODEL + ":") for n in names
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": OLLAMA_URL,
            "model": OLLAMA_MODEL,
            "error": str(exc),
        }


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("VLM tidak mengembalikan JSON yang valid.")
        return json.loads(match.group(0))


def _extract_page(image_bytes: bytes, page_number: int, schema_hint: str = "") -> Dict[str, Any]:
    prompt = SYSTEM_PROMPT
    if schema_hint.strip():
        prompt += (
            "\nPrioritize these expected fields/schema when visible: "
            + schema_hint.strip()
            + "."
        )
    prompt += f"\nThis is page {page_number}."

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image_bytes).decode("ascii")],
            }
        ],
        "options": {"temperature": 0},
    }

    response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    response.raise_for_status()
    body = response.json()
    content = body.get("message", {}).get("content", "")
    parsed = _extract_json(content)
    parsed["_page"] = page_number
    return parsed


def extract_document(filename: str, raw: bytes, schema_hint: str = "") -> Dict[str, Any]:
    pages = file_bytes_to_png_pages(filename, raw, MAX_PAGES)
    all_records: List[Dict[str, Any]] = []
    page_results: List[Dict[str, Any]] = []
    document_types: List[str] = []

    for idx, page in enumerate(pages, start=1):
        result = _extract_page(page, idx, schema_hint)
        page_results.append(result)
        if result.get("document_type"):
            document_types.append(str(result["document_type"]))

        for rec in result.get("records", []):
            fields = rec.get("fields", rec)
            if isinstance(fields, dict):
                all_records.append({"_page": idx, **fields})

    return {
        "filename": filename,
        "model": OLLAMA_MODEL,
        "document_type": document_types[0] if document_types else "unknown",
        "pages_processed": len(pages),
        "records": all_records,
        "page_results": page_results,
    }
