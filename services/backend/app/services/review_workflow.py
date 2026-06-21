from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Any
from uuid import UUID

import redis as redis_lib
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import CandidateDisposition, ExpertAgentType, RatingValue
from app.models.case import (
    Candidate,
    CandidateMatch,
    Document,
    PositionAnalysis,
    ResumeSegment,
    ReviewCase,
    Rubric,
    RubricDimension,
)
from app.models.evaluation import (
    CandidateFact,
    CandidateRating,
    ChallengeFinding,
    ConsensusResult,
    EvidenceItem,
    ExpertAgent,
    ExpertReview,
    InterviewQuestion,
    PairwiseComparison,
    SelectionRecommendation,
)
from app.models.system import ModelRun
from app.services.ai_inference import AIGatewayClient, GatewayInvocationRequest, GatewayInvocationResponse
from app.services.council_deliberation import CouncilDeliberationService
from app.services.reconciliation import ReconciliationService

_settings = get_settings()


def _stop_flag_set(case_id: UUID) -> bool:
    try:
        r = redis_lib.Redis(host=_settings.redis_host, port=_settings.redis_port, db=2, decode_responses=True)
        return bool(r.get(f"council_stop:{case_id}"))
    except Exception:
        return False


def _clear_stop_flag(case_id: UUID) -> None:
    try:
        r = redis_lib.Redis(host=_settings.redis_host, port=_settings.redis_port, db=2, decode_responses=True)
        r.delete(f"council_stop:{case_id}")
    except Exception:
        pass


STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "only",
    "your",
    "their",
    "have",
    "will",
    "been",
    "were",
    "about",
    "against",
    "role",
    "candidate",
    "position",
    "board",
    "review",
    "evidence",
}

TECHNOLOGY_KEYWORDS = (
    "aws",
    "azure",
    "gcp",
    "cloud",
    "devsecops",
    "agile",
    "kubernetes",
    "docker",
    "python",
    "java",
    "react",
    "salesforce",
    "servicenow",
    "linux",
    "windows",
    "network",
    "security",
    "zero trust",
    "automation",
    "terraform",
    "ansible",
    "ci/cd",
    "data",
    "analytics",
)

FOCUS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "leadership": ("supervis", "led", "managed", "director", "chief", "team", "branch", "division", "program manager"),
    "technical-alignment": (
        "system",
        "application",
        "platform",
        "architecture",
        "engineering",
        "cloud",
        "software",
        "data",
    ),
    "mission-fit": ("mission", "stakeholder", "policy", "public", "customer", "service", "federal", "agency"),
    "budget-acquisition": ("budget", "acquisition", "contract", "procurement", "vendor", "purchase", "fiscal"),
    "operations": ("operations", "sustainment", "incident", "production", "continuity", "service delivery", "o&m"),
    "modernization": ("modernization", "transformation", "delivery", "agile", "devsecops", "automation", "cloud"),
    "evidence-skepticism": ("supported", "measured", "metric", "result", "outcome", "scope", "portfolio"),
    "compliance": ("policy", "oversight", "governance", "controls", "privacy", "security", "compliance"),
}

RATING_SCALE: dict[str, Decimal] = {
    RatingValue.EXCEEDS.value: Decimal("5.00"),
    RatingValue.MEETS.value: Decimal("4.00"),
    RatingValue.PARTIAL.value: Decimal("2.75"),
    RatingValue.DOES_NOT_MEET.value: Decimal("1.50"),
    RatingValue.UNSUPPORTED.value: Decimal("0.50"),
}

RATING_ORDER = {
    RatingValue.EXCEEDS.value: 5,
    RatingValue.MEETS.value: 4,
    RatingValue.PARTIAL.value: 3,
    RatingValue.DOES_NOT_MEET.value: 2,
    RatingValue.UNSUPPORTED.value: 1,
}

YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
CERT_PATTERN = re.compile(r"\b(PMP|CISSP|Security\+|AWS|Azure|ITIL|Scrum|SAFe|CCNA|CEH)\b", re.IGNORECASE)
EDUCATION_PATTERN = re.compile(
    r"\b(PhD|Doctorate|Master(?:'s)?|MBA|Bachelor(?:'s)?|B\.S\.|B\.A\.|M\.S\.|M\.A\.)\b", re.IGNORECASE
)


@dataclass(slots=True)
class CandidateContext:
    candidate: Candidate
    match: CandidateMatch | None
    segment: ResumeSegment | None
    resume_text: str
    resume_pages: list[dict[str, Any]]
    top_quotes: list[dict[str, Any]]


