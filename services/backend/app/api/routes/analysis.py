from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.schemas.analysis import PositionAnalysisRead
from app.services.audit import AuditRecorder
from app.services.position_analysis import PositionAnalysisService

router = APIRouter()
audit = AuditRecorder()
analysis_service = PositionAnalysisService()


@router.get("/position", response_model=PositionAnalysisRead)
def get_position_analysis(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> PositionAnalysisRead:
    analysis = analysis_service.get_case_analysis(db, case_id)
    return PositionAnalysisRead(
        id=analysis.id,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        case_id=str(case_id),
        role_type=analysis.role_type,
        status=analysis.status,
        duties=analysis.duties,
        critical_factors=analysis.critical_factors,
        recommended_dimensions=analysis.recommended_dimensions,
        evidence_map=analysis.evidence_map,
    )


@router.post("/position/run", response_model=PositionAnalysisRead)
def run_position_analysis(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> PositionAnalysisRead:
    analysis = analysis_service.analyze_case(db, case_id)
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.MODEL_RUN,
        entity_type="position_analysis",
        entity_id=str(analysis.id),
        details={
            "case_id": str(case_id),
            "role_type": analysis.role_type,
            "duty_count": len(analysis.duties or []),
            "critical_factor_count": len(analysis.critical_factors or []),
        },
        case_id=case_id,
    )
    db.commit()
    return PositionAnalysisRead(
        id=analysis.id,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        case_id=str(case_id),
        role_type=analysis.role_type,
        status=analysis.status,
        duties=analysis.duties,
        critical_factors=analysis.critical_factors,
        recommended_dimensions=analysis.recommended_dimensions,
        evidence_map=analysis.evidence_map,
    )
