from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import DocumentStatus, DocumentType
from app.schemas.common import TimestampedResponse
from app.schemas.status import DocumentStatusSummary


class DocumentCreate(BaseModel):
    file_name: str
    content_type: str
    storage_key: str | None = None
    checksum: str | None = None
    document_type: DocumentType = DocumentType.OTHER
    page_count: int | None = None
    metadata_json: dict = Field(default_factory=dict)


class DocumentRead(TimestampedResponse):
    file_name: str
    content_type: str
    storage_key: str
    checksum: str | None
    document_type: DocumentType
    status: DocumentStatus
    page_count: int | None
    metadata_json: dict
    malware_scan_status: str


class DocumentUploadResponse(BaseModel):
    document: DocumentRead
    processing_task_id: str


class DocumentProcessingSnapshot(BaseModel):
    documents: list[DocumentRead]
    summary: DocumentStatusSummary
