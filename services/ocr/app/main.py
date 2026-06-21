from __future__ import annotations

from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
import pytesseract

app = FastAPI(title="Selection Board OCR Service", version="0.1.0")

ALLOWED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/tiff", "image/bmp", "image/webp")
MAX_OCR_BYTES = 20 * 1024 * 1024  # 20 MB


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ocr"}


@app.post("/v1/ocr")
async def run_ocr(file: UploadFile = File(...)) -> dict[str, object]:
    content_type = file.content_type or ""
    if not any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail=f"File type '{content_type}' not permitted for OCR.")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_OCR_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB OCR limit.")

    image = Image.open(BytesIO(image_bytes))
    text = pytesseract.image_to_string(image)
    return {
        "file_name": file.filename,
        "character_count": len(text),
        "text_preview": text[:500],
    }

