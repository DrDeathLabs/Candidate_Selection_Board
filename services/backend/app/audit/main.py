from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Candidate Selection Board Audit Service", version="0.1.0")


class AuditIngressEvent(BaseModel):
    event_type: str
    actor_id: str
    entity_type: str
    entity_id: str
    details: dict = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "audit-service"}


@app.post("/v1/events")
def ingest_event(event: AuditIngressEvent) -> dict[str, object]:
    return {"accepted": True, "event_type": event.event_type}
