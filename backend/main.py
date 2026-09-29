from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from pydantic import BaseModel

from .compare import compare_records
from .vlm import extract_document, ollama_health


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"

app = FastAPI(title="ReForm Local VLM Comparator", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class CompareRequest(BaseModel):
    source_records: List[Dict[str, Any]]
    target_records: List[Dict[str, Any]]
    match_key: Optional[str] = None


class ExportRequest(BaseModel):
    summary: Dict[str, Any]
    rows: List[Dict[str, Any]]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return ollama_health()


@app.post("/api/extract")
async def extract(
    file: UploadFile = File(...),
    schema_hint: str = Form(""),
):
    try:
        raw = await file.read()
        return extract_document(file.filename or "document", raw, schema_hint)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/read-table")
async def read_table(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        name = (file.filename or "").lower()

        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw), dtype=object)
        elif name.endswith((".xlsx", ".xlsm", ".xltx")):
            df = pd.read_excel(io.BytesIO(raw), dtype=object)
        else:
            raise ValueError("Master data harus CSV atau XLSX.")

        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")
        return {
            "filename": file.filename,
            "columns": list(df.columns),
            "records": records,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/compare")
def compare(payload: CompareRequest):
    return compare_records(
        payload.source_records,
        payload.target_records,
        payload.match_key,
    )


@app.post("/api/export")
def export_excel(payload: ExportRequest):
    wb = Workbook()
    ws = wb.active
    ws.title = "Comparison"

    headers = [
        "source_row",
        "target_row",
        "record_similarity",
        "field",
        "source_value",
        "target_value",
        "field_similarity",
        "status",
    ]
    ws.append(headers)
    for row in payload.rows:
        ws.append([row.get(h) for h in headers])

    summary_ws = wb.create_sheet("Summary")
    summary_ws.append(["metric", "value"])
    for key, value in payload.summary.items():
        summary_ws.append([key, value])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="reform_comparison.xlsx"'},
    )
