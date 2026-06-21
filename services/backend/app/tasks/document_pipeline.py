from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.case import Document
from app.models.operations import AuditEvent
from app.services.malware_scan import MalwareScanService
from app.services.parser_client import ParserClient
from app.services.review_workflow import ReviewWorkflowService
from app.services.storage import ObjectStorageService, StorageObjectRef
from app.workers.celery_app import celery_app


@celery_app.task(name="documents.classify", time_limit=300, soft_time_limit=240)
def classify_document(document_id: str) -> dict[str, str]:
    storage = ObjectStorageService()
    scanner = MalwareScanService()
    with SessionLocal() as db:
        document = _get_document(db, document_id)
        document.status = "processing"
        _merge_metadata(
            document,
            {"pipeline_stage": "malware_scan", "classification_status": "running"},
        )
        db.commit()

        payload = storage.get_bytes(StorageObjectRef(bucket=storage.bucket, key=document.storage_key))
        scan_result = scanner.scan_bytes(payload)
        document.malware_scan_status = scan_result.status
        _merge_metadata(
            document,
            {
                "pipeline_stage": "classification",
                "classification_status": "completed" if scan_result.status == "clean" else "blocked",
                "malware_scan_detail": _sanitize_text(scan_result.detail),
            },
        )

        if scan_result.status != "clean":
            document.status = "failed"
            _record_pipeline_event(
                db,
                case_id=document.case_id,
                entity_id=str(document.id),
                event_type="document_scan_failed",
                details={"malware_scan_status": scan_result.status},
            )
            db.commit()
            return {"document_id": document_id, "status": "scan_failed"}

        db.commit()
        parse_task = parse_document.delay(document_id)
        document = _get_document(db, document_id)
        _merge_metadata(document, {"parse_task_id": parse_task.id})
        _record_pipeline_event(
            db,
            case_id=document.case_id,
            entity_id=str(document.id),
            event_type="document_scan_completed",
            details={"malware_scan_status": scan_result.status},
        )
        db.commit()
        return {"document_id": document_id, "status": "queued_for_parsing"}


@celery_app.task(name="documents.parse", time_limit=120, soft_time_limit=100)
def parse_document(document_id: str) -> dict[str, str]:
    storage = ObjectStorageService()
    parser_client = ParserClient()
    with SessionLocal() as db:
        document = _get_document(db, document_id)
        document.status = "processing"
        _merge_metadata(document, {"pipeline_stage": "parsing", "parser_status": "running"})
        db.commit()

        try:
            payload = storage.get_bytes(StorageObjectRef(bucket=storage.bucket, key=document.storage_key))
            parser_result = parser_client.parse_document(
                file_name=document.file_name,
                content_type=document.content_type,
                data=payload,
            )

            document.status = "ready"
            if parser_result.get("page_count") is not None:
                document.page_count = parser_result["page_count"]
            _merge_metadata(
                document,
                {
                    "pipeline_stage": "ready",
                    "parser_status": "completed",
                    "parse_summary": parser_result,
                    "unreadable": parser_result.get("unreadable", False),
                },
            )
            _record_pipeline_event(
                db,
                case_id=document.case_id,
                entity_id=str(document.id),
                event_type="document_parsed",
                details={"page_count": document.page_count, "parser_status": "completed"},
            )
            db.commit()
            return {"document_id": document_id, "status": "ready"}
        except Exception as exc:
            document.status = "failed"
            _merge_metadata(
                document,
                {
                    "pipeline_stage": "parse_failed",
                    "parser_status": "failed",
                    "parser_error": str(exc),
                },
            )
            _record_pipeline_event(
                db,
                case_id=document.case_id,
                entity_id=str(document.id),
                event_type="document_parse_failed",
                details={"error": str(exc)},
            )
            db.commit()
            raise


@celery_app.task(name="cases.evaluate", time_limit=3600, soft_time_limit=3300)
def evaluate_case(case_id: str) -> dict[str, str]:
    workflow_service = ReviewWorkflowService()
    with SessionLocal() as db:
        result = workflow_service.run_case_evaluation(db, UUID(case_id))
        _record_pipeline_event(
            db,
            case_id=UUID(case_id),
            entity_id=case_id,
            event_type="case_evaluation_completed",
            details={
                "candidate_count": result["candidate_count"],
                "evaluated_candidates": result["evaluated_candidates"],
                "rubric_id": result["rubric_id"],
            },
        )
        db.commit()
        return {key: str(value) for key, value in result.items()}


@celery_app.task(name="cases.run_expert_council")
def run_expert_council(case_id: str, candidate_id: str | None = None) -> dict[str, str]:
    workflow_service = ReviewWorkflowService()
    with SessionLocal() as db:
        result = workflow_service.run_expert_council(
            db,
            UUID(case_id),
            UUID(candidate_id) if candidate_id else None,
        )
        _record_pipeline_event(
            db,
            case_id=UUID(case_id),
            entity_id=case_id,
            event_type="expert_council_completed",
            details={
                "candidate_id": candidate_id,
                "candidate_count": result.get("candidate_count", 0),
                "expert_review_count": result.get("expert_review_count", 0),
            },
        )
        db.commit()
        return {key: "" if value is None else str(value) for key, value in result.items()}


def _get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, UUID(document_id))
    if document is None:
        raise ValueError(f"Document {document_id} not found.")
    return document


def _merge_metadata(document: Document, payload: dict) -> None:
    document.metadata_json = {**(document.metadata_json or {}), **payload}


def _record_pipeline_event(
    db: Session,
    *,
    case_id: UUID,
    entity_id: str,
    event_type: str,
    details: dict,
) -> None:
    raw = f"{event_type}:{entity_id}:{details}".encode("utf-8")
    db.add(
        AuditEvent(
            case_id=case_id,
            actor_id="system:pipeline",
            event_type=event_type,
            entity_type="document",
            entity_id=entity_id,
            details=details,
            immutable_hash=hashlib.sha256(raw).hexdigest(),
        )
    )


def _sanitize_text(value: str) -> str:
    return value.replace("\x00", "").strip()
