from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.models.case import Candidate, CandidateMatch, Document, ResumeSegment
from app.schemas.candidates import (
    CandidateCreateRequest,
    CandidateMatchRead,
    CandidateMatchUpdateRequest,
    CandidateMergeRequest,
    CandidateRead,
    CandidateReconciliationResult,
    CandidateReconciliationSummary,
    ResumeSegmentRead,
)
from app.services.audit import AuditRecorder
from app.services.reconciliation import ReconciliationService

router = APIRouter()
audit = AuditRecorder()
reconciliation_service = ReconciliationService()


@router.get("/", response_model=list[CandidateRead])
def list_candidates(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[Candidate]:
    return db.query(Candidate).filter(Candidate.case_id == case_id).order_by(Candidate.full_name).all()


@router.post("/", response_model=CandidateRead)
def create_candidate(
    case_id: UUID,
    payload: CandidateCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> Candidate:
    candidate = reconciliation_service.create_manual_candidate(
        db,
        case_id=case_id,
        full_name=payload.full_name,
        email=payload.email,
        certificate_identifier=payload.certificate_identifier,
    )
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.CANDIDATE_MATCH_CHANGE,
        entity_type="candidate",
        entity_id=str(candidate.id),
        details={
            "case_id": str(case_id),
            "action": "create",
            "full_name": candidate.full_name,
            "email": candidate.email,
        },
        case_id=case_id,
    )
    db.commit()
    return candidate


@router.get("/reconciliation", response_model=CandidateReconciliationSummary)
def reconciliation_summary(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> CandidateReconciliationSummary:
    candidates = db.query(Candidate).filter(Candidate.case_id == case_id).all()
    matches = db.query(CandidateMatch).filter(CandidateMatch.case_id == case_id).all()
    segments = db.query(ResumeSegment).join(Document).filter(Document.case_id == case_id).all()
    matched_count = sum(1 for match in matches if match.resume_segment_id is not None)
    duplicate_count = sum(1 for match in matches if match.is_duplicate)
    return CandidateReconciliationSummary(
        case_id=str(case_id),
        candidate_count=len(candidates),
        matched_count=matched_count,
        unmatched_count=max(len(candidates) - matched_count, 0),
        duplicate_count=duplicate_count,
        resume_segment_count=len(segments),
        unmatched_segment_count=sum(1 for segment in segments if segment.candidate_id is None),
    )


@router.get("/matches", response_model=list[CandidateMatchRead])
def list_candidate_matches(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[CandidateMatch]:
    # Single query with eager-loaded associations to eliminate N+1
    matches = (
        db.query(CandidateMatch)
        .filter(CandidateMatch.case_id == case_id)
        .options(
            joinedload(CandidateMatch.candidate),
            joinedload(CandidateMatch.resume_segment).joinedload(ResumeSegment.document),
        )
        .all()
    )
    return [
        CandidateMatchRead(
            id=match.id,
            created_at=match.created_at,
            updated_at=match.updated_at,
            candidate_id=match.candidate_id,
            candidate_name=match.candidate.full_name if match.candidate else None,
            candidate_email=match.candidate.email if match.candidate else None,
            resume_segment_id=match.resume_segment_id,
            resume_document_name=match.resume_segment.document.file_name if match.resume_segment else None,
            segment_start_page=match.resume_segment.start_page if match.resume_segment else None,
            segment_end_page=match.resume_segment.end_page if match.resume_segment else None,
            inferred_name=match.resume_segment.inferred_name if match.resume_segment else None,
            inferred_email=match.resume_segment.inferred_email if match.resume_segment else None,
            matched_name=match.matched_name,
            matched_email=match.matched_email,
            confidence=match.confidence,
            is_duplicate=match.is_duplicate,
            notes=match.notes,
        )
        for match in matches
    ]


@router.get("/resume-segments", response_model=list[ResumeSegmentRead])
def list_resume_segments(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[ResumeSegmentRead]:
    segments = reconciliation_service.get_case_result(db, case_id).segments
    return segments


@router.post("/reconcile", response_model=CandidateReconciliationResult)
def reconcile_candidates(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> CandidateReconciliationResult:
    result = reconciliation_service.reconcile_case(db, case_id)
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.CANDIDATE_MATCH_CHANGE,
        entity_type="review_case",
        entity_id=str(case_id),
        details={
            "candidate_count": result.summary.candidate_count,
            "matched_count": result.summary.matched_count,
            "resume_segment_count": result.summary.resume_segment_count,
        },
        case_id=case_id,
    )
    db.commit()
    return result


@router.put("/{candidate_id}/match", response_model=CandidateReconciliationResult)
def update_candidate_match(
    case_id: UUID,
    candidate_id: UUID,
    payload: CandidateMatchUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> CandidateReconciliationResult:
    result = reconciliation_service.assign_segment_to_candidate(
        db,
        case_id=case_id,
        candidate_id=candidate_id,
        resume_segment_id=payload.resume_segment_id,
        notes=payload.notes,
    )
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.CANDIDATE_MATCH_CHANGE,
        entity_type="candidate",
        entity_id=str(candidate_id),
        details={
            "case_id": str(case_id),
            "resume_segment_id": str(payload.resume_segment_id) if payload.resume_segment_id else None,
            "action": "assign" if payload.resume_segment_id else "clear",
            "notes": payload.notes,
        },
        case_id=case_id,
    )
    db.commit()
    return result


@router.post("/merge", response_model=CandidateReconciliationResult)
def merge_candidates(
    case_id: UUID,
    payload: CandidateMergeRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.CASE_OWNER, RoleName.SYSTEM_ADMINISTRATOR)),
) -> CandidateReconciliationResult:
    result = reconciliation_service.merge_candidates(
        db,
        case_id=case_id,
        source_candidate_id=payload.source_candidate_id,
        target_candidate_id=payload.target_candidate_id,
    )
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.CANDIDATE_MATCH_CHANGE,
        entity_type="candidate",
        entity_id=str(payload.target_candidate_id),
        details={
            "case_id": str(case_id),
            "action": "merge",
            "source_candidate_id": str(payload.source_candidate_id),
            "target_candidate_id": str(payload.target_candidate_id),
        },
        case_id=case_id,
    )
    db.commit()
    return result
