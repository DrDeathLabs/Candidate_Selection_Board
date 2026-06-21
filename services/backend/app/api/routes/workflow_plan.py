from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal
from app.db.session import get_db
from app.schemas.workflow_plan import (
    CandidateStageDecisionRequest,
    DecisionWorkspaceViewRead,
    EngagementWorkflowPlanRead,
    EngagementWorkflowPlanUpdate,
    PrepWorkspaceViewRead,
    ReviewWorkspaceViewRead,
    StageArtifactCreate,
    StageArtifactRead,
    WorkflowCandidateDossierRead,
    WorkflowStageCandidateRead,
    WorkflowStageCreate,
    WorkflowStageRead,
    WorkflowStageRunRequest,
    WorkflowStageRunResult,
    WorkflowStageUpdate,
    WorkflowWorkspaceSummaryRead,
)
from app.services.workflow_plan import WorkflowPlanService


class NarrativeResponseRequest(BaseModel):
    response_text: str


router = APIRouter()
workflow_plan_service = WorkflowPlanService()


@router.get("/workflow-plan", response_model=EngagementWorkflowPlanRead)
def get_workflow_plan(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> EngagementWorkflowPlanRead:
    return workflow_plan_service.get_plan(db, case_id)


@router.put("/workflow-plan", response_model=EngagementWorkflowPlanRead)
def replace_workflow_plan(
    case_id: UUID,
    payload: EngagementWorkflowPlanUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> EngagementWorkflowPlanRead:
    return workflow_plan_service.replace_plan(db, case_id, payload.stages)


@router.get("/workflow-plan/summary", response_model=WorkflowWorkspaceSummaryRead)
def get_workflow_workspace_summary(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> WorkflowWorkspaceSummaryRead:
    return workflow_plan_service.get_workspace_summary(db, case_id)


@router.get("/prep-workspace", response_model=PrepWorkspaceViewRead)
def get_prep_workspace(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> PrepWorkspaceViewRead:
    return workflow_plan_service.get_prep_workspace(db, case_id)


@router.get("/review-workspace", response_model=ReviewWorkspaceViewRead)
def get_review_workspace(
    case_id: UUID,
    stage: str | None = None,
    candidate: UUID | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ReviewWorkspaceViewRead:
    return workflow_plan_service.get_review_workspace(db, case_id, stage, candidate)


@router.get("/decision-workspace", response_model=DecisionWorkspaceViewRead)
def get_decision_workspace(
    case_id: UUID,
    candidate: UUID | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> DecisionWorkspaceViewRead:
    return workflow_plan_service.get_decision_workspace(db, case_id, candidate)


@router.post("/workflow-plan/stages", response_model=EngagementWorkflowPlanRead)
def add_workflow_stage(
    case_id: UUID,
    payload: WorkflowStageCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> EngagementWorkflowPlanRead:
    return workflow_plan_service.add_stage(db, case_id, payload)


@router.put("/workflow-plan/stages/{stage_id}", response_model=WorkflowStageRead)
def update_workflow_stage(
    case_id: UUID,
    stage_id: str,
    payload: WorkflowStageUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> WorkflowStageRead:
    return workflow_plan_service.update_stage(db, case_id, stage_id, payload)


@router.post("/workflow-plan/stages/{stage_id}/clear-overrides", response_model=WorkflowStageRead)
def clear_stage_overrides(
    case_id: UUID,
    stage_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> WorkflowStageRead:
    return workflow_plan_service.clear_stage_overrides(db, case_id, stage_id)


@router.post("/workflow-plan/stages/{stage_id}/run", response_model=WorkflowStageRunResult)
def run_workflow_stage(
    case_id: UUID,
    stage_id: str,
    payload: WorkflowStageRunRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> WorkflowStageRunResult:
    return workflow_plan_service.run_stage(db, case_id, stage_id, force=payload.force)


@router.get("/workflow-plan/stages/{stage_id}/candidates", response_model=list[WorkflowStageCandidateRead])
def list_stage_candidates(
    case_id: UUID,
    stage_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[WorkflowStageCandidateRead]:
    return workflow_plan_service.list_stage_candidates(db, case_id, stage_id)


@router.post(
    "/workflow-plan/stages/{stage_id}/candidates/{candidate_id}/decision", response_model=WorkflowCandidateDossierRead
)
def record_stage_decision(
    case_id: UUID,
    stage_id: str,
    candidate_id: UUID,
    payload: CandidateStageDecisionRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> WorkflowCandidateDossierRead:
    return workflow_plan_service.record_candidate_decision(
        db,
        case_id,
        stage_id,
        candidate_id,
        payload,
        actor_id=principal.user_id,
        actor_name=principal.display_name,
    )


@router.post("/workflow-plan/stages/{stage_id}/artifacts", response_model=StageArtifactRead)
def create_stage_artifact(
    case_id: UUID,
    stage_id: str,
    payload: StageArtifactCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> StageArtifactRead:
    return workflow_plan_service.add_stage_artifact(
        db,
        case_id,
        stage_id,
        payload,
        actor_id=principal.user_id,
    )


@router.delete("/workflow-plan/stages/{stage_id}/candidates/{candidate_id}/artifacts")
def reset_candidate_narrative_artifacts(
    case_id: UUID,
    stage_id: str,
    candidate_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    workflow_plan_service.reset_candidate_stage_artifacts(db, case_id, stage_id, candidate_id)
    return {"deleted": True}


@router.post("/workflow-plan/stages/{stage_id}/import-screening-questions")
def import_screening_questions(
    case_id: UUID,
    stage_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    return workflow_plan_service.import_screening_questions(db, case_id, stage_id)


@router.post("/workflow-plan/stages/{stage_id}/candidates/{candidate_id}/response", response_model=StageArtifactRead)
def record_narrative_response(
    case_id: UUID,
    stage_id: str,
    candidate_id: UUID,
    payload: NarrativeResponseRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> StageArtifactRead:
    return workflow_plan_service.record_narrative_response(
        db,
        case_id,
        stage_id,
        candidate_id,
        payload.response_text,
        actor_id=principal.user_id,
    )


@router.get("/candidates/{candidate_id}/dossier", response_model=WorkflowCandidateDossierRead)
def get_candidate_dossier(
    case_id: UUID,
    candidate_id: UUID,
    stage_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> WorkflowCandidateDossierRead:
    return workflow_plan_service.get_candidate_dossier(db, case_id, stage_id, candidate_id)
