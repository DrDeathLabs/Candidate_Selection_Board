from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import (
    CandidateDisposition,
    CaseStatus,
    DataSensitivity,
    DocumentStatus,
    DocumentType,
)
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReviewCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_cases"

    title: Mapped[str] = mapped_column(String(255))
    series: Mapped[str | None] = mapped_column(String(32))
    grade: Mapped[str | None] = mapped_column(String(32))
    organization: Mapped[str | None] = mapped_column(String(255))
    hiring_action_type: Mapped[str | None] = mapped_column(String(128))
    certificate_number: Mapped[str | None] = mapped_column(String(128))
    selecting_official: Mapped[str | None] = mapped_column(String(255))
    panel_members: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    data_sensitivity: Mapped[DataSensitivity] = mapped_column(String(32), default=DataSensitivity.MODERATE.value)
    retention_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_provider_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    outside_enrichment_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[CaseStatus] = mapped_column(String(32), default=CaseStatus.DRAFT.value)

    documents: Mapped[list["Document"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    rubrics: Mapped[list["Rubric"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    storage_key: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str | None] = mapped_column(String(128))
    document_type: Mapped[DocumentType] = mapped_column(String(64), default=DocumentType.OTHER.value)
    status: Mapped[DocumentStatus] = mapped_column(String(32), default=DocumentStatus.UPLOADED.value)
    page_count: Mapped[int | None]
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    malware_scan_status: Mapped[str] = mapped_column(String(32), default="pending")

    case: Mapped[ReviewCase] = relationship(back_populates="documents")
    resume_segments: Mapped[list["ResumeSegment"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidates"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    certificate_identifier: Mapped[str | None] = mapped_column(String(128))
    disposition: Mapped[CandidateDisposition] = mapped_column(
        String(32), default=CandidateDisposition.UNDER_REVIEW.value
    )
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    case: Mapped[ReviewCase] = relationship(back_populates="candidates")
    resume_segments: Mapped[list["ResumeSegment"]] = relationship(back_populates="candidate")
    candidate_matches: Mapped[list["CandidateMatch"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class ResumeSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resume_segments"

    document_id = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    inferred_name: Mapped[str | None] = mapped_column(String(255))
    inferred_email: Mapped[str | None] = mapped_column(String(255))
    start_page: Mapped[int]
    end_page: Mapped[int]
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    parsed_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    document: Mapped[Document] = relationship(back_populates="resume_segments")
    candidate: Mapped[Candidate | None] = relationship(back_populates="resume_segments")
    candidate_matches: Mapped[list["CandidateMatch"]] = relationship(back_populates="resume_segment")


class CandidateMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_matches"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    resume_segment_id = mapped_column(ForeignKey("resume_segments.id", ondelete="SET NULL"), nullable=True)
    matched_name: Mapped[str | None] = mapped_column(String(255))
    matched_email: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    candidate: Mapped[Candidate] = relationship(back_populates="candidate_matches")
    resume_segment: Mapped[ResumeSegment | None] = relationship(back_populates="candidate_matches")


class PositionAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "position_analyses"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"), index=True)
    role_type: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    duties: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    critical_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    recommended_dimensions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    evidence_map: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Rubric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubrics"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"), index=True)
    position_analysis_id = mapped_column(ForeignKey("position_analyses.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    version: Mapped[int] = mapped_column(default=1)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    total_weight: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=100)

    case: Mapped[ReviewCase] = relationship(back_populates="rubrics")
    dimensions: Mapped[list["RubricDimension"]] = relationship(back_populates="rubric", cascade="all, delete-orphan")


class RubricDimension(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rubric_dimensions"

    rubric_id = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    order_index: Mapped[int]
    evidence_links: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    rubric: Mapped[Rubric] = relationship(back_populates="dimensions")
