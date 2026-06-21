from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, DocumentStatus, RoleName
from app.models.case import Document
from app.schemas.documents import DocumentCreate, DocumentProcessingSnapshot, DocumentRead, DocumentUploadResponse
from app.schemas.status import DocumentStatusSummary
from app.services.audit import AuditRecorder
from app.services.storage import ObjectStorageService
from app.tasks.document_pipeline import classify_document

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "image/jpeg",
    "image/png",
    "image/tiff",
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
VALID_DOC_TYPES = {"position_description", "resume_bundle", "resume", "supporting", "other"}

router = APIRouter()
audit = AuditRecorder()
storage = ObjectStorageService()


@router.get("/", response_model=list[DocumentRead])
def list_documents(
    response: Response,
    case_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[Document]:
    total = db.scalar(select(func.count(Document.id)).where(Document.case_id == case_id)) or 0
    response.headers["X-Total-Count"] = str(total)
    return (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/processing-snapshot", response_model=DocumentProcessingSnapshot)
def get_processing_snapshot(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> DocumentProcessingSnapshot:
    documents = db.query(Document).filter(Document.case_id == case_id).order_by(Document.created_at.desc()).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    unreadable_or_flagged = 0

    for document in documents:
        by_status[document.status] = by_status.get(document.status, 0) + 1
        by_type[document.document_type] = by_type.get(document.document_type, 0) + 1
        stage = str(document.metadata_json.get("pipeline_stage", "unknown"))
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if document.metadata_json.get("unreadable") or document.metadata_json.get("flagged"):
            unreadable_or_flagged += 1

    return DocumentProcessingSnapshot(
        documents=documents,
        summary=DocumentStatusSummary(
            total_documents=len(documents),
            by_status=by_status,
            by_type=by_type,
            by_stage=by_stage,
            unreadable_or_flagged=unreadable_or_flagged,
        ),
    )


@router.post("/", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def register_document(
    case_id: UUID,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> Document:
    storage_ref = storage.build_object_ref(str(case_id), payload.file_name)
    document = Document(
        case_id=case_id,
        file_name=payload.file_name,
        content_type=payload.content_type,
        storage_key=payload.storage_key or storage_ref.key,
        checksum=payload.checksum,
        document_type=payload.document_type.value,
        status=DocumentStatus.UPLOADED.value,
        page_count=payload.page_count,
        metadata_json=payload.metadata_json,
    )
    db.add(document)
    db.flush()
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.FILE_UPLOAD,
        entity_type="document",
        entity_id=str(document.id),
        details={"file_name": payload.file_name, "document_type": payload.document_type.value},
        case_id=case_id,
    )
    db.commit()
    db.refresh(document)
    return document


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    case_id: UUID,
    document_type: str = Form(...),
    metadata_source: str = Form(default="upload"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> DocumentUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a name.")

    if document_type not in VALID_DOC_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid document_type '{document_type}'.")

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"File type '{content_type}' is not permitted."
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds the 50 MB size limit."
        )

    safe_filename = Path(file.filename).name
    object_ref = storage.build_object_ref(str(case_id), safe_filename)
    storage.upload_bytes(object_ref, payload, content_type=file.content_type or "application/octet-stream")

    checksum = hashlib.sha256(payload).hexdigest()
    document = Document(
        case_id=case_id,
        file_name=safe_filename,
        content_type=content_type or "application/octet-stream",
        storage_key=object_ref.key,
        checksum=checksum,
        document_type=document_type,
        status=DocumentStatus.UPLOADED.value,
        page_count=None,
        metadata_json={
            "source": metadata_source,
            "size_bytes": len(payload),
            "pipeline_stage": "uploaded",
            "original_file_name": file.filename,
        },
        malware_scan_status="pending",
    )
    db.add(document)
    db.flush()

    task = classify_document.delay(str(document.id))
    document.metadata_json = {**document.metadata_json, "classification_task_id": task.id}

    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.FILE_UPLOAD,
        entity_type="document",
        entity_id=str(document.id),
        details={
            "file_name": document.file_name,
            "document_type": document.document_type,
            "storage_key": document.storage_key,
        },
        case_id=case_id,
    )
    db.commit()
    db.refresh(document)
    return DocumentUploadResponse(document=document, processing_task_id=task.id)
