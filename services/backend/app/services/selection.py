from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import AdjudicationActionType, CandidateDisposition
from app.models.case import Candidate, CandidateMatch, PositionAnalysis, Rubric, RubricDimension
from app.models.evaluation import (
    CandidateRating,
    ChallengeFinding,
    ConsensusResult,
    ExpertReview,
    InterviewResult,
    SelectionRecommendation,
)
from app.models.system import ModelRun
from app.schemas.adjudications import AdjudicationActionCreate
from app.schemas.selection import RankedCandidateRead, SelectionRecommendationRead
from app.services.review_workflow import ReviewWorkflowService, average_decimal, dedupe_strings


@dataclass(slots=True)
class CandidateRecommendationContext:
    candidate: Candidate
    match: CandidateMatch | None
    ratings: list[CandidateRating]
    reviews: list[ExpertReview]
    consensus: ConsensusResult | None
    unresolved_challenges: list[ChallengeFinding]
    interview_result: InterviewResult | None


class SelectionService:
    def __init__(self) -> None:
        self.review_workflow = ReviewWorkflowService()

    def generate_recommendation(self, db: Session, case_id: UUID) -> SelectionRecommendationRead:
        candidates = db.scalars(
            select(Candidate).where(Candidate.case_id == case_id).order_by(Candidate.full_name.asc())
        ).all()
        if not candidates:
            raise HTTPException(status_code=400, detail="No candidates are available for this case.")
        if not db.scalar(select(Rubric.id).where(Rubric.case_id == case_id)):
            raise HTTPException(status_code=400, detail="Create and lock a rubric before generating a recommendation.")

        if not db.scalar(select(CandidateRating).join(Candidate).where(Candidate.case_id == case_id)):
            self.review_workflow.run_case_evaluation(db, case_id)
        if not db.scalar(select(ExpertReview).where(ExpertReview.case_id == case_id)):
            self.review_workflow.run_expert_council(db, case_id)

        recommendation = db.scalar(select(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id))
        if recommendation is None:
            recommendation = SelectionRecommendation(
                case_id=case_id,
                recommendation_type="selection_mode",
                status="draft",
                rationale="",
                non_selection_rationale={},
                evidence_ledger=[],
                confidence=Decimal("0.00"),
                remaining_validation_issues=[],
            )
            db.add(recommendation)

        rankings = self._build_rankings(db, case_id, candidates)
        if not rankings:
            raise HTTPException(status_code=400, detail="No candidates are available for recommendation.")

        discarded = [entry for entry in rankings if entry.disposition == CandidateDisposition.DISCARDED.value]
        active = [entry for entry in rankings if entry.disposition != CandidateDisposition.DISCARDED.value]
        if not active:
            raise HTTPException(status_code=400, detail="Every candidate is currently discarded.")

        explicit_selectee = next(
            (entry for entry in active if entry.disposition == CandidateDisposition.SELECTEE.value),
            None,
        )
        selectee = explicit_selectee or active[0]
        alternates = self._build_alternates(active, selectee.candidate_id)
        interview_slate = self._build_interview_slate(active)

        recommendation.status = recommendation.status or "draft"
        recommendation.selectee_candidate_id = UUID(selectee.candidate_id)
        recommendation.alternate_candidate_ids = [entry.candidate_id for entry in alternates]
        recommendation.interview_slate_candidate_ids = [entry.candidate_id for entry in interview_slate]
        recommendation.discarded_candidate_ids = [entry.candidate_id for entry in discarded]
        recommendation.rationale = self._build_rationale(selectee, alternates)
        recommendation.non_selection_rationale = {
            entry.candidate_id: {
                "candidate_name": entry.candidate_name,
                "reason": self._build_non_selection_reason(entry, selectee, discarded),
            }
            for entry in rankings
            if entry.candidate_id != selectee.candidate_id
        }
        recommendation.evidence_ledger = [
            {
                "candidate_id": entry.candidate_id,
                "candidate_name": entry.candidate_name,
                "overall_score": str(entry.score),
                "evaluation_score": str(entry.evaluation_score),
                "expert_confidence": str(entry.expert_confidence),
                "resume_confidence": str(entry.resume_confidence),
                "interview_score": str(entry.interview_score) if entry.interview_score is not None else None,
                "challenge_count": entry.challenge_count,
                "matched_resume": entry.matched_resume,
                "consensus_summary": entry.consensus_summary,
                "strengths": entry.strengths,
                "concerns": entry.concerns,
                "notes": entry.notes,
            }
            for entry in rankings
        ]
        recommendation.confidence = self._average_confidence(rankings)
        advancing = [selectee] + list(alternates)
        recommendation.remaining_validation_issues = self._build_validation_issues(db, case_id, advancing)

        db.add(
            ModelRun(
                case_id=case_id,
                candidate_id=None,
                prompt_template_id=None,
                provider="deterministic",
                model_name="selection-evidence-engine",
                request_purpose="selection_recommendation",
                status="completed",
                input_tokens=None,
                output_tokens=None,
                total_cost=Decimal("0.0000"),
                request_payload={"candidate_count": len(candidates)},
                response_payload={
                    "selectee_candidate_id": selectee.candidate_id,
                    "alternate_candidate_ids": recommendation.alternate_candidate_ids,
                    "discarded_candidate_ids": recommendation.discarded_candidate_ids,
                },
                validation_errors=[],
                started_at=None,
                completed_at=None,
            )
        )
        db.commit()
        db.refresh(recommendation)
        return self._serialize_recommendation(case_id, recommendation, rankings)

    def get_recommendation(self, db: Session, case_id: UUID) -> SelectionRecommendationRead:
        recommendation = db.scalar(select(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id))
        if recommendation is None:
            raise HTTPException(status_code=404, detail="Selection recommendation not found for this case.")

        candidates = db.scalars(
            select(Candidate).where(Candidate.case_id == case_id).order_by(Candidate.full_name.asc())
        ).all()
        rankings = self._build_rankings(db, case_id, candidates)
        return self._serialize_recommendation(case_id, recommendation, rankings)

    def apply_adjudication_action(self, db: Session, case_id: UUID, payload: AdjudicationActionCreate) -> None:
        recommendation = db.scalar(select(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id))
        candidate = db.get(Candidate, payload.target_candidate_id) if payload.target_candidate_id else None

        if payload.target_candidate_id and (candidate is None or candidate.case_id != case_id):
            raise HTTPException(status_code=404, detail="Target candidate not found for this case.")

        if payload.action_type == AdjudicationActionType.PROMOTE_CANDIDATE and candidate is not None:
            self._clear_disposition(db, case_id, CandidateDisposition.SELECTEE.value)
            candidate.disposition = CandidateDisposition.SELECTEE.value
        elif payload.action_type == AdjudicationActionType.DEMOTE_CANDIDATE and candidate is not None:
            candidate.disposition = CandidateDisposition.UNDER_REVIEW.value
        elif payload.action_type == AdjudicationActionType.DISCARD_CANDIDATE and candidate is not None:
            candidate.disposition = CandidateDisposition.DISCARDED.value
        elif payload.action_type == AdjudicationActionType.RESTORE_CANDIDATE and candidate is not None:
            candidate.disposition = CandidateDisposition.UNDER_REVIEW.value
        elif payload.action_type == AdjudicationActionType.LOCK_SELECTEE:
            if recommendation is None:
                self.generate_recommendation(db, case_id)
                recommendation = db.scalar(
                    select(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id)
                )
            if recommendation is not None:
                recommendation.status = "finalized"
        elif payload.action_type == AdjudicationActionType.LOCK_SLATE:
            if recommendation is None:
                self.generate_recommendation(db, case_id)
                recommendation = db.scalar(
                    select(SelectionRecommendation).where(SelectionRecommendation.case_id == case_id)
                )
            if recommendation is not None:
                recommendation.status = "proposed"

        db.flush()
        try:
            self.generate_recommendation(db, case_id)
        except Exception:
            pass

    def _build_rankings(
        self,
        db: Session,
        case_id: UUID,
        candidates: list[Candidate],
    ) -> list[RankedCandidateRead]:
        match_by_candidate_id = {
            match.candidate_id: match
            for match in db.scalars(select(CandidateMatch).where(CandidateMatch.case_id == case_id)).all()
        }
        ratings_by_candidate = self._rows_by_candidate(
            db.scalars(select(CandidateRating).join(Candidate).where(Candidate.case_id == case_id)).all()
        )
        reviews_by_candidate = self._rows_by_candidate(
            db.scalars(select(ExpertReview).where(ExpertReview.case_id == case_id)).all()
        )
        challenges_by_candidate = self._rows_by_candidate(
            db.scalars(
                select(ChallengeFinding).where(
                    ChallengeFinding.case_id == case_id,
                    ChallengeFinding.resolved.is_(False),
                )
            ).all()
        )
        consensus_by_candidate = {
            row.candidate_id: row
            for row in db.scalars(select(ConsensusResult).where(ConsensusResult.case_id == case_id)).all()
            if row.candidate_id is not None
        }
        interviews_by_candidate = {
            row.candidate_id: row
            for row in db.scalars(select(InterviewResult).where(InterviewResult.case_id == case_id)).all()
        }
        dimensions = {
            dimension.id: dimension
            for dimension in db.scalars(select(RubricDimension).join(Rubric).where(Rubric.case_id == case_id)).all()
        }

        rankings = [
            self._build_ranking_entry(
                CandidateRecommendationContext(
                    candidate=candidate,
                    match=match_by_candidate_id.get(candidate.id),
                    ratings=ratings_by_candidate.get(candidate.id, []),
                    reviews=reviews_by_candidate.get(candidate.id, []),
                    consensus=consensus_by_candidate.get(candidate.id),
                    unresolved_challenges=challenges_by_candidate.get(candidate.id, []),
                    interview_result=interviews_by_candidate.get(candidate.id),
                ),
                dimensions,
            )
            for candidate in candidates
        ]

        return sorted(
            rankings,
            key=lambda entry: (
                entry.disposition == CandidateDisposition.DISCARDED.value,
                -entry.score,
                entry.candidate_name.lower(),
            ),
        )

    def _build_ranking_entry(
        self,
        context: CandidateRecommendationContext,
        dimensions: dict[UUID, RubricDimension],
    ) -> RankedCandidateRead:
        resume_confidence = self._normalize_percentage(context.match.confidence if context.match else Decimal("0.00"))
        expert_confidence = self._average_review_confidence(context.reviews)
        evaluation_score = self._calculate_weighted_evaluation_score(context.ratings, dimensions)
        interview_score = (
            self._normalize_percentage(context.interview_result.overall_score)
            if context.interview_result and context.interview_result.overall_score is not None
            else None
        )
        final_score = evaluation_score.quantize(Decimal("0.01"))

        strengths = dedupe_strings(
            [strength for rating in context.ratings for strength in rating.strengths]
            + [strength for review in context.reviews for strength in review.strengths]
        )[:4]
        concerns = dedupe_strings(
            [concern for rating in context.ratings for concern in rating.concerns]
            + [concern for review in context.reviews for concern in review.concerns]
            + [challenge.description for challenge in context.unresolved_challenges]
        )[:4]
        consensus_summary = context.consensus.consensus_summary if context.consensus else None
        notes = (
            consensus_summary or (context.match.notes if context.match else None) or "Review evidence is still limited."
        )

        confidence = average_decimal(
            [
                self._denormalize_percentage(evaluation_score),
                self._denormalize_percentage(expert_confidence),
                self._denormalize_percentage(resume_confidence),
                self._denormalize_percentage(interview_score) if interview_score is not None else Decimal("0.55"),
            ],
            Decimal("0.55"),
        ).quantize(Decimal("0.01"))

        return RankedCandidateRead(
            candidate_id=str(context.candidate.id),
            candidate_name=context.candidate.full_name,
            disposition=str(context.candidate.disposition),
            score=final_score,
            confidence=confidence,
            evaluation_score=evaluation_score,
            expert_confidence=expert_confidence,
            resume_confidence=resume_confidence,
            interview_score=interview_score,
            challenge_count=len(context.unresolved_challenges),
            matched_resume=context.match.matched_name if context.match else None,
            consensus_summary=consensus_summary,
            strengths=strengths,
            concerns=concerns,
            notes=notes,
        )

    def _calculate_weighted_evaluation_score(
        self,
        ratings: list[CandidateRating],
        dimensions: dict[UUID, RubricDimension],
    ) -> Decimal:
        if not ratings:
            return Decimal("0.00")

        weighted_total = Decimal("0.00")
        total_weight = Decimal("0.00")
        for rating in ratings:
            dimension = dimensions.get(rating.rubric_dimension_id)
            if dimension is None:
                continue
            weight = Decimal(str(dimension.weight))
            weighted_total += Decimal(str(rating.score)) * weight
            total_weight += weight

        if total_weight <= 0:
            return Decimal("0.00")
        return ((weighted_total / total_weight) * Decimal("20.00")).quantize(Decimal("0.01"))

    def _average_review_confidence(self, reviews: list[ExpertReview]) -> Decimal:
        if not reviews:
            return Decimal("0.00")
        return self._normalize_percentage(average_decimal([review.confidence for review in reviews], Decimal("0.00")))

    def _build_alternates(
        self,
        active: list[RankedCandidateRead],
        selectee_candidate_id: str,
    ) -> list[RankedCandidateRead]:
        preferred = [
            entry
            for entry in active
            if entry.candidate_id != selectee_candidate_id and entry.disposition == CandidateDisposition.ALTERNATE.value
        ]
        remaining = [
            entry
            for entry in active
            if entry.candidate_id != selectee_candidate_id
            and entry.candidate_id not in {row.candidate_id for row in preferred}
        ]
        return (preferred + remaining)[:2]

    def _build_interview_slate(self, active: list[RankedCandidateRead]) -> list[RankedCandidateRead]:
        explicit = [
            entry
            for entry in active
            if entry.disposition in {CandidateDisposition.INTERVIEW_SLATE.value, CandidateDisposition.SELECTEE.value}
        ]
        if explicit:
            unique: dict[str, RankedCandidateRead] = {}
            for entry in explicit:
                unique[entry.candidate_id] = entry
            return list(unique.values())[: min(len(unique), 3)]
        return active[: min(len(active), 3)]

    def _build_rationale(self, selectee: RankedCandidateRead, alternates: list[RankedCandidateRead]) -> str:
        alternate_names = ", ".join(alternate.candidate_name for alternate in alternates) or "no alternates identified"
        concern_note = f" Remaining concerns: {', '.join(selectee.concerns[:2])}." if selectee.concerns else ""
        return (
            f"{selectee.candidate_name} leads on weighted rubric performance ({selectee.evaluation_score}), "
            f"supporting expert confidence ({selectee.expert_confidence}), and verified resume alignment "
            f"({selectee.resume_confidence}). Recommended alternates: {alternate_names}.{concern_note}"
        )

    def _build_non_selection_reason(
        self,
        candidate: RankedCandidateRead,
        selectee: RankedCandidateRead,
        discarded: list[RankedCandidateRead],
    ) -> str:
        if candidate.candidate_id == selectee.candidate_id:
            return "Selected as the current top recommendation."
        if any(entry.candidate_id == candidate.candidate_id for entry in discarded):
            return "Currently discarded by adjudication or review status."
        if candidate.challenge_count > selectee.challenge_count:
            return f"Currently trails {selectee.candidate_name} due to more unresolved review concerns."
        if candidate.evaluation_score < selectee.evaluation_score:
            return f"Currently trails {selectee.candidate_name} on weighted rubric evidence."
        return f"Currently ranked below {selectee.candidate_name} on the combined evidence score."

    def _average_confidence(self, rankings: list[RankedCandidateRead]) -> Decimal:
        if not rankings:
            return Decimal("0.00")
        total = sum((entry.confidence for entry in rankings), Decimal("0.00"))
        return (total / Decimal(len(rankings))).quantize(Decimal("0.01"))

    def _build_validation_issues(
        self,
        db: Session,
        case_id: UUID,
        rankings: list[RankedCandidateRead],
    ) -> list[str]:
        issues: list[str] = []
        if not db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == case_id)):
            issues.append("Position analysis has not been completed.")
        if not db.scalar(select(Rubric).where(Rubric.case_id == case_id)):
            issues.append("Approved rubric has not been created yet.")
        if any(entry.evaluation_score <= Decimal("0.00") for entry in rankings):
            issues.append("At least one candidate has not been evaluated against the rubric.")
        if any(entry.matched_resume is None for entry in rankings):
            missing = [entry.candidate_name for entry in rankings if entry.matched_resume is None]
            issues.append(f"No matched resume evidence for: {', '.join(missing)}.")
        if any(entry.expert_confidence <= Decimal("0.00") for entry in rankings):
            issues.append("Expert council reviews have not been completed for every candidate.")
        if any(entry.challenge_count > 0 for entry in rankings):
            flagged = [entry.candidate_name for entry in rankings if entry.challenge_count > 0]
            issues.append(f"Unresolved challenge findings remain for: {', '.join(flagged)}.")
        return issues

    def _serialize_recommendation(
        self,
        case_id: UUID,
        recommendation: SelectionRecommendation,
        rankings: list[RankedCandidateRead],
    ) -> SelectionRecommendationRead:
        rankings_by_id = {entry.candidate_id: entry for entry in rankings}
        selectee_id = str(recommendation.selectee_candidate_id) if recommendation.selectee_candidate_id else None
        return SelectionRecommendationRead(
            id=recommendation.id,
            created_at=recommendation.created_at,
            updated_at=recommendation.updated_at,
            case_id=str(case_id),
            recommendation_type=recommendation.recommendation_type,
            status=recommendation.status,
            selectee_candidate_id=selectee_id,
            selectee_candidate_name=rankings_by_id.get(selectee_id).candidate_name
            if selectee_id and selectee_id in rankings_by_id
            else None,
            alternate_candidate_ids=recommendation.alternate_candidate_ids or [],
            alternate_candidate_names=[
                rankings_by_id[candidate_id].candidate_name
                for candidate_id in (recommendation.alternate_candidate_ids or [])
                if candidate_id in rankings_by_id
            ],
            interview_slate_candidate_ids=recommendation.interview_slate_candidate_ids or [],
            interview_slate_candidate_names=[
                rankings_by_id[candidate_id].candidate_name
                for candidate_id in (recommendation.interview_slate_candidate_ids or [])
                if candidate_id in rankings_by_id
            ],
            discarded_candidate_ids=recommendation.discarded_candidate_ids or [],
            discarded_candidate_names=[
                rankings_by_id[candidate_id].candidate_name
                for candidate_id in (recommendation.discarded_candidate_ids or [])
                if candidate_id in rankings_by_id
            ],
            rationale=recommendation.rationale,
            non_selection_rationale=recommendation.non_selection_rationale,
            evidence_ledger=recommendation.evidence_ledger,
            confidence=recommendation.confidence,
            remaining_validation_issues=recommendation.remaining_validation_issues,
            rankings=rankings,
        )

    def _clear_disposition(self, db: Session, case_id: UUID, disposition: str) -> None:
        rows = db.scalars(
            select(Candidate).where(Candidate.case_id == case_id, Candidate.disposition == disposition)
        ).all()
        for row in rows:
            row.disposition = CandidateDisposition.UNDER_REVIEW.value

    def _rows_by_candidate(self, rows: list) -> dict[UUID, list]:
        results: dict[UUID, list] = {}
        for row in rows:
            candidate_id = getattr(row, "candidate_id", None)
            if candidate_id is None:
                continue
            results.setdefault(candidate_id, []).append(row)
        return results

    def _normalize_percentage(self, value: Decimal | None) -> Decimal:
        if value is None:
            return Decimal("0.00")
        normalized = Decimal(str(value))
        if normalized <= Decimal("1.00"):
            normalized *= Decimal("100.00")
        return normalized.quantize(Decimal("0.01"))

    def _denormalize_percentage(self, value: Decimal | None) -> Decimal:
        if value is None:
            return Decimal("0.00")
        normalized = Decimal(str(value))
        if normalized > Decimal("1.00"):
            normalized /= Decimal("100.00")
        return normalized.quantize(Decimal("0.01"))

    def _disposition_adjustment(self, disposition: str) -> Decimal:
        if disposition == CandidateDisposition.SELECTEE.value:
            return Decimal("3.00")
        if disposition == CandidateDisposition.ALTERNATE.value:
            return Decimal("1.50")
        if disposition == CandidateDisposition.INTERVIEW_SLATE.value:
            return Decimal("1.00")
        if disposition == CandidateDisposition.DISCARDED.value:
            return Decimal("-25.00")
        return Decimal("0.00")
