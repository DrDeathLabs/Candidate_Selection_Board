from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, CaseStatus, RoleName
from app.models.case import ReviewCase
from app.models.operations import ExportPackage
from app.schemas.cases import CaseCreate, CaseRead, CaseSummary
from app.services.audit import AuditRecorder
from app.services.storage import ObjectStorageService, StorageObjectRef

router = APIRouter()
audit = AuditRecorder()
storage = ObjectStorageService()


@router.get("/", response_model=list[CaseSummary])
def list_cases(
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[ReviewCase]:
    total = db.scalar(func.count(ReviewCase.id)) or 0
    response.headers["X-Total-Count"] = str(total)
    return db.query(ReviewCase).order_by(ReviewCase.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> ReviewCase:
    case = ReviewCase(**payload.model_dump(mode="json"), status=CaseStatus.DRAFT.value)
    db.add(case)
    db.flush()
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.CASE_CREATION,
        entity_type="review_case",
        entity_id=str(case.id),
        details={"title": case.title},
        case_id=case.id,
    )
    db.commit()
    db.refresh(case)
    return case


@router.get("/{case_id}", response_model=CaseRead)
def get_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ReviewCase:
    case = db.get(ReviewCase, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> Response:
    case = db.get(ReviewCase, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    document_keys = [document.storage_key for document in case.documents if document.storage_key]
    export_keys = [
        export.storage_key
        for export in db.query(ExportPackage).filter(ExportPackage.case_id == case_id).all()
        if export.storage_key
    ]

    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.CASE_DELETION,
        entity_type="review_case",
        entity_id=str(case.id),
        details={"title": case.title},
        case_id=None,
    )

    # Delete storage objects before DB commit so a storage failure doesn't leave orphaned DB records
    for key in [*document_keys, *export_keys]:
        storage.delete_object(StorageObjectRef(bucket=storage.bucket, key=key))

    db.execute(sa_delete(ReviewCase).where(ReviewCase.id == case_id))
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
