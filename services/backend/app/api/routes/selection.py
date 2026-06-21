from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.schemas.selection import SelectionRecommendationRead
from app.services.audit import AuditRecorder
from app.services.selection import SelectionService

router = APIRouter()
audit = AuditRecorder()
selection_service = SelectionService()


@router.get("/recommendation", response_model=SelectionRecommendationRead)
def get_selection_recommendation(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SelectionRecommendationRead:
    return selection_service.get_recommendation(db, case_id)


@router.post("/recommendation/generate", response_model=SelectionRecommendationRead)
def generate_selection_recommendation(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.SELECTING_OFFICIAL, RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> SelectionRecommendationRead:
    recommendation = selection_service.generate_recommendation(db, case_id)
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.SELECTION_RECOMMENDATION,
        entity_type="selection_recommendation",
        entity_id=str(recommendation.id),
        details={
            "case_id": str(case_id),
            "selectee_candidate_id": recommendation.selectee_candidate_id,
            "alternate_candidate_ids": recommendation.alternate_candidate_ids,
            "status": recommendation.status,
        },
        case_id=case_id,
    )
    db.commit()
    return recommendation
