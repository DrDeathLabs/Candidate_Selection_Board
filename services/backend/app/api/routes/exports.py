from __future__ import annotations

import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.models.operations import ExportPackage
from app.services.audit import AuditRecorder
from app.services.export_generation import generate_export_package
from app.services.storage import ObjectStorageService, StorageObjectRef

router = APIRouter()
audit = AuditRecorder()


class ExportRequest(BaseModel):
    export_type: str = "decision_package"
    parameters: dict = Field(default_factory=dict)


@router.get("/", response_model=list[dict])
def list_exports(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(
            RoleName.CASE_OWNER,
            RoleName.SELECTING_OFFICIAL,
            RoleName.SYSTEM_ADMINISTRATOR,
            RoleName.READ_ONLY_AUDITOR,
            RoleName.SECURITY_ADMINISTRATOR,
        )
    ),
) -> list[dict]:
    exports = db.query(ExportPackage).filter(ExportPackage.case_id == case_id).all()
    return [
        {
            "id": str(export.id),
            "export_type": export.export_type,
            "status": export.status,
            "storage_key": export.storage_key,
        }
        for export in exports
    ]


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
def request_export(
    case_id: UUID,
    payload: ExportRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> dict[str, str]:
    export = ExportPackage(
        case_id=case_id,
        export_type=payload.export_type,
        status="pending",
        requested_by=principal.user_id,
        parameters=payload.parameters,
    )
    db.add(export)
    db.commit()
    db.refresh(export)

    # Generate the decision package synchronously (a single hiring case is modest).
    generate_export_package(db, export)

    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.EXPORT_GENERATION.value,
        entity_type="export_package",
        entity_id=str(export.id),
        details={"case_id": str(case_id), "export_type": export.export_type, "status": export.status},
        case_id=case_id,
    )
    db.commit()

    return {"export_id": str(export.id), "status": export.status, "storage_key": export.storage_key or ""}


@router.get("/{export_id}/download")
def download_export(
    case_id: UUID,
    export_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(
            RoleName.CASE_OWNER,
            RoleName.SELECTING_OFFICIAL,
            RoleName.SYSTEM_ADMINISTRATOR,
            RoleName.READ_ONLY_AUDITOR,
            RoleName.SECURITY_ADMINISTRATOR,
        )
    ),
) -> StreamingResponse:
    export = db.get(ExportPackage, export_id)
    if export is None or export.case_id != case_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found.")
    if export.status != "complete" or not export.storage_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Export is not ready (status: {export.status})."
        )

    storage = ObjectStorageService()
    data = storage.get_bytes(StorageObjectRef(bucket=storage.bucket, key=export.storage_key))

    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.EXPORT_DOWNLOAD.value,
        entity_type="export_package",
        entity_id=str(export.id),
        details={"case_id": str(case_id)},
        case_id=case_id,
    )
    db.commit()

    filename = f"decision-package-{export.id}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
