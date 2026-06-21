from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_items"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    document_id = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_page: Mapped[int | None]
    quote_text: Mapped[str | None] = mapped_column(Text)
    normalized_fact: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)


class CandidateFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_facts"

    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    fact_type: Mapped[str] = mapped_column(String(128))
    fact_value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_item_id = mapped_column(ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    unsupported: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class CandidateRating(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_ratings"

    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    rubric_dimension_id = mapped_column(ForeignKey("rubric_dimensions.id", ondelete="CASCADE"))
    rating: Mapped[str] = mapped_column(String(32))
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    evidence_summary: Mapped[str] = mapped_column(Text)
    source_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    strengths: Mapped[list[str]] = mapped_column(JSONB, default=list)
    concerns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    unsupported_areas: Mapped[list[str]] = mapped_column(JSONB, default=list)
    generated_by_model_run_id = mapped_column(ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True)
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_rationale: Mapped[str | None] = mapped_column(Text)


class ExpertAgent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expert_agents"

    agent_type: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ExpertReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "expert_reviews"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    expert_agent_id = mapped_column(ForeignKey("expert_agents.id", ondelete="SET NULL"), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    strengths: Mapped[list[str]] = mapped_column(JSONB, default=list)
    concerns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    model_run_id = mapped_column(ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True)


class ConsensusResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "consensus_results"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    consensus_summary: Mapped[str] = mapped_column(Text)
    agreement_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    dissent_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    unresolved_issues: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class ChallengeFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "challenge_findings"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    source_expert_review_id = mapped_column(ForeignKey("expert_reviews.id", ondelete="SET NULL"), nullable=True)
    challenge_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class PairwiseComparison(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pairwise_comparisons"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    left_candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    right_candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    winner_candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    rationale: Mapped[str] = mapped_column(Text)
    dimension_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class SelectionRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "selection_recommendations"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    recommendation_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    selectee_candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    alternate_candidate_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    interview_slate_candidate_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    discarded_candidate_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    non_selection_rationale: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence_ledger: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    remaining_validation_issues: Mapped[list[str]] = mapped_column(JSONB, default=list)


class InterviewQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_questions"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(64))
    question_text: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)


class InterviewResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interview_results"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    panel_notes: Mapped[str | None] = mapped_column(Text)
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class BoardMeetingTranscript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "board_meeting_transcripts"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    candidate_name: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    agent_count: Mapped[int] = mapped_column(default=0)
    round_count: Mapped[int] = mapped_column(default=0)
    phase1_turns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    phase2_turns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    phase3_synthesis: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    full_transcript: Mapped[str | None] = mapped_column(Text)
    meeting_notes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    meeting_summary: Mapped[str | None] = mapped_column(Text)
