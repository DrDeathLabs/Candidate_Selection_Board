from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.models.operations import AdjudicationAction
from app.schemas.adjudications import AdjudicationActionCreate, AdjudicationActionRead
from app.services.audit import AuditRecorder
from app.services.selection import SelectionService

router = APIRouter()
audit = AuditRecorder()
selection_service = SelectionService()


@router.get("/", response_model=list[AdjudicationActionRead])
def list_actions(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[AdjudicationAction]:
    return db.query(AdjudicationAction).filter(AdjudicationAction.case_id == case_id).all()


@router.post("/", response_model=AdjudicationActionRead, status_code=status.HTTP_201_CREATED)
def create_action(
    case_id: UUID,
    payload: AdjudicationActionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.SELECTING_OFFICIAL, RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> AdjudicationAction:
    selection_service.apply_adjudication_action(db, case_id, payload)
    action = AdjudicationAction(case_id=case_id, actor_id=principal.user_id, **payload.model_dump(mode="json"))
    db.add(action)
    db.flush()
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADJUDICATION_ACTION,
        entity_type="adjudication_action",
        entity_id=str(action.id),
        details=payload.model_dump(mode="json"),
        case_id=case_id,
    )
    selection_service.generate_recommendation(db, case_id)
    db.refresh(action)
    return action
