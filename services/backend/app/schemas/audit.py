from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.schemas.common import ORMModel


class AuditEventRead(ORMModel):
    id: UUID
    case_id: UUID | None = None
    actor_id: str
    event_type: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    immutable_hash: str
    occurred_at: datetime
    session_id: str | None = None
    source_ip: str | None = None
