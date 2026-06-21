from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

import redis as redis_lib
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import AuditEventType, CandidateDisposition
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
    ExpertReview,
    InterviewQuestion,
    PairwiseComparison,
)
from app.models.operations import AuditEvent
from app.schemas.workflow_plan import (
    CandidateDossierViewRead,
    CandidateMatrixRowRead,
    CandidateStageDecisionRequest,
    CandidateStageHistoryRead,
    DecisionWorkspaceViewRead,
    EngagementWorkflowPlanRead,
    PrepWorkspaceIssueRead,
    PrepWorkspaceStepRead,
    PrepWorkspaceViewRead,
    ReviewStageNavItemRead,
    ReviewWorkspaceEmptyStateRead,
    ReviewWorkspaceViewRead,
    StageArtifactCreate,
    StageArtifactRead,
    WorkflowAuditEventRead,
    WorkflowCandidateDossierRead,
    WorkflowDimensionScoreRead,
    WorkflowStageCandidateRead,
    WorkflowStageCreate,
    WorkflowStageRead,
    WorkflowStageRunResult,
    WorkflowStageTemplateRead,
    WorkflowStageUpdate,
    WorkflowWorkspaceSummaryRead,
    WorkspacePrimaryActionRead,
)
from app.services.ai_inference import AIGatewayService, GatewayInvocationRequest
from app.services.audit import AuditRecorder
from app.services.position_analysis import PositionAnalysisService
from app.services.review_workflow import ReviewWorkflowService, dedupe_strings
from app.services.selection import SelectionService

WORKFLOW_PLAN_KEY = "workflow_plan_v2"
WORKFLOW_ARTIFACTS_KEY = "workflow_stage_artifacts_v2"

STAGE_TEMPLATE_LIBRARY: list[dict[str, Any]] = [
    {
        "key": "resume_review",
        "name": "Resume Review",
        "description": "Score the resume package against the PD, propose tiers, surface differentiators, and assemble advisory evidence.",
        "default_workspace": "review",
        "default_config": {
            "tier_labels": ["Tier A", "Tier B", "Tier C"],
            "osint_enabled": True,
            "advisory_only": True,
        },
    },
    {
        "key": "narrative_request",
        "name": "Narrative Request",
        "description": "Request written follow-up from shortlisted candidates, summarize responses, and generate follow-up questions.",
        "default_workspace": "prep",
        "default_config": {
            "eligible_tiers": ["Tier A", "Tier B"],
            "artifact_types": ["prompt_request", "candidate_response"],
        },
    },
    {
        "key": "screening_interview",
        "name": "Screening Interview",
        "description": "Capture screening interview evidence, score the responses, and decide who advances.",
        "default_workspace": "review",
        "default_config": {
            "eligible_tiers": ["Tier A", "Tier B"],
            "artifact_types": ["interview_notes", "candidate_response"],
        },
    },
    {
        "key": "panel_interview",
        "name": "Panel Interview",
        "description": "Consolidate panel interview evidence and update candidate decisions with full override support.",
        "default_workspace": "review",
        "default_config": {
            "eligible_tiers": ["Tier A", "Tier B"],
            "artifact_types": ["panel_notes", "candidate_response"],
        },
    },
    {
        "key": "final_selection",
        "name": "Final Selection",
        "description": "Lock the final ranking, recommendation rationale, alternates, and disposition decisions.",
        "default_workspace": "review",
        "default_config": {
            "eligible_tiers": ["Tier A", "Tier B"],
            "artifact_types": ["selection_note"],
        },
    },
]


