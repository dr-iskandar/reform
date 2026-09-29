from __future__ import annotations

import io
from pathlib import Path
from typing import List

import pymupdf as fitz
from PIL import Image


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def file_bytes_to_png_pages(filename: str, raw: bytes, max_pages: int = 8) -> List[bytes]:
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        doc = fitz.open(stream=raw, filetype="pdf")
        pages: List[bytes] = []
        for idx in range(min(len(doc), max_pages)):
            page = doc.load_page(idx)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            pages.append(pix.tobytes("png"))
        doc.close()
        return pages

    if ext in IMAGE_EXTS:
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        out = io.BytesIO()
        image.save(out, format="PNG")
        return [out.getvalue()]

    raise ValueError(
        "Format dokumen belum didukung. Gunakan PDF, PNG, JPG, JPEG, WEBP, atau BMP."
    )
