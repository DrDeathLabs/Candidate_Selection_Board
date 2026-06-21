from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.operations import AuditEvent


class AuditRecorder:
    def record(
        self,
        db: Session,
        *,
        actor_id: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        details: dict[str, Any],
        case_id: object | None = None,
        session_id: str | None = None,
        source_ip: str | None = None,
    ) -> AuditEvent:
        # Auto-fill session_id / source_ip from the current request principal
        # when not supplied by the caller, so all audit records are enriched
        # without requiring every call site to pass them explicitly.
        if session_id is None or source_ip is None:
            from app.core.security import _current_principal

            p = _current_principal.get()
            if p is not None:
                if session_id is None:
                    session_id = p.session_id
                if source_ip is None:
                    source_ip = p.source_ip

        payload = json.dumps(details, sort_keys=True).encode("utf-8")
        immutable_hash = hashlib.sha256(payload).hexdigest()
        event = AuditEvent(
            case_id=case_id,
            actor_id=actor_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            immutable_hash=immutable_hash,
            occurred_at=datetime.now(timezone.utc),
            session_id=session_id,
            source_ip=source_ip,
        )
        db.add(event)
        return event