class WorkflowPlanService:
    def __init__(self) -> None:
        self.audit = AuditRecorder()
        self.ai_gateway = AIGatewayService()
        self.position_analysis_service = PositionAnalysisService()
        self.review_workflow = ReviewWorkflowService()
        self.selection_service = SelectionService()
        _s = get_settings()
        self._redis = redis_lib.Redis(
            host=_s.redis_host,
            port=_s.redis_port,
            password=_s.redis_password or None,
            db=3,
            decode_responses=True,
        )

    def get_plan(self, db: Session, case_id: UUID) -> EngagementWorkflowPlanRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        stages = self._serialize_stage_records(db, review_case, plan)
        current_stage_id = self._resolve_current_stage_id(stages)
        return EngagementWorkflowPlanRead(
            case_id=str(review_case.id),
            case_title=review_case.title,
            current_stage_id=current_stage_id,
            next_action=self._build_next_action(stages),
            updated_at=str(plan["updated_at"]),
            templates=[WorkflowStageTemplateRead(**entry) for entry in STAGE_TEMPLATE_LIBRARY],
            stages=stages,
        )

    def update_plan(
        self, db: Session, case_id: UUID, stages_payload: list[WorkflowStageUpdate]
    ) -> EngagementWorkflowPlanRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        updated_stages: list[dict[str, Any]] = []
        for current_stage, payload in zip(plan["stages"], stages_payload, strict=False):
            merged = dict(current_stage)
            for field_name, value in payload.model_dump(exclude_none=True).items():
                merged[field_name] = value
            updated_stages.append(merged)
        if updated_stages:
            plan["stages"] = updated_stages
        self._persist_plan(review_case, plan)
        db.commit()
        return self.get_plan(db, case_id)

    def replace_plan(
        self, db: Session, case_id: UUID, stages_payload: list[WorkflowStageCreate]
    ) -> EngagementWorkflowPlanRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        plan["stages"] = [self._new_stage_dict(payload.model_dump()) for payload in stages_payload]
        self._persist_plan(review_case, plan)
        db.commit()
        return self.get_plan(db, case_id)

    def add_stage(self, db: Session, case_id: UUID, payload: WorkflowStageCreate) -> EngagementWorkflowPlanRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        plan["stages"].append(self._new_stage_dict(payload.model_dump()))
        plan["stages"] = self._sorted_stage_dicts(plan["stages"])
        self._persist_plan(review_case, plan)
        db.commit()
        return self.get_plan(db, case_id)

    def update_stage(
        self, db: Session, case_id: UUID, stage_id: str, payload: WorkflowStageUpdate
    ) -> WorkflowStageRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        stage = self._get_stage_dict(plan, stage_id)
        for field_name, value in payload.model_dump(exclude_none=True).items():
            stage[field_name] = value
        plan["stages"] = self._sorted_stage_dicts(plan["stages"])
        self._persist_plan(review_case, plan)
        db.commit()
        if payload.config and payload.config.get("official_accepted"):
            self._bulk_accept_stage(db, review_case, plan, stage_id)
            db.commit()
        return self._get_stage_record(db, review_case, plan, stage_id)

    def _is_advancing_row(self, row: WorkflowStageCandidateRead) -> bool:
        _NEGATIVE = {"do_not_advance", "eliminate"}
        _POSITIVE = {"advance", "hold", "selected", "alternate_ready", "selectee_ready"}
        if (row.final_disposition or "") in _NEGATIVE:
            return False
        adv = row.advancement_decision or ""
        if adv in _NEGATIVE or "Candidate is currently discarded" in (row.flags or []):
            return False
        if adv in _POSITIVE:
            return True
        letter = (row.final_tier or row.proposed_tier or "").upper().replace("TIER ", "").strip()
        return letter in {"A", "B"}

    def _bulk_accept_stage(self, db: Session, review_case: Any, plan: dict[str, Any], stage_id: str) -> None:
        stage = self._get_stage_dict(plan, stage_id)
        rows = self._build_stage_candidate_rows(db, review_case, plan, stage)
        for row in rows:
            candidate = self._get_candidate(db, review_case.id, UUID(row.candidate_id))
            decisions = self._candidate_stage_decisions(candidate)
            current = deepcopy(decisions.get(stage_id, {}))
            if current.get("advancement_decision"):
                continue
            current["stage_id"] = stage_id
            current["stage_name"] = stage["name"]
            current["stage_type"] = stage["template_key"]
            current["updated_at"] = self._now_iso()
            current["updated_by"] = "Stage acceptance"
            current["advancement_decision"] = "advance" if self._is_advancing_row(row) else "do_not_advance"
            decisions[stage_id] = current
            self._set_candidate_stage_decisions(candidate, decisions)

    def clear_stage_overrides(self, db: Session, case_id: UUID, stage_id: str) -> WorkflowStageRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        candidates = db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        for candidate in candidates:
            decisions = self._candidate_stage_decisions(candidate)
            decision = deepcopy(decisions.get(stage_id, {}))
            decision.pop("final_tier", None)
            decision.pop("final_disposition", None)
            decision.pop("manual_rationale", None)
            decisions[stage_id] = decision
            self._set_candidate_stage_decisions(candidate, decisions)
            for r in db.scalars(select(CandidateRating).where(CandidateRating.candidate_id == candidate.id)).all():
                if r.overridden:
                    r.overridden = False
                    r.override_rationale = None
        db.commit()
        return self._get_stage_record(db, review_case, plan, stage_id)

    def run_stage(self, db: Session, case_id: UUID, stage_id: str, *, force: bool = False) -> WorkflowStageRunResult:
        lock_key = f"stage_run_lock:{case_id}:{stage_id}"
        lock = self._redis.lock(lock_key, timeout=300, blocking_timeout=5)
        if not lock.acquire(blocking=True):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Stage run already in progress for this engagement."
            )
        try:
            return self._run_stage_locked(db, case_id, stage_id, force=force)
        finally:
            try:
                lock.release()
            except Exception:
                pass

    def _run_stage_locked(
        self, db: Session, case_id: UUID, stage_id: str, *, force: bool = False
    ) -> WorkflowStageRunResult:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        stage = self._get_stage_dict(plan, stage_id)

        if not stage.get("enabled", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="This stage is disabled for the engagement."
            )

        template_key = str(stage["template_key"])
        if template_key == "resume_review":
            candidate_rows = self._run_resume_review_stage(db, review_case, force=force)
            artifact_count = 0
            run_summary = (
                f"Resume review completed for {len(candidate_rows)} candidates."
                if force or stage.get("last_run_status") != "completed"
                else "Existing resume review is available. Use a forced rerun only when the source materials changed."
            )
        elif template_key == "narrative_request":
            candidate_rows, artifact_count = self._run_narrative_stage(db, review_case, stage, force=force)
            run_summary = (
                f"Narrative review updated {artifact_count} AI artifacts for {len(candidate_rows)} candidates."
                if artifact_count
                else "Narrative stage is ready, but no candidate responses were available to summarize."
            )
        elif template_key in {"screening_interview", "panel_interview"}:
            candidate_rows, artifact_count = self._run_interview_stage(db, review_case, stage)
            run_summary = (
                f"{stage['name']} refreshed {artifact_count} interview summaries."
                if artifact_count
                else f"{stage['name']} is ready. Add interview evidence to generate scored summaries."
            )
        elif template_key == "final_selection":
            candidate_rows = self.list_stage_candidates(db, case_id, stage_id)
            if force:
                recommendation = self.selection_service.generate_recommendation(db, case_id)
            else:
                try:
                    recommendation = self.selection_service.get_recommendation(db, case_id)
                except Exception:
                    recommendation = self.selection_service.generate_recommendation(db, case_id)
            artifact_count = 0
            run_summary = (
                f"Recommendation generated. Current selectee: {recommendation.selectee_candidate_name or 'not set'}."
            )
        else:
            candidate_rows = self.list_stage_candidates(db, case_id, stage_id)
            artifact_count = 0
            run_summary = f"{stage['name']} is available."

        stage["last_run_status"] = "completed"
        stage["status"] = "completed"
        stage["last_run_at"] = self._now_iso()
        stage["last_run_summary"] = run_summary
        self._persist_plan(review_case, plan)
        db.commit()
        return WorkflowStageRunResult(
            case_id=str(case_id),
            stage_id=stage_id,
            status="completed",
            run_summary=run_summary,
            candidate_count=len(candidate_rows),
            artifact_count=artifact_count,
        )

    def list_stage_candidates(self, db: Session, case_id: UUID, stage_id: str) -> list[WorkflowStageCandidateRead]:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        stage = self._get_stage_dict(plan, stage_id)
        return self._build_stage_candidate_rows(db, review_case, plan, stage)

    def record_candidate_decision(
        self,
        db: Session,
        case_id: UUID,
        stage_id: str,
        candidate_id: UUID,
        payload: CandidateStageDecisionRequest,
        *,
        actor_id: str,
        actor_name: str,
    ) -> WorkflowCandidateDossierRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        stage = self._get_stage_dict(plan, stage_id)
        candidate = self._get_candidate(db, case_id, candidate_id)

        stage_decisions = self._candidate_stage_decisions(candidate)
        prior_decision = deepcopy(stage_decisions.get(stage_id, {}))
        decision = deepcopy(prior_decision)
        decision["stage_id"] = stage_id
        decision["stage_name"] = stage["name"]
        decision["stage_type"] = stage["template_key"]
        decision["updated_at"] = self._now_iso()
        decision["updated_by"] = actor_name
        if payload.clear_all_overrides:
            decision.pop("final_tier", None)
            decision.pop("final_disposition", None)
            decision.pop("manual_rationale", None)
            for r in db.scalars(select(CandidateRating).where(CandidateRating.candidate_id == candidate_id)).all():
                if r.overridden:
                    r.overridden = False
                    r.override_rationale = None
            stage_decisions[stage_id] = decision
            self._set_candidate_stage_decisions(candidate, stage_decisions)
            db.commit()
            return self.get_candidate_dossier(db, case_id, stage_id, candidate_id)
        if payload.stage_score is not None:
            decision["stage_score"] = payload.stage_score
        if payload.clear_final_tier:
            decision.pop("final_tier", None)
        elif payload.final_tier is not None:
            decision["final_tier"] = payload.final_tier
        if payload.clear_final_disposition:
            decision.pop("final_disposition", None)
        elif payload.final_disposition is not None:
            decision["final_disposition"] = payload.final_disposition
        if payload.clear_advancement_decision:
            decision.pop("advancement_decision", None)
        elif payload.advancement_decision is not None:
            decision["advancement_decision"] = payload.advancement_decision
        if payload.rationale is not None:
            decision["manual_rationale"] = payload.rationale
        if payload.notes is not None:
            decision["notes"] = payload.notes

        for override in payload.dimension_overrides:
            rating = db.scalar(
                select(CandidateRating).where(
                    CandidateRating.candidate_id == candidate_id,
                    CandidateRating.rubric_dimension_id == UUID(override.dimension_id),
                )
            )
            if rating is None:
                continue
            before = {"rating": rating.rating, "score": str(rating.score)}
            if override.rating is not None:
                rating.rating = override.rating
            if override.score is not None:
                raw = self._to_decimal(override.score, fallback=rating.score)
                rating.score = min(max(raw, Decimal("0.50")), Decimal("5.00"))
            rating.overridden = True
            rating.override_rationale = override.rationale or payload.rationale
            self.audit.record(
                db,
                actor_id=actor_id,
                event_type=AuditEventType.RATING_OVERRIDE,
                entity_type="candidate_rating",
                entity_id=str(rating.id),
                details={
                    "candidate_id": str(candidate.id),
                    "stage_id": stage_id,
                    "dimension_id": str(rating.rubric_dimension_id),
                    "prior_value": before,
                    "new_value": {"rating": rating.rating, "score": str(rating.score)},
                    "rationale": rating.override_rationale,
                },
                case_id=case_id,
            )

        for override in payload.rubric_weight_overrides:
            dimension = db.get(RubricDimension, UUID(override.dimension_id))
            if dimension is None:
                continue
            prior_weight = str(dimension.weight)
            dimension.weight = self._to_decimal(override.weight, fallback=dimension.weight)
            self.audit.record(
                db,
                actor_id=actor_id,
                event_type=AuditEventType.RUBRIC_CHANGE,
                entity_type="rubric_dimension",
                entity_id=str(dimension.id),
                details={
                    "candidate_id": str(candidate.id),
                    "stage_id": stage_id,
                    "prior_weight": prior_weight,
                    "new_weight": str(dimension.weight),
                    "rationale": override.rationale or payload.rationale,
                },
                case_id=case_id,
            )

        if payload.final_tier is not None and payload.final_tier != prior_decision.get("final_tier"):
            self.audit.record(
                db,
                actor_id=actor_id,
                event_type=AuditEventType.TIER_MOVEMENT,
                entity_type="candidate",
                entity_id=str(candidate.id),
                details={
                    "stage_id": stage_id,
                    "prior_value": prior_decision.get("final_tier"),
                    "new_value": payload.final_tier,
                    "rationale": payload.rationale,
                },
                case_id=case_id,
            )

        if payload.final_disposition is not None:
            candidate.disposition = self._map_candidate_disposition(payload.final_disposition, candidate.disposition)
            self.audit.record(
                db,
                actor_id=actor_id,
                event_type=AuditEventType.ADJUDICATION_ACTION,
                entity_type="candidate",
                entity_id=str(candidate.id),
                details={
                    "stage_id": stage_id,
                    "prior_value": prior_decision.get("final_disposition"),
                    "new_value": payload.final_disposition,
                    "advancement_decision": payload.advancement_decision,
                    "rationale": payload.rationale,
                },
                case_id=case_id,
            )

        stage_decisions[stage_id] = decision
        self._set_candidate_stage_decisions(candidate, stage_decisions)
        db.commit()
        try:
            self.selection_service.generate_recommendation(db, case_id)
        except Exception:
            pass
        return self.get_candidate_dossier(db, case_id, stage_id, candidate_id)

    def add_stage_artifact(
        self,
        db: Session,
        case_id: UUID,
        stage_id: str,
        payload: StageArtifactCreate,
        *,
        actor_id: str,
    ) -> StageArtifactRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        self._get_stage_dict(plan, stage_id)
        artifact = {
            "id": str(uuid4()),
            "stage_id": stage_id,
            "artifact_type": payload.artifact_type,
            "title": payload.title,
            "content": payload.content,
            "candidate_id": payload.candidate_id,
            "metadata": payload.metadata,
            "created_at": self._now_iso(),
            "created_by": actor_id,
        }
        artifacts = self._load_artifacts(review_case)
        artifacts.setdefault(stage_id, []).append(artifact)
        self._persist_artifacts(review_case, artifacts)
        db.commit()
        return StageArtifactRead(**artifact)

    def get_candidate_dossier(
        self, db: Session, case_id: UUID, stage_id: str, candidate_id: UUID
    ) -> WorkflowCandidateDossierRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        self._get_stage_dict(plan, stage_id)
        candidate = self._get_candidate(db, case_id, candidate_id)
        stage_rows = self.list_stage_candidates(db, case_id, stage_id)
        stage_record = next((entry for entry in stage_rows if entry.candidate_id == str(candidate_id)), None)
        if stage_record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Candidate is not eligible for the requested stage."
            )

        ratings = self._load_dimension_scores(db, candidate.id)
        facts = [
            {
                "id": str(row.id),
                "fact_type": row.fact_type,
                "fact_value": row.fact_value,
                "confidence": str(row.confidence),
                "unsupported": row.unsupported,
                "notes": row.notes,
            }
            for row in db.scalars(
                select(CandidateFact)
                .where(CandidateFact.candidate_id == candidate.id)
                .order_by(CandidateFact.created_at.asc())
            ).all()
        ]
        expert_reviews = [
            {
                "id": str(row.id),
                "agent_type": row.agent_type,
                "summary": row.summary,
                "findings": row.findings,
                "strengths": row.strengths,
                "concerns": row.concerns,
                "confidence": str(row.confidence),
            }
            for row in db.scalars(
                select(ExpertReview)
                .where(ExpertReview.candidate_id == candidate.id)
                .order_by(ExpertReview.created_at.asc())
            ).all()
        ]
        interview_questions = [
            {
                "id": str(row.id),
                "category": row.category,
                "question_text": row.question_text,
                "rationale": row.rationale,
                "evidence_references": row.evidence_references,
            }
            for row in db.scalars(
                select(InterviewQuestion)
                .where(InterviewQuestion.candidate_id == candidate.id)
                .order_by(InterviewQuestion.created_at.asc())
            ).all()
        ]
        pairwise = [
            {
                "id": str(row.id),
                "left_candidate_id": str(row.left_candidate_id),
                "right_candidate_id": str(row.right_candidate_id),
                "winner_candidate_id": str(row.winner_candidate_id) if row.winner_candidate_id else None,
                "rationale": row.rationale,
                "dimension_results": row.dimension_results,
                "confidence": str(row.confidence),
            }
            for row in db.scalars(
                select(PairwiseComparison).where(
                    PairwiseComparison.case_id == case_id,
                    (PairwiseComparison.left_candidate_id == candidate.id)
                    | (PairwiseComparison.right_candidate_id == candidate.id),
                )
            ).all()
        ]
        raw_artifacts = list(self._artifacts_for_candidate(review_case, stage_id, str(candidate_id)))
        # For interview stages, also include the candidate's narrative_analysis artifact from the
        # narrative_request stage — the frontend uses it to surface per-candidate screening questions
        current_stage = next((s for s in plan.get("stages", []) if str(s.get("id")) == stage_id), {})
        if current_stage.get("template_key") in {"screening_interview", "panel_interview"}:
            all_artifacts = self._load_artifacts(review_case)
            narrative_stage_id = next(
                (str(s["id"]) for s in plan.get("stages", []) if s.get("template_key") == "narrative_request"),
                "narrative_request",
            )
            for a in all_artifacts.get(narrative_stage_id, []):
                if a.get("candidate_id") == str(candidate_id) and a.get("artifact_type") == "narrative_analysis":
                    raw_artifacts = raw_artifacts + [a]
                    break
        artifacts = [StageArtifactRead(**artifact) for artifact in raw_artifacts]
        audit_events = [
            WorkflowAuditEventRead(
                id=str(event.id),
                actor_id=event.actor_id,
                event_type=event.event_type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                details=event.details or {},
                occurred_at=event.occurred_at.isoformat(),
            )
            for event in db.scalars(
                select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.occurred_at.desc())
            ).all()
            if event.entity_id == str(candidate.id)
            or str((event.details or {}).get("candidate_id")) == str(candidate.id)
        ][:20]
        stage_history = self._build_stage_history(db, review_case, plan, candidate)
        recommendation_summary = self._recommendation_summary(db, case_id, str(candidate.id))
        match = db.scalar(
            select(CandidateMatch).where(CandidateMatch.case_id == case_id, CandidateMatch.candidate_id == candidate.id)
        )

        # Pull parsed_profile from the candidate's matched resume segment
        resume_profile: dict[str, Any] | None = None
        if match and match.resume_segment_id:
            segment = db.scalar(select(ResumeSegment).where(ResumeSegment.id == match.resume_segment_id))
            if segment and segment.parsed_profile:
                resume_profile = segment.parsed_profile

        return WorkflowCandidateDossierRead(
            candidate_id=str(candidate.id),
            candidate_name=candidate.full_name,
            candidate_email=candidate.email,
            disposition=str(candidate.disposition),
            matched_resume=match.matched_name if match else None,
            resume_confidence=str(match.confidence) if match else "0.00",
            evaluation_summary=str((candidate.profile or {}).get("evaluation_summary") or ""),
            resume_profile=resume_profile,
            stage_record=stage_record,
            stage_history=stage_history,
            ratings=ratings,
            facts=facts,
            expert_reviews=expert_reviews,
            interview_questions=interview_questions,
            pairwise_comparisons=pairwise,
            stage_artifacts=artifacts,
            audit_events=audit_events,
            recommendation_summary=recommendation_summary,
        )

    def get_workspace_summary(self, db: Session, case_id: UUID) -> WorkflowWorkspaceSummaryRead:
        review_case = self._get_case(db, case_id)
        plan = self.get_plan(db, case_id)
        documents = db.scalars(select(Document).where(Document.case_id == case_id)).all()
        matches = db.scalars(select(CandidateMatch).where(CandidateMatch.case_id == case_id)).all()
        segments = db.scalars(select(ResumeSegment).join(Document).where(Document.case_id == case_id)).all()
        recommendation_summary = self._recommendation_summary(db, case_id, None)

        document_summary = {
            "total_documents": len(documents),
            "position_descriptions": sum(1 for row in documents if row.document_type == "position_description"),
            "resume_files": sum(1 for row in documents if row.document_type in {"resume", "resume_bundle"}),
            "ready_documents": sum(1 for row in documents if row.status == "ready"),
            "processing_documents": sum(1 for row in documents if row.status == "processing"),
            "flagged_documents": sum(1 for row in documents if row.status == "failed"),
        }
        matching_summary = {
            "candidate_count": len(db.scalars(select(Candidate.id).where(Candidate.case_id == case_id)).all()),
            "matched_count": sum(1 for row in matches if row.resume_segment_id is not None),
            "duplicate_count": sum(1 for row in matches if row.is_duplicate),
            "unmatched_segment_count": sum(1 for row in segments if row.candidate_id is None),
        }
        rubric = db.scalar(select(Rubric).where(Rubric.case_id == case_id).order_by(Rubric.updated_at.desc()))
        rubric_summary = {
            "has_analysis": db.scalar(select(PositionAnalysis.id).where(PositionAnalysis.case_id == case_id))
            is not None,
            "rubric_name": rubric.name if rubric else None,
            "rubric_locked": rubric.is_locked if rubric else False,
            "dimension_count": len(rubric.dimensions) if rubric else 0,
        }
        active_stage = next((stage for stage in plan.stages if stage.id == plan.current_stage_id), None)
        flagged_issues = self._build_flagged_issues(document_summary, matching_summary, recommendation_summary)
        prep_progress = [
            {"label": "Upload PD", "complete": document_summary["position_descriptions"] > 0},
            {"label": "Upload resumes", "complete": document_summary["resume_files"] > 0},
            {"label": "Review parsing", "complete": document_summary["ready_documents"] > 0},
            {
                "label": "Resolve matching",
                "complete": matching_summary["duplicate_count"] == 0
                and matching_summary["unmatched_segment_count"] == 0,
            },
            {
                "label": "Launch advisory run",
                "complete": any(stage.last_run_status == "completed" for stage in plan.stages),
            },
        ]
        stage_counts = {stage.name: stage.candidate_count for stage in plan.stages}

        return WorkflowWorkspaceSummaryRead(
            case_id=str(review_case.id),
            case_title=review_case.title,
            organization=review_case.organization,
            hiring_action_type=review_case.hiring_action_type,
            selecting_official=review_case.selecting_official,
            active_stage_id=active_stage.id if active_stage else None,
            active_stage_name=active_stage.name if active_stage else None,
            active_stage_status=active_stage.status if active_stage else None,
            next_action=plan.next_action,
            document_summary=document_summary,
            matching_summary=matching_summary,
            rubric_summary=rubric_summary,
            recommendation_summary=recommendation_summary,
            flagged_issues=flagged_issues,
            prep_progress=prep_progress,
            stage_counts=stage_counts,
        )

    def get_prep_workspace(self, db: Session, case_id: UUID) -> PrepWorkspaceViewRead:
        review_case = self._get_case(db, case_id)
        plan = self.get_plan(db, case_id)
        summary = self.get_workspace_summary(db, case_id)
        issues = [self._issue_from_text(issue) for issue in summary.flagged_issues]

        steps = [
            PrepWorkspaceStepRead(
                key="position_description",
                title="Position description",
                status="complete" if summary.document_summary.get("position_descriptions", 0) > 0 else "pending",
                detail="Load the position description that defines the hiring event.",
                metric=f"{summary.document_summary.get('position_descriptions', 0)} files",
                next_action="Upload the PD if it is not already on file.",
            ),
            PrepWorkspaceStepRead(
                key="resume_package",
                title="Resume package",
                status="complete" if summary.document_summary.get("resume_files", 0) > 0 else "pending",
                detail="Add the resume bundle that will feed the candidate pool.",
                metric=f"{summary.document_summary.get('resume_files', 0)} files",
                next_action="Upload resumes or the consolidated resume package.",
            ),
            PrepWorkspaceStepRead(
                key="parsing_validation",
                title="Parsing validation",
                status="attention"
                if summary.document_summary.get("flagged_documents", 0) > 0
                else "complete"
                if summary.document_summary.get("ready_documents", 0) > 0
                else "pending",
                detail="Confirm the uploaded materials parsed cleanly before review begins.",
                metric=f"{summary.document_summary.get('ready_documents', 0)} ready",
                next_action="Resolve failed or incomplete parsing before moving forward.",
            ),
            PrepWorkspaceStepRead(
                key="candidate_matching",
                title="Candidate pool integrity",
                status="attention"
                if summary.matching_summary.get("duplicate_count", 0) > 0
                or summary.matching_summary.get("unmatched_segment_count", 0) > 0
                else "complete"
                if summary.matching_summary.get("candidate_count", 0) > 0
                else "pending",
                detail="Verify resumes map cleanly to candidates and duplicates are resolved.",
                metric=f"{summary.matching_summary.get('candidate_count', 0)} candidates",
                next_action="Resolve duplicates and unmatched resume segments before final review.",
            ),
            PrepWorkspaceStepRead(
                key="scoring_model",
                title="Scoring model",
                status="complete" if summary.rubric_summary.get("has_analysis") else "pending",
                detail="Confirm the PD-derived dimensions and rubric are ready for advisory scoring.",
                metric=f"{summary.rubric_summary.get('dimension_count', 0)} dimensions",
                next_action="Run the advisory analysis to generate or refresh the rubric.",
            ),
            PrepWorkspaceStepRead(
                key="launch_review",
                title="Launch advisory review",
                status="complete" if any(stage.last_run_status == "completed" for stage in plan.stages) else "pending",
                detail="Run the active stage so the selecting official sees a ranked candidate slate with evidence.",
                metric=summary.active_stage_name or "Resume Review",
                next_action=summary.next_action,
            ),
        ]

        return PrepWorkspaceViewRead(
            case_id=str(review_case.id),
            case_title=review_case.title,
            organization=review_case.organization,
            hiring_action_type=review_case.hiring_action_type,
            selecting_official=review_case.selecting_official,
            status=review_case.status,
            active_stage_id=summary.active_stage_id,
            active_stage_name=summary.active_stage_name,
            next_action=summary.next_action,
            primary_action=self._build_prep_primary_action(summary),
            steps=steps,
            issues=issues,
            templates=plan.templates,
            stages=plan.stages,
            document_summary=summary.document_summary,
            matching_summary=summary.matching_summary,
            rubric_summary=summary.rubric_summary,
            recommendation_summary=summary.recommendation_summary,
        )

    def get_review_workspace(
        self,
        db: Session,
        case_id: UUID,
        stage_id: str | None,
        candidate_id: UUID | None,
    ) -> ReviewWorkspaceViewRead:
        review_case = self._get_case(db, case_id)
        plan = self.get_plan(db, case_id)
        summary = self.get_workspace_summary(db, case_id)

        active_stage = next((stage for stage in plan.stages if stage.id == stage_id), None)
        if active_stage is None:
            active_stage = next((stage for stage in plan.stages if stage.id == plan.current_stage_id), None)
        if active_stage is None and plan.stages:
            active_stage = plan.stages[0]

        candidate_rows: list[CandidateMatrixRowRead] = []
        selected_candidate_id: str | None = None
        dossier: CandidateDossierViewRead | None = None
        empty_state: ReviewWorkspaceEmptyStateRead | None = None

        if active_stage is not None:
            candidate_rows = [
                CandidateMatrixRowRead.model_validate(row.model_dump())
                for row in self.list_stage_candidates(db, case_id, active_stage.id)
            ]
            requested_candidate_id = str(candidate_id) if candidate_id is not None else None
            selected_candidate_id = (
                requested_candidate_id
                if any(row.candidate_id == requested_candidate_id for row in candidate_rows)
                else (candidate_rows[0].candidate_id if candidate_rows else None)
            )
            if selected_candidate_id is not None:
                dossier = CandidateDossierViewRead.model_validate(
                    self.get_candidate_dossier(db, case_id, active_stage.id, UUID(selected_candidate_id)).model_dump()
                )
            else:
                empty_state = self._build_review_empty_state(plan.stages, active_stage)

        return ReviewWorkspaceViewRead(
            case_id=str(review_case.id),
            case_title=review_case.title,
            organization=review_case.organization,
            hiring_action_type=review_case.hiring_action_type,
            selecting_official=review_case.selecting_official,
            series=review_case.series,
            grade=review_case.grade,
            active_stage_id=active_stage.id if active_stage else None,
            next_action=summary.next_action,
            primary_action=self._build_review_primary_action(active_stage),
            stage_navigation=[
                ReviewStageNavItemRead(
                    id=stage.id,
                    template_key=stage.template_key,
                    name=stage.name,
                    order_index=stage.order_index,
                    status=stage.status,
                    last_run_status=stage.last_run_status,
                    last_run_at=stage.last_run_at,
                    last_run_summary=stage.last_run_summary,
                    candidate_count=stage.candidate_count if stage.last_run_status == "completed" else 0,
                    flagged_candidate_count=stage.flagged_candidate_count
                    if stage.last_run_status == "completed"
                    else 0,
                )
                for stage in plan.stages
            ],
            active_stage=active_stage,
            candidate_rows=candidate_rows,
            selected_candidate_id=selected_candidate_id,
            dossier=dossier,
            empty_state=empty_state,
            recommendation_summary=summary.recommendation_summary,
        )

    def get_decision_workspace(
        self,
        db: Session,
        case_id: UUID,
        candidate_id: UUID | None,
    ) -> DecisionWorkspaceViewRead:
        review_case = self._get_case(db, case_id)
        plan = self.get_plan(db, case_id)
        summary = self.get_workspace_summary(db, case_id)

        final_stage = next((stage for stage in plan.stages if stage.template_key == "final_selection"), None)
        if final_stage is None and plan.stages:
            final_stage = plan.stages[-1]

        try:
            recommendation = self.selection_service.get_recommendation(db, case_id)
        except HTTPException:
            recommendation = None

        candidate_rows: list[CandidateMatrixRowRead] = []
        available_candidate_ids: set[str] = set()
        if final_stage is not None:
            candidate_rows = [
                CandidateMatrixRowRead.model_validate(row.model_dump())
                for row in self.list_stage_candidates(db, case_id, final_stage.id)
            ]
            available_candidate_ids = {row.candidate_id for row in candidate_rows}

        ranking_candidate_ids = [row.candidate_id for row in recommendation.rankings] if recommendation else []
        requested_candidate_id = str(candidate_id) if candidate_id is not None else None
        selected_candidate_id = next(
            (
                candidate_key
                for candidate_key in [
                    requested_candidate_id,
                    recommendation.selectee_candidate_id if recommendation else None,
                    candidate_rows[0].candidate_id if candidate_rows else None,
                    ranking_candidate_ids[0] if ranking_candidate_ids else None,
                ]
                if candidate_key is not None
                and (not available_candidate_ids or candidate_key in available_candidate_ids)
            ),
            None,
        )

        dossier: CandidateDossierViewRead | None = None
        if (
            selected_candidate_id is not None
            and final_stage is not None
            and selected_candidate_id in available_candidate_ids
        ):
            dossier = CandidateDossierViewRead.model_validate(
                self.get_candidate_dossier(db, case_id, final_stage.id, UUID(selected_candidate_id)).model_dump()
            )

        unresolved_issues = recommendation.remaining_validation_issues if recommendation else summary.flagged_issues

        return DecisionWorkspaceViewRead(
            case_id=str(review_case.id),
            case_title=review_case.title,
            organization=review_case.organization,
            hiring_action_type=review_case.hiring_action_type,
            selecting_official=review_case.selecting_official,
            series=review_case.series,
            grade=review_case.grade,
            final_stage_id=final_stage.id if final_stage else None,
            next_action=summary.next_action,
            primary_action=self._build_decision_primary_action(final_stage, recommendation),
            recommendation=recommendation,
            candidate_rows=candidate_rows,
            selected_candidate_id=selected_candidate_id,
            dossier=dossier,
            unresolved_issues=unresolved_issues,
            export_ready=bool(recommendation and not unresolved_issues),
        )

    def _run_resume_review_stage(
        self, db: Session, review_case: ReviewCase, *, force: bool
    ) -> list[WorkflowStageCandidateRead]:
        if not force and self._has_resume_review_outputs(db, review_case.id):
            plan = self._load_or_initialize_plan(review_case)
            resume_stage = next(stage for stage in plan["stages"] if stage["template_key"] == "resume_review")
            return self._build_stage_candidate_rows(db, review_case, plan, resume_stage)

        analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == review_case.id))
        if analysis is None:
            analysis = self.position_analysis_service.analyze_case(db, review_case.id)
        self._ensure_rubric(db, review_case.id, analysis)
        self.review_workflow.run_case_evaluation(db, review_case.id)
        self.review_workflow.run_expert_council(db, review_case.id)
        try:
            self.selection_service.generate_recommendation(db, review_case.id)
        except HTTPException:
            pass
        plan = self._load_or_initialize_plan(review_case)
        resume_stage = next(stage for stage in plan["stages"] if stage["template_key"] == "resume_review")
        return self._build_stage_candidate_rows(db, review_case, plan, resume_stage)

    def _generate_narrative_questions(
        self,
        db: Session,
        review_case: ReviewCase,
        position_analysis: PositionAnalysis | None,
    ) -> dict[str, Any]:
        """Generate one shared question set from the PD only. No candidate-specific data."""
        position_title = review_case.title or "the position"
        organization = review_case.organization or "the organization"
        critical_factors: list[str] = []
        duties_text = ""
        if position_analysis:
            critical_factors = list(position_analysis.critical_factors or [])
            duties_raw = position_analysis.duties or {}
            if isinstance(duties_raw, dict):
                duties_text = "\n".join(f"- {k}: {v}" for k, v in duties_raw.items())
            elif isinstance(duties_raw, list):
                duties_text = "\n".join(f"- {d}" for d in duties_raw)
            elif isinstance(duties_raw, str):
                duties_text = duties_raw

        context_parts = [f"Position: {position_title}", f"Organization: {organization}"]
        if duties_text:
            context_parts.append(f"Major Duties:\n{duties_text}")
        if critical_factors:
            context_parts.append("Critical Factors: " + "; ".join(str(c) for c in critical_factors))
        context_block = "\n".join(context_parts)

        structured = None
        try:
            ai_payload = self.ai_gateway.invoke(
                db,
                GatewayInvocationRequest(
                    purpose="narrative_prompt_generation",
                    prompt=(
                        f"You are drafting a formal narrative request for a competitive hiring process.\n\n"
                        f"POSITION CONTEXT:\n{context_block}\n\n"
                        "Generate ONE set of narrative questions that ALL candidates for this position will receive. "
                        "Questions must be based solely on the position requirements — not on any individual candidate's background. "
                        "All candidates receive identical questions; only the salutation differs.\n\n"
                        "Return:\n"
                        "- subject_line: email subject line for this request\n"
                        "- narrative_questions: array of 4-6 questions derived from the major duties and critical factors "
                        "(each with number, question text, and context explaining which duty/factor it addresses)\n"
                        "- closing_instruction: professional closing instruction (deadline, format, length guidance)\n\n"
                        "Questions must be position-specific and assessable — not generic. "
                        "Do not reference any individual candidate."
                    ),
                    response_schema={
                        "type": "object",
                        "properties": {
                            "subject_line": {"type": "string"},
                            "narrative_questions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "number": {"type": "integer"},
                                        "question": {"type": "string"},
                                        "context": {"type": "string"},
                                    },
                                    "required": ["number", "question", "context"],
                                },
                            },
                            "closing_instruction": {"type": "string"},
                        },
                        "required": ["subject_line", "narrative_questions", "closing_instruction"],
                    },
                ),
            )
            structured = ai_payload.structured_output if isinstance(ai_payload.structured_output, dict) else None
        except Exception:
            structured = None

        if not structured:
            q_list = [f"Describe your experience with {cf}" for cf in critical_factors[:4]] or [
                "Describe your most relevant leadership experience for this position."
            ]
            structured = {
                "subject_line": f"{position_title} — Narrative Request",
                "narrative_questions": [
                    {"number": i + 1, "question": q, "context": "Derived from position requirements"}
                    for i, q in enumerate(q_list[:6])
                ],
                "closing_instruction": "Please respond in writing within 10 business days. Limit each response to 750 words.",
            }

        return {
            "questions": structured.get("narrative_questions") or [],
            "subject_line": structured.get("subject_line") or f"{position_title} — Narrative Request",
            "closing": structured.get("closing_instruction") or "Please respond in writing within 10 business days.",
        }

    def _generate_panel_questions_from_pd(
        self,
        db: Session,
        review_case: ReviewCase,
    ) -> list[dict[str, Any]]:
        """Generate one universal panel interview question set from the PD only. No candidate data."""
        position_analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == review_case.id))
        position_title = review_case.title or "the position"
        organization = review_case.organization or "the organization"
        critical_factors: list[str] = []
        duties_text = ""
        if position_analysis:
            critical_factors = list(position_analysis.critical_factors or [])
            duties_raw = position_analysis.duties or {}
            if isinstance(duties_raw, dict):
                duties_text = "\n".join(f"- {k}: {v}" for k, v in duties_raw.items())
            elif isinstance(duties_raw, list):
                duties_text = "\n".join(f"- {d}" for d in duties_raw)
            elif isinstance(duties_raw, str):
                duties_text = duties_raw

        context_parts = [f"Position: {position_title}", f"Organization: {organization}"]
        if duties_text:
            context_parts.append(f"Major Duties:\n{duties_text}")
        if critical_factors:
            context_parts.append("Critical Factors: " + "; ".join(str(c) for c in critical_factors))
        context_block = "\n".join(context_parts)

        structured = None
        try:
            ai_payload = self.ai_gateway.invoke(
                db,
                GatewayInvocationRequest(
                    purpose="panel_question_generation",
                    prompt=(
                        f"You are developing structured panel interview questions for a competitive merit-based hiring process.\n\n"
                        f"POSITION CONTEXT:\n{context_block}\n\n"
                        "Generate ONE standardized set of panel interview questions that ALL candidates will be asked. "
                        "Questions must be derived solely from the position requirements — not from any individual candidate. "
                        "All panel members will use these same questions for every candidate to ensure equal and fair evaluation.\n\n"
                        "Return panel_questions: an array of 5-7 structured interview questions. "
                        "Each question should probe a different critical factor or major duty. "
                        "Questions should be behavioral or situational in nature, require specific examples, "
                        "and be directly assessable against the position requirements.\n\n"
                        "Do not reference any individual candidate. Do not generate generic questions."
                    ),
                    response_schema={
                        "type": "object",
                        "properties": {
                            "panel_questions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "number": {"type": "integer"},
                                        "question": {"type": "string"},
                                        "focus": {"type": "string"},
                                    },
                                    "required": ["number", "question", "focus"],
                                },
                            },
                        },
                        "required": ["panel_questions"],
                    },
                ),
            )
            structured = ai_payload.structured_output if isinstance(ai_payload.structured_output, dict) else None
        except Exception:
            structured = None

        if not structured or not structured.get("panel_questions"):
            fallback_factors = critical_factors[:5] or [
                "leadership",
                "technical expertise",
                "communication",
                "problem solving",
                "collaboration",
            ]
            structured = {
                "panel_questions": [
                    {
                        "number": i + 1,
                        "question": f"Describe a specific example where you demonstrated {cf} in a role similar to this position.",
                        "focus": str(cf),
                    }
                    for i, cf in enumerate(fallback_factors)
                ]
            }

        return [
            {
                "number": q.get("number", i + 1),
                "question": str(q.get("question", "")),
                "context": str(q.get("focus", "")),
            }
            for i, q in enumerate(structured.get("panel_questions") or [])
        ]

    def _generate_prompt_request(
        self,
        db: Session,
        review_case: ReviewCase,
        stage: dict[str, Any],
        candidate: Candidate,
    ) -> dict[str, Any]:
        """Assemble a narrative request letter using the stage-level shared questions."""
        candidate_id = str(candidate.id)
        candidate_name = candidate.full_name or "Candidate"
        position_title = review_case.title or "the position"
        organization = review_case.organization or "the organization"

        stage_config = stage.get("config") or {}
        questions = stage_config.get("narrative_questions") or []
        subject = stage_config.get("narrative_subject_line") or f"{position_title} — Narrative Request"
        closing = stage_config.get("narrative_closing") or "Please respond in writing within 10 business days."

        numbered_questions = "\n\n".join(
            f"{q.get('number', i + 1)}. {q.get('question', '')}" for i, q in enumerate(questions)
        )
        letter = (
            f"Dear {candidate_name},\n\n"
            f"Thank you for your interest in the {position_title} position with {organization}. "
            f"After reviewing your application materials, you have been identified as among the "
            f"best qualified candidates and are being advanced to the next stage of the selection process.\n\n"
            f"You are being asked to provide written narrative responses to the following questions. "
            f"Your responses will be reviewed by the selection board as part of our evaluation.\n\n"
            f"{numbered_questions}\n\n"
            f"{closing}\n\n"
            f"[Selecting Official Signature Block]"
        )

        return {
            "id": str(uuid4()),
            "stage_id": str(stage["id"]),
            "artifact_type": "prompt_request",
            "title": f"Narrative Request — {candidate_name}",
            "content": letter,
            "candidate_id": candidate_id,
            "metadata": {
                "questions": questions,
                "subject_line": subject,
                "candidate_email": candidate.email,
                "generated_at": self._now_iso(),
                "prompt_sent": False,
            },
            "created_at": self._now_iso(),
            "created_by": "ai-narrative-generator",
        }

    def _analyze_narrative_response(
        self,
        db: Session,
        review_case: ReviewCase,
        stage: dict[str, Any],
        candidate: Candidate,
        response_text: str,
        prompt_artifact: dict[str, Any] | None,
        position_analysis: PositionAnalysis | None,
    ) -> dict[str, Any]:
        candidate_id = str(candidate.id)
        candidate_name = candidate.full_name or "Candidate"

        position_title = review_case.title or "the position"
        organization = review_case.organization or "the organization"

        # Original questions from prompt artifact
        questions = (prompt_artifact or {}).get("metadata", {}).get("questions") or []
        questions_text = (
            "\n".join(f"{q.get('number', i + 1)}. {q.get('question', '')}" for i, q in enumerate(questions))
            if questions
            else "No structured questions available."
        )

        # Dimension context from ratings
        ratings_rows = db.execute(
            select(CandidateRating, RubricDimension)
            .join(RubricDimension, CandidateRating.rubric_dimension_id == RubricDimension.id)
            .where(CandidateRating.candidate_id == candidate.id)
        ).all()
        ratings_context = (
            "\n".join(f"- {dim.title}: {r.rating} ({r.score}/5.00)" for r, dim in ratings_rows)
            if ratings_rows
            else "No prior dimension ratings."
        )

        # Critical factors
        critical_factors = ""
        if position_analysis:
            cf_list = position_analysis.critical_factors or []
            if cf_list:
                critical_factors = "Critical factors: " + "; ".join(str(c) for c in cf_list)

        q_count = len(questions) if questions else 3

        structured = None
        try:
            ai_payload = self.ai_gateway.invoke(
                db,
                GatewayInvocationRequest(
                    purpose="narrative_response_analysis",
                    prompt=(
                        f"You are a selection board evaluator reviewing a candidate's written narrative response "
                        f"for {position_title} at {organization}.\n\n"
                        f"POSITION CONTEXT:\n{critical_factors}\n\n"
                        f"PRIOR DIMENSION RATINGS (from resume review):\n{ratings_context}\n\n"
                        f"NARRATIVE QUESTIONS ASKED:\n{questions_text}\n\n"
                        f"CANDIDATE RESPONSE ({candidate_name}):\n{response_text}\n\n"
                        "Evaluate this response against the questions and position requirements. Return:\n"
                        "- response_score: integer 0-100\n"
                        "- response_tier: 'Strong', 'Adequate', or 'Weak'\n"
                        f"- question_assessments: one assessment per question asked ({q_count} total)\n"
                        "- expert_insights: 3-5 high-value observations about what the response reveals\n"
                        "- screening_interview_questions: 5-7 targeted questions for a screening interview, "
                        "personalized to this candidate's specific resume evidence and narrative response\n"
                        "- panel_interview_questions: 5-7 deeper probing questions suitable for a panel interview\n"
                        "- advance_recommendation: 'Advance to screening', 'Hold — response insufficient', or 'Decline'\n"
                        "- advance_rationale: one sentence explaining the recommendation\n\n"
                        "Questions must be specific, not generic. Reference actual claims the candidate made. "
                        "Probe gaps identified in resume review. Surface new evidence from the response."
                    ),
                    response_schema={
                        "type": "object",
                        "properties": {
                            "response_score": {"type": "integer"},
                            "response_tier": {"type": "string"},
                            "question_assessments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "question_number": {"type": "integer"},
                                        "addressed": {"type": "boolean"},
                                        "quality": {"type": "string"},
                                        "key_finding": {"type": "string"},
                                        "gap": {"type": "string"},
                                    },
                                    "required": ["question_number", "addressed", "quality", "key_finding"],
                                },
                            },
                            "expert_insights": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "category": {"type": "string"},
                                        "finding": {"type": "string"},
                                        "alignment": {"type": "string"},
                                    },
                                    "required": ["category", "finding", "alignment"],
                                },
                            },
                            "screening_interview_questions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "number": {"type": "integer"},
                                        "question": {"type": "string"},
                                        "focus": {"type": "string"},
                                        "basis": {"type": "string"},
                                    },
                                    "required": ["number", "question", "focus", "basis"],
                                },
                            },
                            "panel_interview_questions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "number": {"type": "integer"},
                                        "question": {"type": "string"},
                                        "focus": {"type": "string"},
                                        "basis": {"type": "string"},
                                    },
                                    "required": ["number", "question", "focus", "basis"],
                                },
                            },
                            "advance_recommendation": {"type": "string"},
                            "advance_rationale": {"type": "string"},
                        },
                        "required": [
                            "response_score",
                            "response_tier",
                            "question_assessments",
                            "expert_insights",
                            "screening_interview_questions",
                            "panel_interview_questions",
                            "advance_recommendation",
                            "advance_rationale",
                        ],
                    },
                ),
            )
            structured = ai_payload.structured_output if isinstance(ai_payload.structured_output, dict) else None
        except Exception:
            structured = None

        if not structured:
            structured = {
                "response_score": 50,
                "response_tier": "Adequate",
                "question_assessments": [],
                "expert_insights": [
                    {
                        "category": "Analysis",
                        "finding": "Response received but AI evaluation unavailable.",
                        "alignment": "N/A",
                    }
                ],
                "screening_interview_questions": [
                    {
                        "number": 1,
                        "question": "Please elaborate on your response to the narrative questions.",
                        "focus": "Clarification",
                        "basis": "AI analysis unavailable",
                    }
                ],
                "panel_interview_questions": [
                    {
                        "number": 1,
                        "question": "Please describe your most relevant experience for this position.",
                        "focus": "General suitability",
                        "basis": "AI analysis unavailable",
                    }
                ],
                "advance_recommendation": "Hold — manual review required",
                "advance_rationale": "AI analysis could not be completed; manual evaluation needed.",
            }

        summary_lines = [
            f"Response Score: {structured.get('response_score', '—')}/100 — {structured.get('response_tier', '')}",
            f"Recommendation: {structured.get('advance_recommendation', '')}",
            structured.get("advance_rationale", ""),
        ]
        summary_text = "\n".join(line for line in summary_lines if line)

        return {
            "id": str(uuid4()),
            "stage_id": str(stage["id"]),
            "artifact_type": "narrative_analysis",
            "title": f"Narrative Analysis — {candidate_name}",
            "content": summary_text,
            "candidate_id": candidate_id,
            "metadata": structured,
            "created_at": self._now_iso(),
            "created_by": "ai-narrative-evaluator",
        }

    def record_narrative_response(
        self,
        db: Session,
        case_id: UUID,
        stage_id: str,
        candidate_id: UUID,
        response_text: str,
        *,
        actor_id: str,
    ) -> StageArtifactRead:
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        self._get_stage_dict(plan, stage_id)
        candidate = self._get_candidate(db, case_id, candidate_id)

        artifacts_store = self._load_artifacts(review_case)
        stage_artifacts = artifacts_store.get(stage_id, [])

        # Remove any existing candidate_response and narrative_analysis artifacts for this candidate
        stage_artifacts = [
            a
            for a in stage_artifacts
            if not (
                a.get("candidate_id") == str(candidate_id)
                and a.get("artifact_type") in {"candidate_response", "narrative_analysis"}
            )
        ]

        response_artifact: dict[str, Any] = {
            "id": str(uuid4()),
            "stage_id": stage_id,
            "artifact_type": "candidate_response",
            "title": f"Response — {candidate.full_name or 'Candidate'}",
            "content": response_text,
            "candidate_id": str(candidate_id),
            "metadata": {"recorded_at": self._now_iso(), "recorded_by": actor_id},
            "created_at": self._now_iso(),
            "created_by": actor_id,
        }
        stage_artifacts.append(response_artifact)
        artifacts_store[stage_id] = stage_artifacts
        self._persist_artifacts(review_case, artifacts_store)
        db.commit()

        # Run AI analysis immediately (synchronous — will be fast enough for the response flow)
        try:
            position_analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == case_id))
            prompt_artifact = next(
                (
                    a
                    for a in stage_artifacts
                    if a.get("candidate_id") == str(candidate_id) and a.get("artifact_type") == "prompt_request"
                ),
                None,
            )
            analysis_artifact = self._analyze_narrative_response(
                db,
                review_case,
                self._get_stage_dict(plan, stage_id),
                candidate,
                response_text,
                prompt_artifact,
                position_analysis,
            )
            artifacts_store2 = self._load_artifacts(review_case)
            artifacts_store2.setdefault(stage_id, []).append(analysis_artifact)
            self._persist_artifacts(review_case, artifacts_store2)
            db.commit()
        except Exception:
            pass  # Analysis failure does not block response ingestion

        return StageArtifactRead(**response_artifact)

    def reset_candidate_stage_artifacts(self, db: Session, case_id: UUID, stage_id: str, candidate_id: UUID) -> None:
        review_case = self._get_case(db, case_id)
        artifacts_store = self._load_artifacts(review_case)
        cid = str(candidate_id)
        artifacts_store[stage_id] = [
            a
            for a in artifacts_store.get(stage_id, [])
            if not (
                a.get("candidate_id") == cid
                and a.get("artifact_type") in {"prompt_request", "candidate_response", "narrative_analysis"}
            )
        ]
        self._persist_artifacts(review_case, artifacts_store)
        db.flush()

    def _run_narrative_stage(
        self, db: Session, review_case: ReviewCase, stage: dict[str, Any], *, force: bool = False
    ) -> tuple[list[WorkflowStageCandidateRead], int]:
        plan = self._load_or_initialize_plan(review_case)
        rows = self._build_stage_candidate_rows(db, review_case, plan, stage)
        artifacts_store = self._load_artifacts(review_case)
        stage_artifacts = artifacts_store.get(str(stage["id"]), [])
        created_count = 0

        # Load position analysis once
        position_analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == review_case.id))

        # Generate stage-level questions from PD if not already stored
        stage_config = stage.get("config") or {}
        if not stage_config.get("narrative_questions"):
            questions_result = self._generate_narrative_questions(db, review_case, position_analysis)
            stage_config["narrative_questions"] = questions_result["questions"]
            stage_config["narrative_subject_line"] = questions_result["subject_line"]
            stage_config["narrative_closing"] = questions_result["closing"]
            stage["config"] = stage_config
            self._persist_plan(review_case, plan)
            db.flush()

        for row in rows:
            cid = row.candidate_id
            if force:
                stage_artifacts = [
                    a
                    for a in stage_artifacts
                    if not (
                        a.get("candidate_id") == cid
                        and a.get("artifact_type") in {"prompt_request", "candidate_response", "narrative_analysis"}
                    )
                ]
            has_prompt = any(
                a.get("candidate_id") == cid and a.get("artifact_type") == "prompt_request" for a in stage_artifacts
            )
            if not has_prompt:
                candidate = self._get_candidate(db, review_case.id, UUID(cid))
                try:
                    prompt_artifact = self._generate_prompt_request(db, review_case, stage, candidate)
                    stage_artifacts.append(prompt_artifact)
                    created_count += 1
                except Exception:
                    pass

            # Process responses if present
            candidate_responses = [
                a
                for a in stage_artifacts
                if a.get("candidate_id") == cid and a.get("artifact_type") == "candidate_response"
            ]
            has_analysis = any(
                a.get("candidate_id") == cid and a.get("artifact_type") == "narrative_analysis" for a in stage_artifacts
            )
            if candidate_responses and not has_analysis:
                candidate = self._get_candidate(db, review_case.id, UUID(cid))
                response_text = "\n\n".join(a["content"] for a in candidate_responses)
                prompt_artifact = next(
                    (
                        a
                        for a in stage_artifacts
                        if a.get("candidate_id") == cid and a.get("artifact_type") == "prompt_request"
                    ),
                    None,
                )
                try:
                    analysis_artifact = self._analyze_narrative_response(
                        db, review_case, stage, candidate, response_text, prompt_artifact, position_analysis
                    )
                    stage_artifacts.append(analysis_artifact)
                    structured = analysis_artifact["metadata"]
                    decisions = self._candidate_stage_decisions(candidate)
                    current = deepcopy(decisions.get(str(stage["id"]), {}))
                    current.update(
                        {
                            "stage_id": str(stage["id"]),
                            "stage_name": stage["name"],
                            "stage_type": stage["template_key"],
                            "stage_score": str(structured.get("response_score") or ""),
                            "ai_rationale": analysis_artifact["content"],
                            "proposed_disposition": str(structured.get("advance_recommendation") or ""),
                            "updated_at": self._now_iso(),
                            "updated_by": "AI advisory",
                        }
                    )
                    decisions[str(stage["id"])] = current
                    self._set_candidate_stage_decisions(candidate, decisions)
                    created_count += 1
                except Exception:
                    pass

        artifacts_store[str(stage["id"])] = stage_artifacts
        self._persist_artifacts(review_case, artifacts_store)
        db.flush()
        return self._build_stage_candidate_rows(
            db, review_case, self._load_or_initialize_plan(review_case), stage
        ), created_count

    def _collect_screening_questions_from_narrative(self, review_case: ReviewCase) -> list[dict]:
        """Aggregate and deduplicate screening_interview_questions from all narrative_analysis artifacts."""
        artifacts_store = self._load_artifacts(review_case)
        seen: set[str] = set()
        questions: list[dict] = []
        num = 1
        for stage_artifacts in artifacts_store.values():
            for a in stage_artifacts:
                if a.get("artifact_type") != "narrative_analysis":
                    continue
                meta = a.get("metadata") or {}
                for q in meta.get("screening_interview_questions") or []:
                    text = str(q.get("question") or "").strip()
                    if text and text not in seen:
                        seen.add(text)
                        questions.append(
                            {
                                "number": num,
                                "question": text,
                                "context": str(q.get("focus") or q.get("basis") or ""),
                            }
                        )
                        num += 1
        return questions

    def import_screening_questions(self, db: Session, case_id: UUID, stage_id: str) -> dict:
        """Import screening questions from narrative analysis into the interview stage config."""
        review_case = self._get_case(db, case_id)
        plan = self._load_or_initialize_plan(review_case)
        stage = next((s for s in plan.get("stages", []) if str(s.get("id")) == stage_id), None)
        if not stage:
            raise ValueError(f"Stage {stage_id} not found")
        questions = self._collect_screening_questions_from_narrative(review_case)
        stage_config = stage.get("config") or {}
        stage_config["screening_questions"] = questions
        stage["config"] = stage_config
        self._persist_plan(review_case, plan)
        db.commit()
        return {"imported": len(questions), "questions": questions}

    def _run_interview_stage(
        self, db: Session, review_case: ReviewCase, stage: dict[str, Any]
    ) -> tuple[list[WorkflowStageCandidateRead], int]:
        plan = self._load_or_initialize_plan(review_case)
        # Auto-populate screening questions from narrative analysis if not already set
        stage_config = stage.get("config") or {}
        if not stage_config.get("screening_questions"):
            questions = self._collect_screening_questions_from_narrative(review_case)
            if questions:
                stage_config["screening_questions"] = questions
                stage["config"] = stage_config
                self._persist_plan(review_case, plan)
                db.commit()
        # Auto-populate panel questions from PD if this is a panel interview stage
        if stage.get("template_key") == "panel_interview" and not stage_config.get("panel_questions"):
            panel_qs = self._generate_panel_questions_from_pd(db, review_case)
            if panel_qs:
                stage_config["panel_questions"] = panel_qs
                stage["config"] = stage_config
                self._persist_plan(review_case, plan)
                db.commit()
        rows = self._build_stage_candidate_rows(db, review_case, plan, stage)
        artifacts = self._load_artifacts(review_case).get(str(stage["id"]), [])
        created_count = 0
        for row in rows:
            candidate_artifacts = [
                entry
                for entry in artifacts
                if entry.get("candidate_id") == row.candidate_id
                and entry.get("artifact_type") in {"interview_notes", "panel_notes", "candidate_response"}
            ]
            if not candidate_artifacts:
                continue
            combined_notes = "\n\n".join(entry["content"] for entry in candidate_artifacts)
            structured = None
            try:
                ai_payload = self.ai_gateway.invoke(
                    db,
                    GatewayInvocationRequest(
                        purpose="interview_stage_summary",
                        prompt=(
                            f"Summarize the interview notes for {row.candidate_name}. "
                            "Return an advisory score, key strengths, concerns, and advancement recommendation."
                            f"\n\nInterview notes:\n{combined_notes}"
                        ),
                        response_schema={
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "stage_score": {"type": "string"},
                                "recommendation": {"type": "string"},
                                "strengths": {"type": "array", "items": {"type": "string"}},
                                "risks": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["summary", "stage_score", "recommendation", "strengths", "risks"],
                        },
                    ),
                )
                structured = ai_payload.structured_output if isinstance(ai_payload.structured_output, dict) else None
            except Exception:
                structured = None
            if not structured:
                structured = self._fallback_stage_summary(row, candidate_artifacts)
            summary_artifact = {
                "id": str(uuid4()),
                "stage_id": str(stage["id"]),
                "artifact_type": "ai_summary",
                "title": f"{row.candidate_name} {stage['name']} summary",
                "content": str(structured.get("summary") or ""),
                "candidate_id": row.candidate_id,
                "metadata": {
                    "stage_score": structured.get("stage_score"),
                    "recommendation": structured.get("recommendation"),
                    "strengths": structured.get("strengths") or [],
                    "risks": structured.get("risks") or [],
                },
                "created_at": self._now_iso(),
                "created_by": "ai-summary",
            }
            store = self._load_artifacts(review_case)
            store.setdefault(str(stage["id"]), []).append(summary_artifact)
            self._persist_artifacts(review_case, store)
            candidate = self._get_candidate(db, review_case.id, UUID(row.candidate_id))
            decisions = self._candidate_stage_decisions(candidate)
            current = deepcopy(decisions.get(str(stage["id"]), {}))
            current["stage_id"] = str(stage["id"])
            current["stage_name"] = stage["name"]
            current["stage_type"] = stage["template_key"]
            current["stage_score"] = str(structured.get("stage_score") or row.stage_score)
            current["ai_rationale"] = str(structured.get("summary") or "")
            current["proposed_disposition"] = str(structured.get("recommendation") or row.proposed_disposition)
            current["updated_at"] = self._now_iso()
            current["updated_by"] = "AI advisory"
            decisions[str(stage["id"])] = current
            self._set_candidate_stage_decisions(candidate, decisions)
            created_count += 1
        db.flush()
        return self._build_stage_candidate_rows(
            db, review_case, self._load_or_initialize_plan(review_case), stage
        ), created_count

    def _fallback_stage_summary(
        self,
        row: WorkflowStageCandidateRead,
        artifacts: list[dict[str, Any]],
        *,
        include_follow_up_questions: bool = False,
    ) -> dict[str, Any]:
        text = " ".join(str(entry.get("content") or "") for entry in artifacts).lower()
        strengths: list[str] = []
        risks: list[str] = []

        if any(keyword in text for keyword in ("lead", "leadership", "supervis", "managed", "director")):
            strengths.append("Leadership examples remained visible in the stage evidence.")
        if any(keyword in text for keyword in ("budget", "acquisition", "vendor", "contract")):
            strengths.append("Budget and acquisition judgment was addressed directly.")
        if any(keyword in text for keyword in ("cloud", "modernization", "automation", "security")):
            strengths.append("Technical modernization themes stayed aligned to the role.")
        if not strengths:
            strengths.append("Stage evidence supports continued review against the established rubric.")

        if any(keyword in text for keyword in ("limited", "lighter", "underspecified", "risk", "gap")):
            risks.append("Some claims still need stronger supporting detail or metrics.")
        if any(keyword in text for keyword in ("vendor", "sourcing", "procurement")):
            risks.append("Acquisition depth should be confirmed before final selection.")
        if not risks:
            risks.append("No major blockers were introduced in this stage, but human review remains necessary.")

        stage_score = str(self._to_decimal(row.stage_score, fallback=Decimal("72.00")))
        recommendation = row.final_disposition or row.proposed_disposition or "hold"
        summary = (
            f"{row.candidate_name} advanced through the stage with structured evidence that reinforced "
            "the existing advisory position while preserving human review for the final decision."
        )
        response = {
            "summary": summary,
            "stage_score": stage_score,
            "recommendation": recommendation,
            "strengths": dedupe_strings(strengths)[:3],
            "risks": dedupe_strings(risks)[:3],
        }
        if include_follow_up_questions:
            response["follow_up_questions"] = [
                "Which accomplishment best demonstrates executive judgment under pressure?",
                "Where is the strongest measurable outcome tied to this stage?",
                "What evidence still needs confirmation before final advancement?",
            ]
        return response

    def _serialize_stage_records(
        self, db: Session, review_case: ReviewCase, plan: dict[str, Any]
    ) -> list[WorkflowStageRead]:
        return [
            self._get_stage_record(db, review_case, plan, str(stage["id"]))
            for stage in self._sorted_stage_dicts(plan["stages"])
        ]

    def _get_stage_record(
        self, db: Session, review_case: ReviewCase, plan: dict[str, Any], stage_id: str
    ) -> WorkflowStageRead:
        stage = self._get_stage_dict(plan, stage_id)
        has_run = stage.get("last_run_status") == "completed"
        candidate_rows = self._build_stage_candidate_rows(db, review_case, plan, stage) if has_run else []
        return WorkflowStageRead(
            id=str(stage["id"]),
            template_key=str(stage["template_key"]),
            name=str(stage["name"]),
            description=str(stage["description"]),
            workspace=str(stage.get("workspace") or "review"),
            order_index=int(stage.get("order_index") or 0),
            enabled=bool(stage.get("enabled", True)),
            config=deepcopy(stage.get("config") or {}),
            guidance=stage.get("guidance"),
            status=self._stage_status_from_runtime(stage, candidate_rows),
            last_run_status=str(stage.get("last_run_status") or "not_started"),
            last_run_at=stage.get("last_run_at"),
            last_run_summary=stage.get("last_run_summary"),
            candidate_count=len(candidate_rows),
            flagged_candidate_count=sum(1 for row in candidate_rows if row.flags),
        )

    def _build_stage_candidate_rows(
        self,
        db: Session,
        review_case: ReviewCase,
        plan: dict[str, Any],
        stage: dict[str, Any],
    ) -> list[WorkflowStageCandidateRead]:
        evaluations = {
            row["candidate_id"]: row for row in self.review_workflow.list_candidate_evaluations(db, review_case.id)
        }
        review_rows = self.review_workflow.list_expert_reviews(db, review_case.id)
        reviews_by_candidate: dict[str, list[dict[str, Any]]] = {}
        for row in review_rows:
            reviews_by_candidate.setdefault(row["candidate_id"], []).append(row)
        recommendation = None
        ranking_order: dict[str, int] = {}
        try:
            recommendation = self.selection_service.get_recommendation(db, review_case.id)
        except HTTPException:
            recommendation = None
        recommendation_rows = {row.candidate_id: row for row in (recommendation.rankings if recommendation else [])}
        ranking_order = {
            row.candidate_id: index
            for index, row in enumerate(recommendation.rankings if recommendation else [], start=1)
        }
        matches = {
            str(row.candidate_id): row
            for row in db.scalars(select(CandidateMatch).where(CandidateMatch.case_id == review_case.id)).all()
        }
        candidates = db.scalars(
            select(Candidate).where(Candidate.case_id == review_case.id).order_by(Candidate.full_name.asc())
        ).all()
        rows: list[WorkflowStageCandidateRead] = []
        for candidate in candidates:
            if not self._candidate_in_stage(candidate, plan, stage, recommendation_rows):
                continue
            row = self._build_candidate_row(
                db,
                review_case,
                plan,
                stage,
                candidate,
                evaluations.get(str(candidate.id)),
                reviews_by_candidate.get(str(candidate.id), []),
                recommendation_rows.get(str(candidate.id)),
                ranking_order.get(str(candidate.id), 999),
                matches.get(str(candidate.id)),
            )
            rows.append(row)

        def _tier_sort_key(tier: str) -> int:
            t = (tier or "").upper().replace("TIER ", "").strip()
            return {"A": 0, "B": 1, "C": 2}.get(t, 9)

        return sorted(
            rows,
            key=lambda entry: (
                entry.rank if entry.rank < 900 else _tier_sort_key(entry.final_tier or entry.proposed_tier or ""),
                -float(entry.stage_score or 0),
                entry.candidate_name.lower(),
            ),
        )

    def _build_candidate_row(
        self,
        db: Session,
        review_case: ReviewCase,
        plan: dict[str, Any],
        stage: dict[str, Any],
        candidate: Candidate,
        evaluation_row: dict[str, Any] | None,
        expert_reviews: list[dict[str, Any]],
        recommendation_row: Any,
        recommendation_rank: int,
        match: CandidateMatch | None,
    ) -> WorkflowStageCandidateRead:
        ratings = self._load_dimension_scores(db, candidate.id)
        score_value = self._to_decimal(
            str(getattr(recommendation_row, "score", None) or (evaluation_row or {}).get("overall_score") or "0.00"),
            fallback=Decimal("0.00"),
        )
        candidate_stage_decisions = self._candidate_stage_decisions(candidate)
        stage_decision = candidate_stage_decisions.get(str(stage["id"]), {})
        rank = recommendation_rank
        proposed_tier = self._proposed_tier(rank, score_value, stage.get("config") or {})
        final_tier = stage_decision.get("final_tier")
        council_result = (candidate.profile or {}).get("council_result") or {}
        council_tier = council_result.get("council_tier") or None
        council_recommendation = council_result.get("council_recommendation") or None
        proposed_disposition = self._proposed_disposition(str(stage["template_key"]), proposed_tier, score_value)
        final_disposition = stage_decision.get("final_disposition")
        advancement_decision = stage_decision.get("advancement_decision")
        ai_rationale = str(
            stage_decision.get("ai_rationale")
            or getattr(recommendation_row, "consensus_summary", None)
            or getattr(recommendation_row, "notes", None)
            or (candidate.profile or {}).get("evaluation_summary")
            or ""
        )
        differentiators = dedupe_strings(
            list(getattr(recommendation_row, "strengths", []) or [])
            + [finding for finding in stage_decision.get("strengths", []) or []]
            + [
                item.get("title", "")
                for item in (expert_reviews[0].get("findings") if expert_reviews else [])
                if isinstance(item, dict)
            ]
        )[:4]
        risks = dedupe_strings(
            list(getattr(recommendation_row, "concerns", []) or [])
            + [finding for finding in stage_decision.get("risks", []) or []]
        )[:4]
        osint_summary = self._osint_summary(expert_reviews)
        flags = self._candidate_flags(candidate, match, ratings, stage, stage_decision)
        override_count = sum(1 for rating in ratings if rating.overridden) + (
            1 if final_tier or final_disposition else 0
        )
        return WorkflowStageCandidateRead(
            candidate_id=str(candidate.id),
            candidate_name=candidate.full_name,
            candidate_email=candidate.email,
            rank=rank,
            stage_status=self._stage_candidate_status(stage_decision, flags),
            stage_score=str(stage_decision.get("stage_score") or score_value.quantize(Decimal("0.01"))),
            stage_score_label=self._score_label(score_value),
            confidence=str(
                getattr(recommendation_row, "confidence", None)
                or (evaluation_row or {}).get("resume_confidence")
                or "0.00"
            ),
            matched_resume=match.matched_name if match else None,
            proposed_tier=proposed_tier,
            final_tier=str(final_tier) if final_tier is not None else None,
            council_tier=council_tier,
            council_recommendation=council_recommendation,
            proposed_disposition=proposed_disposition,
            final_disposition=str(final_disposition) if final_disposition is not None else None,
            advancement_decision=str(advancement_decision) if advancement_decision is not None else None,
            ai_rationale=ai_rationale or "AI advisory output is not available yet for this stage.",
            manual_rationale=stage_decision.get("manual_rationale"),
            differentiators=differentiators,
            risks=risks,
            osint_summary=osint_summary,
            flags=flags,
            dimension_scores=ratings,
            override_count=override_count,
        )

    def _build_stage_history(
        self,
        db: Session,
        review_case: ReviewCase,
        plan: dict[str, Any],
        candidate: Candidate,
    ) -> list[CandidateStageHistoryRead]:
        stage_decisions = self._candidate_stage_decisions(candidate)
        history: list[CandidateStageHistoryRead] = []
        for stage in self._sorted_stage_dicts(plan["stages"]):
            decision = stage_decisions.get(str(stage["id"]), {})
            if not decision and not self._candidate_in_stage(candidate, plan, stage, {}):
                continue
            history.append(
                CandidateStageHistoryRead(
                    stage_id=str(stage["id"]),
                    stage_name=str(stage["name"]),
                    stage_type=str(stage["template_key"]),
                    proposed_tier=decision.get("proposed_tier"),
                    final_tier=decision.get("final_tier"),
                    proposed_disposition=decision.get("proposed_disposition"),
                    final_disposition=decision.get("final_disposition"),
                    advancement_decision=decision.get("advancement_decision"),
                    stage_score=str(decision["stage_score"]) if decision.get("stage_score") is not None else None,
                    rationale=decision.get("manual_rationale") or decision.get("ai_rationale"),
                    updated_at=decision.get("updated_at"),
                    updated_by=decision.get("updated_by"),
                )
            )
        return history

    def _load_dimension_scores(self, db: Session, candidate_id: UUID) -> list[WorkflowDimensionScoreRead]:
        dimensions = {row.id: row for row in db.scalars(select(RubricDimension)).all()}
        ratings = db.scalars(
            select(CandidateRating)
            .where(CandidateRating.candidate_id == candidate_id)
            .order_by(CandidateRating.created_at.asc())
        ).all()
        results: list[WorkflowDimensionScoreRead] = []
        for rating in ratings:
            dimension = dimensions.get(rating.rubric_dimension_id)
            if dimension is None:
                continue
            results.append(
                WorkflowDimensionScoreRead(
                    dimension_id=str(dimension.id),
                    title=dimension.title,
                    weight=str(dimension.weight),
                    rating=rating.rating,
                    score=str(rating.score),
                    confidence=str(rating.confidence),
                    evidence_summary=rating.evidence_summary,
                    strengths=rating.strengths,
                    concerns=rating.concerns,
                    unsupported_areas=rating.unsupported_areas,
                    overridden=rating.overridden,
                    override_rationale=rating.override_rationale,
                )
            )
        return results

    def _ensure_rubric(self, db: Session, case_id: UUID, analysis: PositionAnalysis) -> Rubric:
        rubric = db.scalar(select(Rubric).where(Rubric.case_id == case_id).order_by(Rubric.updated_at.desc()))
        if rubric is not None:
            return rubric

        payload = self.position_analysis_service.build_rubric_create(analysis, "PD-Derived Resume Review")
        rubric = Rubric(
            case_id=case_id,
            position_analysis_id=analysis.id,
            name=payload.name,
            status="approved",
            version=1,
            is_locked=False,
            total_weight=sum(
                (self._to_decimal(str(entry.weight), fallback=Decimal("0.00")) for entry in payload.dimensions),
                Decimal("0.00"),
            ),
        )
        db.add(rubric)
        db.flush()
        for dimension in payload.dimensions:
            db.add(
                RubricDimension(
                    rubric_id=rubric.id,
                    title=dimension.title,
                    description=dimension.description,
                    weight=self._to_decimal(str(dimension.weight), fallback=Decimal("0.00")),
                    order_index=dimension.order_index,
                    evidence_links=dimension.evidence_links,
                    is_locked=False,
                )
            )
        db.flush()
        return rubric

    def _get_case(self, db: Session, case_id: UUID) -> ReviewCase:
        review_case = db.get(ReviewCase, case_id)
        if review_case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Engagement not found.")
        return review_case

    def _get_candidate(self, db: Session, case_id: UUID, candidate_id: UUID) -> Candidate:
        candidate = db.get(Candidate, candidate_id)
        if candidate is None or candidate.case_id != case_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found for this engagement."
            )
        return candidate

    def _load_or_initialize_plan(self, review_case: ReviewCase) -> dict[str, Any]:
        stored = deepcopy((review_case.retention_settings or {}).get(WORKFLOW_PLAN_KEY) or {})
        if stored.get("stages"):
            stored["stages"] = self._sorted_stage_dicts(stored["stages"])
            return stored
        return self._default_plan(review_case)

    def _default_plan(self, review_case: ReviewCase) -> dict[str, Any]:
        now = self._now_iso()
        stages = []
        for index, template in enumerate(STAGE_TEMPLATE_LIBRARY, start=1):
            stage = self._new_stage_dict(
                {
                    "id": template["key"],
                    "template_key": template["key"],
                    "name": template["name"],
                    "description": template["description"],
                    "workspace": template["default_workspace"],
                    "order_index": index,
                    "enabled": True,
                    "config": deepcopy(template.get("default_config") or {}),
                    "guidance": None,
                }
            )
            stages.append(stage)
        plan = {"version": 2, "updated_at": now, "stages": stages}
        self._persist_plan(review_case, plan)
        return plan

    def _persist_plan(self, review_case: ReviewCase, plan: dict[str, Any]) -> None:
        retention = deepcopy(review_case.retention_settings or {})
        plan["updated_at"] = self._now_iso()
        retention[WORKFLOW_PLAN_KEY] = plan
        review_case.retention_settings = retention

    def _load_artifacts(self, review_case: ReviewCase) -> dict[str, list[dict[str, Any]]]:
        return deepcopy((review_case.retention_settings or {}).get(WORKFLOW_ARTIFACTS_KEY) or {})

    def _persist_artifacts(self, review_case: ReviewCase, artifacts: dict[str, list[dict[str, Any]]]) -> None:
        retention = deepcopy(review_case.retention_settings or {})
        retention[WORKFLOW_ARTIFACTS_KEY] = artifacts
        review_case.retention_settings = retention

    def _get_stage_dict(self, plan: dict[str, Any], stage_id: str) -> dict[str, Any]:
        stage = next((row for row in plan["stages"] if str(row["id"]) == stage_id), None)
        if stage is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow stage not found.")
        return stage

    def _new_stage_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(payload.get("id") or uuid4()),
            "template_key": payload["template_key"],
            "name": payload["name"],
            "description": payload["description"],
            "workspace": payload.get("workspace") or "review",
            "order_index": int(payload["order_index"]),
            "enabled": bool(payload.get("enabled", True)),
            "config": deepcopy(payload.get("config") or {}),
            "guidance": payload.get("guidance"),
            "status": "not_started",
            "last_run_status": "not_started",
            "last_run_at": None,
            "last_run_summary": None,
        }

    def _sorted_stage_dicts(self, stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(stages, key=lambda row: (int(row.get("order_index") or 0), str(row.get("name") or "")))

    def _resolve_current_stage_id(self, stages: list[WorkflowStageRead]) -> str | None:
        for stage in stages:
            if stage.enabled and stage.last_run_status != "completed":
                return stage.id
        return stages[0].id if stages else None

    def _build_next_action(self, stages: list[WorkflowStageRead]) -> str:
        active = next((stage for stage in stages if stage.enabled and stage.last_run_status != "completed"), None)
        if active is None:
            return "Review the current recommendation and finalize the selection package."
        if active.template_key == "resume_review":
            return "Upload the PD and resumes if needed, then launch the advisory resume review."
        if active.template_key == "narrative_request":
            return "Send narrative prompts to the shortlisted candidates and paste their responses into the stage."
        if active.template_key in {"screening_interview", "panel_interview"}:
            return "Capture interview evidence for the candidates who advanced to this stage."
        return f"Continue the {active.name.lower()} stage."

    def _candidate_stage_decisions(self, candidate: Candidate) -> dict[str, dict[str, Any]]:
        workflow = deepcopy((candidate.profile or {}).get("workflow") or {})
        decisions = workflow.get("stage_decisions")
        return decisions if isinstance(decisions, dict) else {}

    def _set_candidate_stage_decisions(self, candidate: Candidate, decisions: dict[str, dict[str, Any]]) -> None:
        profile = deepcopy(candidate.profile or {})
        workflow = deepcopy(profile.get("workflow") or {})
        workflow["stage_decisions"] = decisions
        profile["workflow"] = workflow
        candidate.profile = profile

    def _candidate_in_stage(
        self,
        candidate: Candidate,
        plan: dict[str, Any],
        stage: dict[str, Any],
        recommendation_rows: dict[str, Any],
    ) -> bool:
        if stage["template_key"] == "resume_review":
            return True
        config = stage.get("config") or {}
        eligible_tiers = {str(entry) for entry in config.get("eligible_tiers") or []}
        if not eligible_tiers:
            eligible_tiers = {"Tier A", "Tier B"}  # default: only A/B advance; Tier C is eliminated
        stage_index = next(
            (
                index
                for index, entry in enumerate(self._sorted_stage_dicts(plan["stages"]))
                if str(entry["id"]) == str(stage["id"])
            ),
            0,
        )
        if stage_index <= 0:
            return True
        previous_stage = self._sorted_stage_dicts(plan["stages"])[stage_index - 1]
        decisions = self._candidate_stage_decisions(candidate)
        previous = decisions.get(str(previous_stage["id"]), {})
        prior_tier = previous.get("final_tier") or previous.get("proposed_tier")
        if prior_tier in eligible_tiers:
            return True
        # If an explicit manual final_tier was set and it's not eligible, respect it — don't override
        if previous.get("final_tier"):
            return False
        # Only treat advancement_decision as meaningful if it's an explicit signal.
        # Positive values (advance, hold, selected, etc.) include; negative values exclude.
        # No advancement_decision → fall through to recommendation fallback or False.
        _NEGATIVE_ADVANCEMENT = {"do_not_advance", "eliminate"}
        adv = previous.get("advancement_decision")
        if adv is not None:
            return adv not in _NEGATIVE_ADVANCEMENT
        # No explicit decision in previous stage.
        # Only fall back to recommendation score when the previous stage is resume_review —
        # subsequent stages require an explicit advancement decision to populate.
        if previous_stage.get("template_key") == "resume_review":
            recommendation_row = recommendation_rows.get(str(candidate.id))
            if recommendation_row is not None:
                proposed_tier = self._proposed_tier(
                    999,
                    self._to_decimal(str(recommendation_row.score), fallback=Decimal("0.00")),
                    previous_stage.get("config") or {},
                )
                return proposed_tier in eligible_tiers
        return False

    def _proposed_tier(self, rank: int, score_value: Decimal, config: dict[str, Any]) -> str:
        tier_labels = list(config.get("tier_labels") or ["Tier A", "Tier B", "Tier C"])
        tier_a = tier_labels[0] if tier_labels else "Tier A"
        tier_b = tier_labels[1] if len(tier_labels) > 1 else "Tier B"
        tier_c = tier_labels[2] if len(tier_labels) > 2 else "Tier C"
        tier_a_threshold = Decimal(str(config.get("tier_a_threshold", "82.00")))
        tier_b_threshold = Decimal(str(config.get("tier_b_threshold", "68.00")))
        if score_value >= tier_a_threshold or rank <= 3:
            return tier_a
        if score_value >= tier_b_threshold or rank <= 8:
            return tier_b
        return tier_c

    def _proposed_disposition(self, template_key: str, proposed_tier: str, score_value: Decimal) -> str:
        if template_key == "final_selection":
            if proposed_tier == "Tier A" and score_value >= Decimal("82.00"):
                return "selectee_ready"
            if proposed_tier == "Tier B":
                return "alternate_ready"
            return "do_not_advance"
        if proposed_tier == "Tier A":
            return "advance"
        if proposed_tier == "Tier B":
            return "hold"
        return "do_not_advance"

    def _score_label(self, score_value: Decimal) -> str:
        if score_value >= Decimal("82.00"):
            return "Leading"
        if score_value >= Decimal("68.00"):
            return "Competitive"
        if score_value >= Decimal("50.00"):
            return "Mixed"
        return "Needs review"

    def _candidate_flags(
        self,
        candidate: Candidate,
        match: CandidateMatch | None,
        ratings: list[WorkflowDimensionScoreRead],
        stage: dict[str, Any],
        stage_decision: dict[str, Any],
    ) -> list[str]:
        flags: list[str] = []
        if match is None or match.resume_segment_id is None:
            flags.append("Resume match needs review")
        if not ratings and stage["template_key"] == "resume_review":
            flags.append("Scoring has not been generated")
        if candidate.disposition == CandidateDisposition.DISCARDED.value:
            flags.append("Candidate is currently discarded")
        return flags

    def _stage_candidate_status(self, stage_decision: dict[str, Any], flags: list[str]) -> str:
        if stage_decision.get("final_disposition") or stage_decision.get("advancement_decision"):
            return "decision_recorded"
        if stage_decision.get("stage_score"):
            return "analysis_ready"
        if flags:
            return "attention"
        return "ready"

    def _stage_status_from_runtime(
        self, stage: dict[str, Any], candidate_rows: list[WorkflowStageCandidateRead]
    ) -> str:
        if stage.get("last_run_status") == "completed":
            return "completed"
        if any(row.flags for row in candidate_rows):
            return "attention"
        if candidate_rows:
            return "ready"
        return "not_started"

    def _osint_summary(self, reviews: list[dict[str, Any]]) -> str | None:
        osint_like = [
            row.get("summary", "")
            for row in reviews
            if row.get("agent_type") in {"mission_alignment_expert", "compliance_reviewer", "selection_reviewer"}
        ]
        if not osint_like:
            return None
        return " ".join(text for text in osint_like if text).strip()[:400]

    def _artifacts_for_candidate(
        self, review_case: ReviewCase, stage_id: str, candidate_id: str
    ) -> list[dict[str, Any]]:
        artifacts = self._load_artifacts(review_case).get(stage_id, [])
        return [entry for entry in artifacts if entry.get("candidate_id") in {None, candidate_id}]

    def _recommendation_summary(self, db: Session, case_id: UUID, candidate_id: str | None) -> dict[str, Any] | None:
        try:
            recommendation = self.selection_service.get_recommendation(db, case_id)
        except HTTPException:
            return None
        if candidate_id is None:
            return {
                "selectee_candidate_name": recommendation.selectee_candidate_name,
                "alternate_candidate_names": recommendation.alternate_candidate_names,
                "interview_slate_candidate_names": recommendation.interview_slate_candidate_names,
                "status": recommendation.status,
                "confidence": str(recommendation.confidence),
                "rationale": recommendation.rationale,
            }
        ranking = next((row for row in recommendation.rankings if row.candidate_id == candidate_id), None)
        if ranking is None:
            return None
        return {
            "candidate_name": ranking.candidate_name,
            "score": str(ranking.score),
            "disposition": ranking.disposition,
            "strengths": ranking.strengths,
            "concerns": ranking.concerns,
            "notes": ranking.notes,
            "selectee_candidate_name": recommendation.selectee_candidate_name,
        }

    def _has_resume_review_outputs(self, db: Session, case_id: UUID) -> bool:
        has_ratings = (
            db.scalar(select(CandidateRating.id).join(Candidate).where(Candidate.case_id == case_id)) is not None
        )
        has_reviews = db.scalar(select(ExpertReview.id).where(ExpertReview.case_id == case_id)) is not None
        try:
            self.selection_service.get_recommendation(db, case_id)
            has_recommendation = True
        except HTTPException:
            has_recommendation = False
        return has_ratings and has_reviews and has_recommendation

    def _build_flagged_issues(
        self,
        document_summary: dict[str, Any],
        matching_summary: dict[str, Any],
        recommendation_summary: dict[str, Any] | None,
    ) -> list[str]:
        issues: list[str] = []
        if document_summary.get("position_descriptions", 0) == 0:
            issues.append("A position description has not been uploaded yet.")
        if document_summary.get("resume_files", 0) == 0:
            issues.append("No resumes are on file yet.")
        if document_summary.get("flagged_documents", 0) > 0:
            issues.append("Some uploaded documents failed parsing and need attention.")
        if matching_summary.get("duplicate_count", 0) > 0:
            issues.append("Candidate matching has duplicates to resolve.")
        return issues

    def _issue_from_text(self, detail: str) -> PrepWorkspaceIssueRead:
        lowered = detail.lower()
        title = "Needs attention"
        severity = "attention"
        anchor = "prep-exceptions"
        if "position description" in lowered:
            title = "Position description missing"
            anchor = "prep-materials"
        elif "resumes" in lowered:
            title = "Resume package missing"
            anchor = "prep-materials"
        elif "parsing" in lowered or "document" in lowered:
            title = "Parsing issue"
            anchor = "prep-exceptions"
        elif "duplicate" in lowered:
            title = "Duplicate candidates detected"
            anchor = "prep-exceptions"
        elif "unmatched" in lowered:
            title = "Resume matching incomplete"
            anchor = "prep-exceptions"
        return PrepWorkspaceIssueRead(title=title, detail=detail, severity=severity, anchor=anchor)

    def _build_prep_primary_action(self, summary: WorkflowWorkspaceSummaryRead) -> WorkspacePrimaryActionRead:
        if (
            summary.document_summary.get("position_descriptions", 0) == 0
            or summary.document_summary.get("resume_files", 0) == 0
        ):
            return WorkspacePrimaryActionRead(
                label="Upload materials",
                detail="Load the PD and resume package before running the advisory workflow.",
                action="upload_materials",
                disabled=False,
                target_section="prep-materials",
            )
        if summary.document_summary.get("flagged_documents", 0) > 0:
            return WorkspacePrimaryActionRead(
                label="Review parsing issues",
                detail="Some files failed parsing and should be corrected before analysis runs.",
                action="review_parsing",
                disabled=False,
                target_section="prep-exceptions",
            )
        if (
            summary.matching_summary.get("duplicate_count", 0) > 0
            or summary.matching_summary.get("unmatched_segment_count", 0) > 0
        ):
            return WorkspacePrimaryActionRead(
                label="Resolve candidate matching",
                detail="Resume segmentation or candidate matching still needs cleanup.",
                action="resolve_matching",
                disabled=False,
                target_section="prep-exceptions",
            )
        if summary.recommendation_summary is None:
            return WorkspacePrimaryActionRead(
                label="Run resume review",
                detail="Generate the first ranked slate and evidence package for the selecting official.",
                action="run_resume_review",
                disabled=False,
                target_section="prep-launch",
            )
        return WorkspacePrimaryActionRead(
            label="Open selecting official workspace",
            detail="The review package is ready for decision-making.",
            action="open_review_workspace",
            disabled=False,
        )

    def _build_review_primary_action(self, active_stage: WorkflowStageRead | None) -> WorkspacePrimaryActionRead:
        if active_stage is None:
            return WorkspacePrimaryActionRead(
                label="Open an engagement",
                detail="Select an engagement with an active workflow stage to continue.",
                action="open_engagement",
                disabled=True,
            )
        if active_stage.template_key == "final_selection" and active_stage.last_run_status == "completed":
            return WorkspacePrimaryActionRead(
                label="Review recommendation",
                detail=active_stage.last_run_summary
                or "Review the recommended selectee, alternates, and rationale package.",
                action="review_recommendation",
                disabled=False,
            )
        label = "Refresh active stage" if active_stage.last_run_status == "completed" else "Run active stage"
        return WorkspacePrimaryActionRead(
            label=label,
            detail=active_stage.last_run_summary or active_stage.description,
            action="run_active_stage",
            disabled=False,
        )

    def _build_decision_primary_action(
        self, final_stage: WorkflowStageRead | None, recommendation: Any
    ) -> WorkspacePrimaryActionRead:
        if final_stage is not None and final_stage.last_run_status != "completed":
            return WorkspacePrimaryActionRead(
                label="Run final selection",
                detail=final_stage.description,
                action="run_final_stage",
                disabled=False,
                target_section="decision-package",
            )
        if recommendation is None:
            return WorkspacePrimaryActionRead(
                label="Generate decision package",
                detail="Build the final recommendation, ranking, and rationale package for selecting-official review.",
                action="generate_recommendation",
                disabled=False,
                target_section="decision-package",
            )
        if recommendation.remaining_validation_issues:
            return WorkspacePrimaryActionRead(
                label="Review validation issues",
                detail="Some recommendation blockers still need human review before export.",
                action="review_validation",
                disabled=False,
                target_section="decision-issues",
            )
        return WorkspacePrimaryActionRead(
            label="Export decision package",
            detail="The recommendation package is ready for export and final disposition review.",
            action="export_package",
            disabled=False,
            target_section="decision-package",
        )

    def _build_review_empty_state(
        self,
        stages: list[WorkflowStageRead],
        active_stage: WorkflowStageRead,
    ) -> ReviewWorkspaceEmptyStateRead:
        if active_stage.last_run_status != "completed":
            return ReviewWorkspaceEmptyStateRead(
                title="This stage has not been run yet",
                detail=active_stage.description,
                action_label="Run this stage",
                action="run_active_stage",
            )

        ordered_stages = sorted(stages, key=lambda row: row.order_index)
        current_index = next((index for index, stage in enumerate(ordered_stages) if stage.id == active_stage.id), 0)
        previous_stage = ordered_stages[current_index - 1] if current_index > 0 else None
        if previous_stage is not None:
            return ReviewWorkspaceEmptyStateRead(
                title="No candidates are in this stage",
                detail="Review the prior stage and adjust advancement decisions if more candidates should move forward.",
                action_label=f"Open {previous_stage.name}",
                action="open_stage",
                target_stage_id=previous_stage.id,
            )
        return ReviewWorkspaceEmptyStateRead(
            title="No candidates are ready yet",
            detail="Finish intake and run the first stage to populate the review desk.",
            action_label="Go to intake",
            action="open_intake",
        )

    def _map_candidate_disposition(self, value: str, current: str) -> str:
        normalized = value.strip().lower()
        if normalized in {
            CandidateDisposition.UNDER_REVIEW.value,
            CandidateDisposition.INTERVIEW_SLATE.value,
            CandidateDisposition.SELECTEE.value,
            CandidateDisposition.ALTERNATE.value,
            CandidateDisposition.DISCARDED.value,
        }:
            return normalized
        if normalized in {"advance", "hold"}:
            return CandidateDisposition.UNDER_REVIEW.value
        if normalized == "interview":
            return CandidateDisposition.INTERVIEW_SLATE.value
        if normalized == "alternate_ready":
            return CandidateDisposition.ALTERNATE.value
        if normalized in {"do_not_advance", "eliminate"}:
            return CandidateDisposition.DISCARDED.value
        if normalized == "selectee_ready":
            return CandidateDisposition.SELECTEE.value
        return current

    def _to_decimal(self, raw: str, *, fallback: Decimal) -> Decimal:
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError, TypeError):
            return fallback

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
