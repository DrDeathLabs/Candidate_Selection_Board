from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Candidate Selection Board Export Service", version="0.1.0")


class ExportJobRequest(BaseModel):
    case_id: str
    export_types: list[str] = Field(default_factory=list)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "export-service"}


@app.post("/v1/generate")
def generate_export(request: ExportJobRequest) -> dict[str, object]:
    return {
        "case_id": request.case_id,
        "export_types": request.export_types,
        "status": "queued",
    }
