from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import TimestampedResponse


class RankedCandidateRead(BaseModel):
    candidate_id: str
    candidate_name: str
    disposition: str
    score: Decimal
    confidence: Decimal
    evaluation_score: Decimal
    expert_confidence: Decimal
    resume_confidence: Decimal
    interview_score: Decimal | None
    challenge_count: int
    matched_resume: str | None
    consensus_summary: str | None
    strengths: list[str]
    concerns: list[str]
    notes: str | None


class SelectionRecommendationRead(TimestampedResponse):
    case_id: str
    recommendation_type: str
    status: str
    selectee_candidate_id: str | None
    selectee_candidate_name: str | None
    alternate_candidate_ids: list[str]
    alternate_candidate_names: list[str]
    interview_slate_candidate_ids: list[str]
    interview_slate_candidate_names: list[str]
    discarded_candidate_ids: list[str]
    discarded_candidate_names: list[str]
    rationale: str
    non_selection_rationale: dict
    evidence_ledger: list[dict]
    confidence: Decimal
    remaining_validation_issues: list[str]
    rankings: list[RankedCandidateRead]
