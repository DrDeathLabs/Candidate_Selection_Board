from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.domain.enums import RoleName
from app.models.operations import AuditEvent
from app.schemas.audit import AuditEventRead

router = APIRouter()


@router.get("/", response_model=list[AuditEventRead])
def list_case_audit_events(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(
            RoleName.READ_ONLY_AUDITOR,
            RoleName.SECURITY_ADMINISTRATOR,
            RoleName.SYSTEM_ADMINISTRATOR,
            RoleName.CASE_OWNER,
            RoleName.SELECTING_OFFICIAL,
            RoleName.HR_REVIEWER,
        )
    ),
) -> list[AuditEvent]:
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.case_id == case_id)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(100)
        .all()
    )
