from __future__ import annotations

import re
from io import BytesIO

from fastapi import FastAPI, UploadFile
from pypdf import PdfReader

app = FastAPI(title="Candidate Selection Board Parser", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "parser"}


@app.post("/v1/parse")
async def parse_document(file: UploadFile) -> dict[str, object]:
    payload = await file.read()
    page_count: int | None = None
    text_preview = ""
    unreadable = False
    full_text = ""
    pages: list[dict[str, object]] = []

    if (file.content_type or "").lower() == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(payload))
        page_count = len(reader.pages)
        extracted_chunks: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            pages.append({"page_number": index, "text": page_text})
            extracted_chunks.append(page_text)
        full_text = "\n\n".join(chunk for chunk in extracted_chunks if chunk)
        text_preview = full_text[:1000]
        unreadable = not bool(text_preview.strip())
    elif (file.content_type or "").startswith("text/"):
        full_text = payload.decode("utf-8", errors="replace")
        text_preview = full_text[:1000]
        raw_pages = re.split(r"\f+", full_text)
        pages = [
            {"page_number": index, "text": page_text.strip()}
            for index, page_text in enumerate(raw_pages, start=1)
            if page_text.strip()
        ] or [{"page_number": 1, "text": full_text.strip()}]
        page_count = len(pages)
    else:
        text_preview = ""

    return {
        "file_name": file.filename,
        "content_type": file.content_type,
        "status": "parsed",
        "next_step": "downstream-evaluation",
        "page_count": page_count,
        "text_preview": text_preview,
        "full_text": full_text,
        "pages": pages,
        "unreadable": unreadable,
    }