class ReviewWorkflowService:
    def __init__(self) -> None:
        self.reconciliation_service = ReconciliationService()
        self.ai_gateway_client = AIGatewayClient()
        self.council_service = CouncilDeliberationService()

    def run_case_evaluation(self, db: Session, case_id: UUID) -> dict[str, Any]:
        case = self._get_case(db, case_id)
        rubric = self._get_active_rubric(db, case_id)

        self.reconciliation_service.reconcile_case(db, case_id)
        self._clear_case_outputs(db, case_id, clear_evaluations=True, clear_reviews=False)

        candidates = db.scalars(
            select(Candidate).where(Candidate.case_id == case_id).order_by(Candidate.full_name.asc())
        ).all()
        contexts = self._build_candidate_contexts(db, case_id, candidates)
        resume_analyst = self._get_agent(db, ExpertAgentType.RESUME_EVIDENCE_ANALYST.value)

        evaluated_candidates = 0
        for context in contexts:
            if not context.resume_text.strip():
                continue
            evaluated_candidates += 1

            facts = self._derive_candidate_facts(context)
            fact_rows = self._persist_candidate_facts(db, case_id, context, facts)
            ai_rating_pack = self._generate_candidate_rating_pack(db, case, rubric, context, facts, resume_analyst)
            self._persist_candidate_ratings(db, rubric, context, facts, ai_rating_pack)
            self._persist_interview_questions(db, case_id, context)

            context.candidate.profile = {
                **(context.candidate.profile or {}),
                "resume_match_confidence": str(context.match.confidence) if context.match else "0.00",
                "extracted_fact_count": len(fact_rows),
                "evaluation_summary": ai_rating_pack.get("summary")
                if ai_rating_pack
                else "Generated from resume evidence and rubric fit.",
            }

        case.status = "review"
        db.commit()
        return {
            "case_id": str(case_id),
            "candidate_count": len(candidates),
            "evaluated_candidates": evaluated_candidates,
            "rubric_id": str(rubric.id),
            "status": "completed",
        }

    def run_expert_council(self, db: Session, case_id: UUID, candidate_id: UUID | None = None) -> dict[str, Any]:
        case = self._get_case(db, case_id)
        candidates = self._load_target_candidates(db, case_id, candidate_id)
        if not candidates:
            return {"case_id": str(case_id), "candidate_count": 0, "status": "no_candidates"}

        if not db.scalar(select(CandidateRating).join(Candidate).where(Candidate.case_id == case_id)):
            self.run_case_evaluation(db, case_id)

        self._clear_case_outputs(db, case_id, clear_evaluations=False, clear_reviews=True, candidate_id=candidate_id)
        position_analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == case_id))
        rubric = self._get_active_rubric(db, case_id)
        expert_agents = db.scalars(
            select(ExpertAgent).where(ExpertAgent.enabled.is_(True)).order_by(ExpertAgent.display_name.asc())
        ).all()

        _clear_stop_flag(case_id)
        candidate_contexts = self._build_candidate_contexts(db, case_id, candidates)
        review_count = 0
        for context in candidate_contexts:
            if _stop_flag_set(case_id):
                _clear_stop_flag(case_id)
                break
            ratings = self._load_candidate_ratings(db, context.candidate.id)
            facts = self._load_candidate_facts(db, context.candidate.id)
            composite_score = self._calculate_candidate_score(db, context.candidate.id)

            # Load tier thresholds from the resume_review stage config (if set)
            _plan = (case.retention_settings or {}).get("workflow_plan_v2") or {}
            _resume_stage = next((s for s in _plan.get("stages", []) if s.get("template_key") == "resume_review"), {})
            _stage_cfg = _resume_stage.get("config") or {}
            tier_a_threshold = Decimal(str(_stage_cfg.get("tier_a_threshold", "82.00")))
            tier_b_threshold = Decimal(str(_stage_cfg.get("tier_b_threshold", "68.00")))

            # Run multi-agent council deliberation
            state = self.council_service.run_council_session(
                db,
                case,
                position_analysis,
                rubric,
                context,
                facts,
                ratings,
                expert_agents,
                composite_score=composite_score,
                tier_a_threshold=tier_a_threshold,
                tier_b_threshold=tier_b_threshold,
            )

            # Persist individual ExpertReview records (backward compat) from Phase I turns
            for turn in state.turns:
                if turn.phase == "opening" and turn.speaker != "council_chair":
                    agent = next((a for a in expert_agents if a.agent_type == turn.speaker), None)
                    if agent:
                        payload = {
                            "summary": turn.summary or turn.content[:500],
                            "findings": turn.findings,
                            "strengths": turn.strengths,
                            "concerns": turn.concerns,
                            "confidence": turn.confidence,
                        }
                        self._persist_expert_review(db, case_id, context.candidate.id, agent, payload)
                        review_count += 1

            # Persist skeptic/deliberation reviews as ExpertReview too
            for turn in state.turns:
                if turn.phase == "deliberation" and not turn.responding_to:
                    agent = next((a for a in expert_agents if a.agent_type == turn.speaker), None)
                    if agent:
                        payload = {
                            "summary": turn.summary or turn.content[:500],
                            "findings": turn.findings,
                            "strengths": turn.strengths,
                            "concerns": turn.concerns,
                            "confidence": turn.confidence,
                        }
                        self._persist_expert_review(db, case_id, context.candidate.id, agent, payload)
                        review_count += 1

            # Persist consensus from chair's synthesis
            self._persist_consensus_from_state(db, case_id, context.candidate.id, state)

            # Persist full board meeting transcript
            transcript = self.council_service.format_full_transcript(state, case)
            notes = self.council_service.build_meeting_notes(state)
            chair_agent = next((a for a in expert_agents if a.agent_type == "selection_reviewer"), None)
            summary = self.council_service.generate_meeting_summary(db, state, chair_agent)
            self.council_service.persist_board_meeting(db, state, transcript, notes, summary)

            # Commit after each candidate so progress is visible immediately
            db.commit()

        self._persist_pairwise_comparisons(db, case_id)
        case.status = "review"
        db.commit()
        return {
            "case_id": str(case_id),
            "candidate_count": len(candidates),
            "expert_review_count": review_count,
            "status": "completed",
        }

    def list_candidate_evaluations(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        candidates = db.scalars(
            select(Candidate).where(Candidate.case_id == case_id).order_by(Candidate.full_name.asc())
        ).all()
        matches = {
            match.candidate_id: match
            for match in db.scalars(select(CandidateMatch).where(CandidateMatch.case_id == case_id)).all()
        }
        ratings_by_candidate = defaultdict(list)
        for rating in db.scalars(select(CandidateRating).join(Candidate).where(Candidate.case_id == case_id)).all():
            ratings_by_candidate[rating.candidate_id].append(rating)
        facts_by_candidate = defaultdict(list)
        for fact in db.scalars(select(CandidateFact).join(Candidate).where(Candidate.case_id == case_id)).all():
            facts_by_candidate[fact.candidate_id].append(fact)

        summaries: list[dict[str, Any]] = []
        for candidate in candidates:
            ratings = ratings_by_candidate[candidate.id]
            overall_score = self._calculate_candidate_score(db, candidate.id)
            summaries.append(
                {
                    "candidate_id": str(candidate.id),
                    "candidate_name": candidate.full_name,
                    "candidate_email": candidate.email,
                    "disposition": candidate.disposition,
                    "matched_resume": matches[candidate.id].matched_name if candidate.id in matches else None,
                    "resume_confidence": str(matches[candidate.id].confidence) if candidate.id in matches else "0.00",
                    "overall_score": str(overall_score),
                    "fact_count": len(facts_by_candidate[candidate.id]),
                    "ratings": [
                        {
                            "id": str(rating.id),
                            "dimension_id": str(rating.rubric_dimension_id),
                            "rating": rating.rating,
                            "score": str(rating.score),
                            "confidence": str(rating.confidence),
                            "evidence_summary": rating.evidence_summary,
                            "strengths": rating.strengths,
                            "concerns": rating.concerns,
                            "unsupported_areas": rating.unsupported_areas,
                        }
                        for rating in sorted(ratings, key=lambda entry: str(entry.rubric_dimension_id))
                    ],
                }
            )
        return summaries

    def list_candidate_facts(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        candidates = {
            candidate.id: candidate
            for candidate in db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        }
        evidence_items = {
            item.id: item for item in db.scalars(select(EvidenceItem).where(EvidenceItem.case_id == case_id)).all()
        }
        facts = db.scalars(
            select(CandidateFact)
            .join(Candidate)
            .where(Candidate.case_id == case_id)
            .order_by(CandidateFact.created_at.asc())
        ).all()
        return [
            {
                "id": str(fact.id),
                "candidate_id": str(fact.candidate_id),
                "candidate_name": candidates[fact.candidate_id].full_name,
                "fact_type": fact.fact_type,
                "fact_value": fact.fact_value,
                "confidence": str(fact.confidence),
                "unsupported": fact.unsupported,
                "notes": fact.notes,
                "evidence_quote": evidence_items[fact.evidence_item_id].quote_text
                if fact.evidence_item_id in evidence_items
                else None,
                "source_page": evidence_items[fact.evidence_item_id].source_page
                if fact.evidence_item_id in evidence_items
                else None,
            }
            for fact in facts
        ]

    def list_expert_reviews(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        candidates = {
            candidate.id: candidate
            for candidate in db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        }
        reviews = db.scalars(
            select(ExpertReview).where(ExpertReview.case_id == case_id).order_by(ExpertReview.created_at.asc())
        ).all()
        return [
            {
                "id": str(review.id),
                "candidate_id": str(review.candidate_id),
                "candidate_name": candidates[review.candidate_id].full_name,
                "agent_type": review.agent_type,
                "status": review.status,
                "summary": review.summary,
                "findings": review.findings,
                "strengths": review.strengths,
                "concerns": review.concerns,
                "confidence": str(review.confidence),
                "created_at": review.created_at.isoformat(),
                "updated_at": review.updated_at.isoformat(),
            }
            for review in reviews
        ]

    def list_pairwise_comparisons(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        candidates = {
            candidate.id: candidate
            for candidate in db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        }
        comparisons = db.scalars(
            select(PairwiseComparison)
            .where(PairwiseComparison.case_id == case_id)
            .order_by(PairwiseComparison.created_at.asc())
        ).all()
        return [
            {
                "id": str(comparison.id),
                "left_candidate_id": str(comparison.left_candidate_id),
                "left_candidate_name": candidates[comparison.left_candidate_id].full_name,
                "right_candidate_id": str(comparison.right_candidate_id),
                "right_candidate_name": candidates[comparison.right_candidate_id].full_name,
                "winner_candidate_id": str(comparison.winner_candidate_id) if comparison.winner_candidate_id else None,
                "winner_candidate_name": candidates[comparison.winner_candidate_id].full_name
                if comparison.winner_candidate_id in candidates
                else None,
                "rationale": comparison.rationale,
                "dimension_results": comparison.dimension_results,
                "confidence": str(comparison.confidence),
            }
            for comparison in comparisons
        ]

    def list_interview_questions(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        candidates = {
            candidate.id: candidate
            for candidate in db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        }
        questions = db.scalars(
            select(InterviewQuestion)
            .where(InterviewQuestion.case_id == case_id)
            .order_by(InterviewQuestion.created_at.asc())
        ).all()
        return [
            {
                "id": str(question.id),
                "candidate_id": str(question.candidate_id),
                "candidate_name": candidates[question.candidate_id].full_name,
                "category": question.category,
                "question_text": question.question_text,
                "rationale": question.rationale,
                "evidence_references": question.evidence_references,
            }
            for question in questions
        ]

    def _get_case(self, db: Session, case_id: UUID) -> ReviewCase:
        case = db.get(ReviewCase, case_id)
        if case is None:
            raise ValueError("Review case not found.")
        return case

    def _get_active_rubric(self, db: Session, case_id: UUID) -> Rubric:
        rubric = db.scalar(
            select(Rubric).where(Rubric.case_id == case_id).order_by(Rubric.is_locked.desc(), Rubric.updated_at.desc())
        )
        if rubric is None:
            raise ValueError("No rubric is available for this case.")
        return rubric

    def _get_agent(self, db: Session, agent_type: str) -> ExpertAgent | None:
        return db.scalar(select(ExpertAgent).where(ExpertAgent.agent_type == agent_type))

    def _load_target_candidates(self, db: Session, case_id: UUID, candidate_id: UUID | None) -> list[Candidate]:
        statement = select(Candidate).where(Candidate.case_id == case_id).order_by(Candidate.full_name.asc())
        if candidate_id is not None:
            statement = statement.where(Candidate.id == candidate_id)
        return db.scalars(statement).all()

    def _build_candidate_contexts(
        self, db: Session, case_id: UUID, candidates: list[Candidate]
    ) -> list[CandidateContext]:
        matches = {
            match.candidate_id: match
            for match in db.scalars(select(CandidateMatch).where(CandidateMatch.case_id == case_id)).all()
        }
        segments = {
            segment.id: segment
            for segment in db.scalars(select(ResumeSegment).join(Document).where(Document.case_id == case_id)).all()
        }

        contexts: list[CandidateContext] = []
        for candidate in candidates:
            match = matches.get(candidate.id)
            segment = segments.get(match.resume_segment_id) if match and match.resume_segment_id else None
            resume_pages = self._extract_resume_pages(segment)
            resume_text = "\n\n".join(page["text"] for page in resume_pages if page["text"]).strip()
            top_quotes = self._extract_top_quotes(resume_pages)
            contexts.append(
                CandidateContext(
                    candidate=candidate,
                    match=match,
                    segment=segment,
                    resume_text=resume_text,
                    resume_pages=resume_pages,
                    top_quotes=top_quotes,
                )
            )
        return contexts

    def _clear_case_outputs(
        self,
        db: Session,
        case_id: UUID,
        *,
        clear_evaluations: bool,
        clear_reviews: bool,
        candidate_id: UUID | None = None,
    ) -> None:
        statement = select(Candidate.id).where(Candidate.case_id == case_id)
        if candidate_id is not None:
            statement = statement.where(Candidate.id == candidate_id)
        candidate_ids = list(db.scalars(statement).all())
        if not candidate_ids:
            return

        if clear_reviews:
            db.execute(delete(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id))
            db.execute(delete(PairwiseComparison).where(PairwiseComparison.case_id == case_id))
            db.execute(delete(ChallengeFinding).where(ChallengeFinding.case_id == case_id))
            db.execute(delete(ConsensusResult).where(ConsensusResult.case_id == case_id))
            db.execute(
                delete(ExpertReview).where(
                    ExpertReview.case_id == case_id,
                    ExpertReview.candidate_id.in_(candidate_ids),
                )
            )

        if clear_evaluations:
            db.execute(
                delete(InterviewQuestion).where(
                    InterviewQuestion.case_id == case_id, InterviewQuestion.candidate_id.in_(candidate_ids)
                )
            )
            db.execute(delete(CandidateRating).where(CandidateRating.candidate_id.in_(candidate_ids)))
            db.execute(delete(CandidateFact).where(CandidateFact.candidate_id.in_(candidate_ids)))
            db.execute(
                delete(EvidenceItem).where(
                    EvidenceItem.case_id == case_id, EvidenceItem.candidate_id.in_(candidate_ids)
                )
            )
            db.execute(delete(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id))
            db.execute(delete(PairwiseComparison).where(PairwiseComparison.case_id == case_id))
            db.execute(delete(ChallengeFinding).where(ChallengeFinding.case_id == case_id))
            db.execute(delete(ConsensusResult).where(ConsensusResult.case_id == case_id))
            db.execute(
                delete(ExpertReview).where(
                    ExpertReview.case_id == case_id, ExpertReview.candidate_id.in_(candidate_ids)
                )
            )

        db.flush()

    def _extract_resume_pages(self, segment: ResumeSegment | None) -> list[dict[str, Any]]:
        if segment is None or segment.document is None:
            return []
        parse_summary = segment.document.metadata_json.get("parse_summary", {})
        pages = parse_summary.get("pages") or []
        if pages:
            return [
                {
                    "page_number": int(page.get("page_number", 1)),
                    "text": str(page.get("text") or "").strip(),
                }
                for page in pages
                if segment.start_page <= int(page.get("page_number", 1)) <= segment.end_page
            ]
        if segment.notes:
            return [{"page_number": segment.start_page, "text": segment.notes}]
        return []

    def _extract_top_quotes(self, resume_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        quotes: list[dict[str, Any]] = []
        for page in resume_pages:
            for raw_line in page["text"].splitlines():
                line = raw_line.strip().strip("-*")
                if len(line) < 35:
                    continue
                quotes.append({"page_number": page["page_number"], "quote_text": line[:320]})
                if len(quotes) == 6:
                    return quotes
        return quotes

    def _derive_candidate_facts(self, context: CandidateContext) -> list[dict[str, Any]]:
        text = context.resume_text
        lowered = text.lower()
        facts: list[dict[str, Any]] = []
        years = sorted({int(value.group(0)) for value in YEAR_PATTERN.finditer(text)})
        if years:
            years_experience = max(years) - min(years)
            facts.append(
                {
                    "fact_type": "career_span_years",
                    "fact_value": {"value": years_experience, "first_year": min(years), "last_year": max(years)},
                    "quote_text": self._find_line_with_any(text, tuple(str(year) for year in years[:3])),
                    "source_page": self._find_page_for_keywords(
                        context.resume_pages, tuple(str(year) for year in years[:3])
                    ),
                    "confidence": Decimal("0.72"),
                    "notes": "Estimated from year ranges found in the resume.",
                }
            )

        education_matches = list(dict.fromkeys(match.group(0) for match in EDUCATION_PATTERN.finditer(text)))
        if education_matches:
            facts.append(
                {
                    "fact_type": "education",
                    "fact_value": {"degrees": education_matches},
                    "quote_text": self._find_line_with_any(text, tuple(education_matches)),
                    "source_page": self._find_page_for_keywords(context.resume_pages, tuple(education_matches)),
                    "confidence": Decimal("0.82"),
                    "notes": "Education signal detected from resume text.",
                }
            )

        certifications = list(dict.fromkeys(match.group(0).upper() for match in CERT_PATTERN.finditer(text)))
        if certifications:
            facts.append(
                {
                    "fact_type": "certifications",
                    "fact_value": {"certifications": certifications},
                    "quote_text": self._find_line_with_any(text, tuple(certifications)),
                    "source_page": self._find_page_for_keywords(context.resume_pages, tuple(certifications)),
                    "confidence": Decimal("0.86"),
                    "notes": "Certification keywords found in the resume.",
                }
            )

        technologies = [keyword for keyword in TECHNOLOGY_KEYWORDS if keyword in lowered]
        if technologies:
            facts.append(
                {
                    "fact_type": "technology_domains",
                    "fact_value": {"keywords": technologies[:10]},
                    "quote_text": self._find_line_with_any(text, tuple(technologies[:5])),
                    "source_page": self._find_page_for_keywords(context.resume_pages, tuple(technologies[:5])),
                    "confidence": Decimal("0.78"),
                    "notes": "Technology and delivery keywords extracted from the resume.",
                }
            )

        for fact_type, keywords in (
            ("leadership_scope", FOCUS_KEYWORDS["leadership"]),
            ("budget_acquisition", FOCUS_KEYWORDS["budget-acquisition"]),
            ("operations", FOCUS_KEYWORDS["operations"]),
            ("modernization", FOCUS_KEYWORDS["modernization"]),
            ("cybersecurity", ("cyber", "security", "zero trust", "privacy")),
        ):
            if not self._has_keyword_hits(lowered, keywords):
                continue
            facts.append(
                {
                    "fact_type": fact_type,
                    "fact_value": {"keywords": [keyword for keyword in keywords if keyword in lowered][:6]},
                    "quote_text": self._find_line_with_any(text, keywords),
                    "source_page": self._find_page_for_keywords(context.resume_pages, keywords),
                    "confidence": Decimal("0.75"),
                    "notes": f"Keyword evidence found for {fact_type.replace('_', ' ')}.",
                }
            )

        if not facts and context.top_quotes:
            first_quote = context.top_quotes[0]
            facts.append(
                {
                    "fact_type": "general_experience",
                    "fact_value": {"summary": first_quote["quote_text"]},
                    "quote_text": first_quote["quote_text"],
                    "source_page": first_quote["page_number"],
                    "confidence": Decimal("0.60"),
                    "notes": "Fallback fact derived from the available resume excerpt.",
                }
            )
        return facts

    def _persist_candidate_facts(
        self,
        db: Session,
        case_id: UUID,
        context: CandidateContext,
        facts: list[dict[str, Any]],
    ) -> list[CandidateFact]:
        rows: list[CandidateFact] = []
        for fact in facts:
            evidence_item = EvidenceItem(
                case_id=case_id,
                candidate_id=context.candidate.id,
                document_id=context.segment.document_id if context.segment else None,
                source_page=fact["source_page"],
                quote_text=fact["quote_text"],
                normalized_fact=f"{fact['fact_type']}: {json_safe_string(fact['fact_value'])}",
                confidence=fact["confidence"],
                tags=[fact["fact_type"]],
            )
            db.add(evidence_item)
            db.flush()

            fact_row = CandidateFact(
                candidate_id=context.candidate.id,
                fact_type=fact["fact_type"],
                fact_value=fact["fact_value"],
                evidence_item_id=evidence_item.id,
                confidence=fact["confidence"],
                unsupported=False,
                notes=fact["notes"],
            )
            db.add(fact_row)
            rows.append(fact_row)
        db.flush()
        return rows

    def _generate_candidate_rating_pack(
        self,
        db: Session,
        case: ReviewCase,
        rubric: Rubric,
        context: CandidateContext,
        facts: list[dict[str, Any]],
        agent: ExpertAgent | None,
    ) -> dict[str, Any] | None:
        if agent is None:
            return None

        dimensions = [
            {
                "dimension_id": str(dimension.id),
                "title": dimension.title,
                "description": dimension.description,
                "weight": str(dimension.weight),
            }
            for dimension in rubric.dimensions
        ]
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "overall_strengths": {"type": "array", "items": {"type": "string"}},
                "overall_concerns": {"type": "array", "items": {"type": "string"}},
                "dimension_ratings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimension_id": {"type": "string"},
                            "rating": {"type": "string"},
                            "score": {"type": "number"},
                            "confidence": {"type": "number"},
                            "evidence_summary": {"type": "string"},
                            "strengths": {"type": "array", "items": {"type": "string"}},
                            "concerns": {"type": "array", "items": {"type": "string"}},
                            "unsupported_areas": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": [
                            "dimension_id",
                            "rating",
                            "score",
                            "confidence",
                            "evidence_summary",
                            "strengths",
                            "unsupported_areas",
                        ],
                    },
                },
            },
            "required": ["summary", "overall_strengths", "overall_concerns", "dimension_ratings"],
        }

        prompt = (
            f"Case: {case.title}\n"
            f"Candidate: {context.candidate.full_name}\n"
            f"Matched resume confidence: {context.match.confidence if context.match else '0.00'}\n"
            f"Rubric dimensions: {dimensions}\n"
            f"Extracted facts: {facts}\n"
            f"Resume evidence excerpts: {context.top_quotes}\n"
            "Rate this candidate against each rubric dimension using only the supplied evidence. "
            "Use the rating labels exceeds, meets, partial, does_not_meet, or unsupported. "
            "Keep strengths concise. Only populate concerns if there is a genuine documented gap or risk — "
            "if the evidence fully supports the dimension, return an empty concerns array."
        )

        response = self._invoke_agent(
            db,
            purpose="candidate_evaluation",
            agent=agent,
            prompt=prompt,
            response_schema=schema,
            case_id=case.id,
            candidate_id=context.candidate.id,
        )
        return (
            response.structured_output if response.accepted and isinstance(response.structured_output, dict) else None
        )

    def _persist_candidate_ratings(
        self,
        db: Session,
        rubric: Rubric,
        context: CandidateContext,
        facts: list[dict[str, Any]],
        ai_rating_pack: dict[str, Any] | None,
    ) -> None:
        ai_dimension_map = (
            {
                str(entry.get("dimension_id")): entry
                for entry in (ai_rating_pack.get("dimension_ratings") or [])
                if isinstance(entry, dict) and entry.get("dimension_id")
            }
            if ai_rating_pack
            else {}
        )

        for dimension in rubric.dimensions:
            ai_rating = ai_dimension_map.get(str(dimension.id))
            if ai_rating:
                rating_value = self._normalize_rating(str(ai_rating.get("rating") or "unsupported"))
                numeric_score = Decimal(str(ai_rating.get("score") or RATING_SCALE[rating_value]))
                numeric_score = min(max(numeric_score, Decimal("0.50")), Decimal("5.00"))
                confidence = Decimal(str(ai_rating.get("confidence") or "0.65"))
                evidence_summary = str(ai_rating.get("evidence_summary") or "Generated from resume evidence.")
                strengths = ensure_string_list(ai_rating.get("strengths"))
                concerns = ensure_string_list(ai_rating.get("concerns"))
                unsupported_areas = ensure_string_list(ai_rating.get("unsupported_areas"))
            else:
                heuristic_rating = self._heuristic_dimension_rating(dimension, context.resume_text, facts)
                rating_value = heuristic_rating["rating"]
                numeric_score = heuristic_rating["score"]
                confidence = heuristic_rating["confidence"]
                evidence_summary = heuristic_rating["evidence_summary"]
                strengths = heuristic_rating["strengths"]
                concerns = heuristic_rating["concerns"]
                unsupported_areas = heuristic_rating["unsupported_areas"]

            db.add(
                CandidateRating(
                    candidate_id=context.candidate.id,
                    rubric_dimension_id=dimension.id,
                    rating=rating_value,
                    score=numeric_score.quantize(Decimal("0.01")),
                    evidence_summary=evidence_summary,
                    source_evidence=context.top_quotes[:3],
                    confidence=confidence.quantize(Decimal("0.01")),
                    strengths=strengths,
                    concerns=concerns,
                    unsupported_areas=unsupported_areas,
                    generated_by_model_run_id=None,
                    overridden=False,
                    override_rationale=None,
                )
            )
        db.flush()

    def _persist_interview_questions(self, db: Session, case_id: UUID, context: CandidateContext) -> None:
        prompts = [
            (
                "strength_validation",
                "Describe the strongest result on your resume and explain the scope, stakeholders, and measurable outcome.",
                "Use the interview to validate the strongest documented claim.",
            ),
            (
                "leadership_judgment",
                "Walk through a difficult decision you made involving priorities, people, or mission delivery.",
                "Probe leadership and judgment for the target role.",
            ),
            (
                "evidence_gap",
                "Identify one area from your record that may appear underspecified and explain the actual scope and results.",
                "Clarify unsupported or lightly documented experience before final selection.",
            ),
        ]
        evidence_references = context.top_quotes[:2]
        for category, question_text, rationale in prompts:
            db.add(
                InterviewQuestion(
                    case_id=case_id,
                    candidate_id=context.candidate.id,
                    category=category,
                    question_text=question_text,
                    rationale=rationale,
                    evidence_references=evidence_references,
                )
            )
        db.flush()

    def _load_candidate_ratings(self, db: Session, candidate_id: UUID) -> list[CandidateRating]:
        return db.scalars(select(CandidateRating).where(CandidateRating.candidate_id == candidate_id)).all()

    def _load_candidate_facts(self, db: Session, candidate_id: UUID) -> list[CandidateFact]:
        return db.scalars(select(CandidateFact).where(CandidateFact.candidate_id == candidate_id)).all()

    def _generate_expert_review(
        self,
        db: Session,
        case: ReviewCase,
        position_analysis: PositionAnalysis | None,
        rubric: Rubric,
        context: CandidateContext,
        facts: list[CandidateFact],
        ratings: list[CandidateRating],
        agent: ExpertAgent,
    ) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                            "severity": {"type": "string"},
                        },
                        "required": ["title", "detail", "severity"],
                    },
                },
                "strengths": {"type": "array", "items": {"type": "string"}},
                "concerns": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
            "required": ["summary", "findings", "strengths", "confidence"],
        }

        prompt = (
            f"Case title: {case.title}\n"
            f"Candidate: {context.candidate.full_name}\n"
            f"Agent role: {agent.display_name}\n"
            f"Agent description: {agent.description}\n"
            f"Agent config: {agent.config}\n"
            f"Position analysis: {position_analysis.recommended_dimensions if position_analysis else []}\n"
            f"Rubric dimensions: {[{'title': dimension.title, 'description': dimension.description, 'weight': str(dimension.weight)} for dimension in rubric.dimensions]}\n"
            f"Candidate facts: {[{'type': fact.fact_type, 'value': fact.fact_value, 'notes': fact.notes} for fact in facts]}\n"
            f"Candidate ratings: {[{'rating': rating.rating, 'score': str(rating.score), 'summary': rating.evidence_summary} for rating in ratings]}\n"
            f"Resume evidence excerpts: {context.top_quotes}\n"
            "Produce an evidence-based expert review. Do not invent facts. "
            "Only populate concerns if there is a genuine documented gap or risk relative to the position requirements. "
            "If the candidate's evidence is fully supportive, return an empty concerns array — do not invent concerns to fill the field."
        )

        response = self._invoke_agent(
            db,
            purpose=f"expert_review:{agent.agent_type}",
            agent=agent,
            prompt=prompt,
            response_schema=schema,
            case_id=case.id,
            candidate_id=context.candidate.id,
        )
        if response.accepted and isinstance(response.structured_output, dict):
            return response.structured_output
        return self._heuristic_expert_review(agent, context, facts, ratings)

    def _persist_expert_review(
        self,
        db: Session,
        case_id: UUID,
        candidate_id: UUID,
        agent: ExpertAgent,
        payload: dict[str, Any],
    ) -> None:
        db.add(
            ExpertReview(
                case_id=case_id,
                candidate_id=candidate_id,
                expert_agent_id=agent.id,
                agent_type=agent.agent_type,
                status="completed",
                summary=str(payload.get("summary") or ""),
                findings=payload.get("findings") or [],
                strengths=ensure_string_list(payload.get("strengths")),
                concerns=ensure_string_list(payload.get("concerns")),
                confidence=Decimal(str(payload.get("confidence") or "0.65")).quantize(Decimal("0.01")),
                model_run_id=None,
            )
        )
        db.flush()

    def _persist_consensus_and_challenges(self, db: Session, case_id: UUID, candidate_id: UUID) -> None:
        reviews = db.scalars(
            select(ExpertReview).where(ExpertReview.case_id == case_id, ExpertReview.candidate_id == candidate_id)
        ).all()
        if not reviews:
            return

        strengths = dedupe_strings([entry for review in reviews for entry in review.strengths])
        concerns = dedupe_strings([entry for review in reviews for entry in review.concerns])
        confidence = average_decimal([review.confidence for review in reviews], Decimal("0.65"))
        consensus_summary = (
            f"Consensus favors strengths in {', '.join(strengths[:3]) or 'general fit'}, while concerns remain around "
            f"{', '.join(concerns[:3]) or 'documentation depth'}."
        )
        db.add(
            ConsensusResult(
                case_id=case_id,
                candidate_id=candidate_id,
                consensus_summary=consensus_summary,
                agreement_points=strengths[:5],
                dissent_points=concerns[:5],
                unresolved_issues=concerns[:3],
                confidence=confidence.quantize(Decimal("0.01")),
            )
        )

        skeptic_like_reviews = [
            review for review in reviews if "skeptic" in review.agent_type or "compliance" in review.agent_type
        ]
        for review in skeptic_like_reviews:
            for concern in review.concerns[:2]:
                db.add(
                    ChallengeFinding(
                        case_id=case_id,
                        candidate_id=candidate_id,
                        source_expert_review_id=review.id,
                        challenge_type=review.agent_type,
                        severity="medium",
                        description=concern,
                        resolved=False,
                    )
                )
        db.flush()

    def _persist_consensus_from_state(self, db: Session, case_id: UUID, candidate_id: UUID, state: Any) -> None:
        """Persist ConsensusResult and ChallengeFinding rows from a completed DeliberationState."""
        agreements = state.chair_agreements or []
        open_qs = state.open_questions or []
        conf = (
            Decimal(str(round(state.chair_confidence, 2))).quantize(Decimal("0.01"))
            if state.chair_confidence
            else Decimal("0.65")
        )

        all_concerns = [c for t in state.turns if t.phase in ("opening", "deliberation") for c in t.concerns]
        challenge_concerns = [c for t in state.turns if t.speaker == "skeptic_reviewer" for c in t.concerns]

        summary = (
            f"Board recommendation: {state.chair_recommendation} — Tier {state.chair_tier}. "
            f"Agreements: {', '.join(agreements[:3]) or 'See transcript'}. "
            f"Open questions: {', '.join(open_qs[:3]) or 'None recorded'}."
        )

        existing_consensus = db.scalars(
            select(ConsensusResult).where(
                ConsensusResult.case_id == case_id, ConsensusResult.candidate_id == candidate_id
            )
        ).first()
        if not existing_consensus:
            db.add(
                ConsensusResult(
                    case_id=case_id,
                    candidate_id=candidate_id,
                    consensus_summary=summary,
                    agreement_points=agreements[:5],
                    dissent_points=all_concerns[:5],
                    unresolved_issues=open_qs[:3],
                    confidence=conf,
                )
            )

        for concern in challenge_concerns[:3]:
            db.add(
                ChallengeFinding(
                    case_id=case_id,
                    candidate_id=candidate_id,
                    source_expert_review_id=None,
                    challenge_type="skeptic_reviewer",
                    severity="medium",
                    description=concern,
                    resolved=False,
                )
            )
        db.flush()

    def list_board_meetings(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        return self.council_service.list_board_meetings(db, case_id)

    def get_board_meeting(self, db: Session, case_id: UUID, candidate_id: UUID) -> dict[str, Any] | None:
        return self.council_service.get_board_meeting(db, case_id, candidate_id)

    def delete_board_meeting(self, db: Session, case_id: UUID, candidate_id: UUID) -> bool:
        return self.council_service.delete_board_meeting(db, case_id, candidate_id)

    def delete_all_board_meetings(self, db: Session, case_id: UUID) -> int:
        return self.council_service.delete_all_board_meetings(db, case_id)

    def _persist_pairwise_comparisons(self, db: Session, case_id: UUID) -> None:
        candidates = db.scalars(
            select(Candidate)
            .where(Candidate.case_id == case_id, Candidate.disposition != CandidateDisposition.DISCARDED.value)
            .order_by(Candidate.full_name.asc())
        ).all()
        if len(candidates) < 2:
            return

        score_by_candidate = {
            candidate.id: self._calculate_candidate_score(db, candidate.id) for candidate in candidates
        }
        rating_map = {candidate.id: self._load_candidate_ratings(db, candidate.id) for candidate in candidates}

        for left_candidate, right_candidate in combinations(candidates, 2):
            left_score = score_by_candidate[left_candidate.id]
            right_score = score_by_candidate[right_candidate.id]
            winner = left_candidate if left_score >= right_score else right_candidate
            winning_score = max(left_score, right_score)
            losing_score = min(left_score, right_score)
            dimension_results = self._build_dimension_comparison(
                rating_map[left_candidate.id], rating_map[right_candidate.id]
            )
            db.add(
                PairwiseComparison(
                    case_id=case_id,
                    left_candidate_id=left_candidate.id,
                    right_candidate_id=right_candidate.id,
                    winner_candidate_id=winner.id,
                    rationale=(
                        f"{winner.full_name} currently leads based on weighted rubric fit "
                        f"({winning_score} vs {losing_score}) and available expert review confidence."
                    ),
                    dimension_results=dimension_results,
                    confidence=Decimal("0.72"),
                )
            )
        db.flush()

    def _build_dimension_comparison(
        self,
        left_ratings: list[CandidateRating],
        right_ratings: list[CandidateRating],
    ) -> list[dict[str, Any]]:
        right_by_dimension = {rating.rubric_dimension_id: rating for rating in right_ratings}
        results: list[dict[str, Any]] = []
        for left_rating in left_ratings:
            right_rating = right_by_dimension.get(left_rating.rubric_dimension_id)
            if right_rating is None:
                continue
            if left_rating.score > right_rating.score:
                leader = "left"
            elif right_rating.score > left_rating.score:
                leader = "right"
            else:
                leader = "tie"
            results.append(
                {
                    "dimension_id": str(left_rating.rubric_dimension_id),
                    "left_score": str(left_rating.score),
                    "right_score": str(right_rating.score),
                    "leader": leader,
                }
            )
        return results

    def _calculate_candidate_score(self, db: Session, candidate_id: UUID) -> Decimal:
        # Read all inputs within a single savepoint so they share the same DB snapshot
        with db.begin_nested():
            ratings = self._load_candidate_ratings(db, candidate_id)
            if not ratings:
                return Decimal("0.00")

            dimensions = {dimension.id: dimension for dimension in db.scalars(select(RubricDimension)).all()}
            weighted_total = Decimal("0.00")
            total_weight = Decimal("0.00")
            for rating in ratings:
                dimension = dimensions.get(rating.rubric_dimension_id)
                if dimension is None:
                    continue
                weight = Decimal(str(dimension.weight))
                weighted_total += (Decimal(str(rating.score)) / Decimal("5.00")) * weight
                total_weight += weight

            if total_weight <= 0:
                return Decimal("0.00")

            review_confidences = [
                review.confidence
                for review in db.scalars(select(ExpertReview).where(ExpertReview.candidate_id == candidate_id)).all()
            ]
            challenge_count = len(
                db.scalars(
                    select(ChallengeFinding).where(
                        ChallengeFinding.candidate_id == candidate_id, ChallengeFinding.resolved.is_(False)
                    )
                ).all()
            )
        expert_boost = average_decimal(review_confidences, Decimal("0.00")) * Decimal("5.00")
        challenge_penalty = Decimal(str(challenge_count)) * Decimal("1.25")
        return (weighted_total + expert_boost - challenge_penalty).quantize(Decimal("0.01"))

    def _heuristic_dimension_rating(
        self,
        dimension: RubricDimension,
        resume_text: str,
        facts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        tokens = self._dimension_keywords(dimension)
        overlap = sum(1 for token in tokens if token in resume_text.lower())
        fact_support = sum(
            1 for fact in facts if any(token in json_safe_string(fact["fact_value"]).lower() for token in tokens)
        )
        signal = overlap + fact_support
        if signal >= 5:
            rating = RatingValue.EXCEEDS.value
        elif signal >= 3:
            rating = RatingValue.MEETS.value
        elif signal >= 1:
            rating = RatingValue.PARTIAL.value
        else:
            rating = RatingValue.DOES_NOT_MEET.value if resume_text.strip() else RatingValue.UNSUPPORTED.value
        confidence = min(Decimal("0.55") + (Decimal(str(signal)) * Decimal("0.06")), Decimal("0.90"))
        return {
            "rating": rating,
            "score": RATING_SCALE[rating],
            "confidence": confidence,
            "evidence_summary": f"Keyword and fact support signal: {signal} for {dimension.title}.",
            "strengths": [f"Resume evidence aligns with {dimension.title.lower()}."] if signal >= 3 else [],
            "concerns": [] if signal >= 2 else [f"Limited direct evidence for {dimension.title.lower()}."],
            "unsupported_areas": [dimension.title]
            if rating in {RatingValue.UNSUPPORTED.value, RatingValue.DOES_NOT_MEET.value}
            else [],
        }

    def _heuristic_expert_review(
        self,
        agent: ExpertAgent,
        context: CandidateContext,
        facts: list[CandidateFact],
        ratings: list[CandidateRating],
    ) -> dict[str, Any]:
        focus = str(agent.config.get("focus") or "")
        relevant_keywords = FOCUS_KEYWORDS.get(focus, ())
        fact_notes = [fact.notes for fact in facts if fact.notes]
        relevant_ratings = [
            rating
            for rating in ratings
            if any(keyword in rating.evidence_summary.lower() for keyword in relevant_keywords)
        ] or ratings[:2]
        strengths = dedupe_strings(
            [
                *[strength for rating in relevant_ratings for strength in rating.strengths],
                *[note for note in fact_notes if note][:2],
            ]
        )[:4]
        concerns = dedupe_strings([concern for rating in relevant_ratings for concern in rating.concerns])[:4]
        findings = [
            {
                "title": f"{agent.display_name} finding {index + 1}",
                "detail": detail,
                "severity": "medium" if concerns else "low",
            }
            for index, detail in enumerate((concerns or strengths)[:3])
        ]
        return {
            "summary": (
                f"{agent.display_name} reviewed {context.candidate.full_name}'s record and found "
                f"{'strong alignment' if strengths else 'limited evidence'} for the assigned focus."
            ),
            "findings": findings,
            "strengths": strengths,
            "concerns": concerns,
            "confidence": 0.66,
        }

    def _invoke_agent(
        self,
        db: Session,
        *,
        purpose: str,
        agent: ExpertAgent,
        prompt: str,
        response_schema: dict[str, Any] | None,
        case_id: UUID | None = None,
        candidate_id: UUID | None = None,
    ) -> GatewayInvocationResponse:
        request = GatewayInvocationRequest(
            purpose=purpose,
            prompt=prompt,
            system_prompt=(
                "You are an evidence-focused selection board agent. Use only the supplied record. "
                "If evidence is missing, say so instead of inferring."
            ),
            provider=str(agent.config.get("provider") or "ollama"),
            model=str(agent.config.get("model") or "gpt-oss:120b-cloud"),
            temperature=float(agent.config.get("temperature", 0.2)),
            max_tokens=int(agent.config.get("max_tokens", 4000)),
            response_schema=response_schema,
            metadata={
                "agent_type": agent.agent_type,
                "case_id": str(case_id) if case_id else None,
                "candidate_id": str(candidate_id) if candidate_id else None,
            },
        )

        try:
            response = self.ai_gateway_client.invoke(request)
            self._record_model_run(db, request, response)
            return response
        except Exception as exc:
            fallback = GatewayInvocationResponse(
                accepted=False,
                provider=request.provider or "ollama",
                model=request.model or "gpt-oss:120b-cloud",
                content="",
                structured_output=None,
                usage={},
                validation_errors=[{"message": str(exc)}],
                fallback_used=True,
            )
            self._record_model_run(db, request, fallback, failed_message=str(exc))
            return fallback

    def _record_model_run(
        self,
        db: Session,
        request: GatewayInvocationRequest,
        response: GatewayInvocationResponse,
        failed_message: str | None = None,
    ) -> None:
        db.add(
            ModelRun(
                case_id=UUID(request.metadata["case_id"]) if request.metadata.get("case_id") else None,
                candidate_id=UUID(request.metadata["candidate_id"]) if request.metadata.get("candidate_id") else None,
                prompt_template_id=None,
                provider=response.provider,
                model_name=response.model,
                request_purpose=request.purpose,
                status="completed" if response.accepted else "failed",
                input_tokens=safe_int(response.usage.get("input_tokens")),
                output_tokens=safe_int(response.usage.get("output_tokens")),
                total_cost=Decimal("0.0000"),
                request_payload=request.model_dump(mode="json"),
                response_payload={
                    "accepted": response.accepted,
                    "content": response.content[:4000],
                    "structured_output": response.structured_output,
                    "usage": response.usage,
                    "fallback_used": response.fallback_used,
                    "failed_message": failed_message,
                },
                validation_errors=response.validation_errors,
                started_at=None,
                completed_at=None,
            )
        )
        db.flush()

    def _find_line_with_any(self, text: str, keywords: tuple[str, ...]) -> str | None:
        lowered_keywords = tuple(keyword.lower() for keyword in keywords)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            lowered = line.lower()
            if any(keyword in lowered for keyword in lowered_keywords) and len(line) >= 20:
                return line[:320]
        return None

    def _find_page_for_keywords(self, pages: list[dict[str, Any]], keywords: tuple[str, ...]) -> int | None:
        lowered_keywords = tuple(keyword.lower() for keyword in keywords)
        for page in pages:
            lowered = page["text"].lower()
            if any(keyword in lowered for keyword in lowered_keywords):
                return int(page["page_number"])
        return pages[0]["page_number"] if pages else None

    def _has_keyword_hits(self, lowered_text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in lowered_text for keyword in keywords)

    def _dimension_keywords(self, dimension: RubricDimension) -> set[str]:
        tokens = re.findall(r"[a-z0-9][a-z0-9+/.-]+", f"{dimension.title} {dimension.description}".lower())
        return {token for token in tokens if token not in STOPWORDS and len(token) > 3}

    def _normalize_rating(self, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in RATING_SCALE:
            return normalized
        return RatingValue.UNSUPPORTED.value


def average_decimal(values: list[Decimal], default: Decimal) -> Decimal:
    if not values:
        return default
    return sum(values, Decimal("0.00")) / Decimal(len(values))


def dedupe_strings(values: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(cleaned)
    return results


def ensure_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def json_safe_string(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True)
    except TypeError:
        return str(value)


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, dict):
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
