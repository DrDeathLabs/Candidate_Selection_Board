from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.models.case import Rubric, RubricDimension
from app.schemas.rubrics import RubricCreate, RubricLockRequest, RubricRead, RubricUpdate
from app.services.audit import AuditRecorder
from app.services.position_analysis import PositionAnalysisService

router = APIRouter()
audit = AuditRecorder()
analysis_service = PositionAnalysisService()


@router.get("/", response_model=list[RubricRead])
def list_rubrics(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[Rubric]:
    return db.query(Rubric).filter(Rubric.case_id == case_id).order_by(Rubric.created_at.desc()).all()


@router.post("/", response_model=RubricRead, status_code=status.HTTP_201_CREATED)
def create_rubric(
    case_id: UUID,
    payload: RubricCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> Rubric:
    rubric = Rubric(
        case_id=case_id,
        position_analysis_id=payload.position_analysis_id,
        name=payload.name,
        total_weight=sum(d.weight for d in payload.dimensions),
    )
    db.add(rubric)
    db.flush()
    for dimension in payload.dimensions:
        db.add(RubricDimension(rubric_id=rubric.id, **dimension.model_dump()))
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.RUBRIC_CHANGE,
        entity_type="rubric",
        entity_id=str(rubric.id),
        details={"action": "create", "dimension_count": len(payload.dimensions)},
        case_id=case_id,
    )
    db.commit()
    db.refresh(rubric)
    return rubric


@router.post("/from-analysis", response_model=RubricRead, status_code=status.HTTP_201_CREATED)
def create_rubric_from_analysis(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> Rubric:
    analysis = analysis_service.get_case_analysis(db, case_id)
    payload = analysis_service.build_rubric_create(analysis, "Proposed Position Rubric")
    return create_rubric(case_id=case_id, payload=payload, db=db, principal=principal)


@router.get("/{rubric_id}", response_model=RubricRead)
def get_rubric(
    case_id: UUID,
    rubric_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> Rubric:
    rubric = db.get(Rubric, rubric_id)
    if rubric is None or rubric.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric not found.")
    return rubric


@router.put("/{rubric_id}", response_model=RubricRead)
def update_rubric(
    case_id: UUID,
    rubric_id: UUID,
    payload: RubricUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> Rubric:
    rubric = db.get(Rubric, rubric_id)
    if rubric is None or rubric.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric not found.")

    rubric.name = payload.name
    rubric.status = payload.status or rubric.status
    rubric.is_locked = payload.is_locked
    rubric.total_weight = sum(d.weight for d in payload.dimensions)
    db.query(RubricDimension).filter(RubricDimension.rubric_id == rubric_id).delete()
    db.flush()
    for dimension in payload.dimensions:
        db.add(RubricDimension(rubric_id=rubric.id, **dimension.model_dump()))

    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.RUBRIC_CHANGE,
        entity_type="rubric",
        entity_id=str(rubric.id),
        details={"action": "update", "dimension_count": len(payload.dimensions), "is_locked": payload.is_locked},
        case_id=case_id,
    )
    db.commit()
    db.refresh(rubric)
    return rubric


@router.post("/{rubric_id}/lock", response_model=RubricRead)
def set_rubric_lock(
    case_id: UUID,
    rubric_id: UUID,
    payload: RubricLockRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> Rubric:
    rubric = db.get(Rubric, rubric_id)
    if rubric is None or rubric.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric not found.")

    rubric.is_locked = payload.is_locked
    rubric.status = "locked" if payload.is_locked else "draft"
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.RUBRIC_CHANGE,
        entity_type="rubric",
        entity_id=str(rubric.id),
        details={"action": "lock", "is_locked": payload.is_locked},
        case_id=case_id,
    )
    db.commit()
    db.refresh(rubric)
    return rubric
