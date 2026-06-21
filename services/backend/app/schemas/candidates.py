from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.domain.enums import CandidateDisposition
from app.schemas.common import ORMModel, TimestampedResponse


class CandidateRead(TimestampedResponse):
    full_name: str
    email: str | None
    certificate_identifier: str | None
    disposition: CandidateDisposition
    profile: dict


class CandidateCreateRequest(BaseModel):
    full_name: str
    email: str | None = None
    certificate_identifier: str | None = None


class CandidateMergeRequest(BaseModel):
    source_candidate_id: UUID
    target_candidate_id: UUID


class CandidateMatchRead(TimestampedResponse):
    candidate_id: UUID
    candidate_name: str
    candidate_email: str | None
    resume_segment_id: UUID | None
    resume_document_name: str | None
    segment_start_page: int | None
    segment_end_page: int | None
    inferred_name: str | None
    inferred_email: str | None
    matched_name: str | None
    matched_email: str | None
    confidence: Decimal
    is_duplicate: bool
    notes: str | None


class CandidateReconciliationSummary(BaseModel):
    case_id: str
    candidate_count: int
    matched_count: int
    unmatched_count: int
    duplicate_count: int
    resume_segment_count: int
    unmatched_segment_count: int


class CandidateMatchUpdateRequest(BaseModel):
    resume_segment_id: UUID | None = None
    notes: str | None = None


class ResumeSegmentRead(TimestampedResponse):
    document_id: UUID
    candidate_id: UUID | None
    inferred_name: str | None
    inferred_email: str | None
    start_page: int
    end_page: int
    confidence: Decimal
    notes: str | None
    parsed_profile: dict | None = None


class CandidateMatchDetail(ORMModel):
    id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str | None
    resume_segment_id: UUID | None
    resume_document_name: str | None
    segment_start_page: int | None
    segment_end_page: int | None
    inferred_name: str | None
    inferred_email: str | None
    matched_name: str | None
    matched_email: str | None
    confidence: Decimal
    is_duplicate: bool
    notes: str | None


class CandidateReconciliationResult(BaseModel):
    summary: CandidateReconciliationSummary
    matches: list[CandidateMatchDetail]
    segments: list[ResumeSegmentRead]
