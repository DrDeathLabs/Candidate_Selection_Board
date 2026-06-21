from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.selection import SelectionRecommendationRead


class WorkflowStageTemplateRead(BaseModel):
    key: str
    name: str
    description: str
    default_workspace: str
    default_config: dict[str, Any] = Field(default_factory=dict)
    supports_artifacts: bool = True
    supports_ai_run: bool = True
    supports_candidate_decisions: bool = True


class WorkflowStageCreate(BaseModel):
    template_key: str
    name: str
    description: str
    workspace: str = "review"
    order_index: int
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    guidance: str | None = None


class WorkflowStageUpdate(BaseModel):
    template_key: str | None = None
    name: str | None = None
    description: str | None = None
    workspace: str | None = None
    order_index: int | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    guidance: str | None = None


class WorkflowStageRead(BaseModel):
    id: str
    template_key: str
    name: str
    description: str
    workspace: str
    order_index: int
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    guidance: str | None = None
    status: str
    last_run_status: str
    last_run_at: str | None = None
    last_run_summary: str | None = None
    candidate_count: int = 0
    flagged_candidate_count: int = 0


class EngagementWorkflowPlanUpdate(BaseModel):
    stages: list[WorkflowStageCreate] = Field(default_factory=list)


class EngagementWorkflowPlanRead(BaseModel):
    case_id: str
    case_title: str
    current_stage_id: str | None = None
    next_action: str
    updated_at: str
    templates: list[WorkflowStageTemplateRead]
    stages: list[WorkflowStageRead]


class WorkflowDimensionScoreRead(BaseModel):
    dimension_id: str
    title: str
    weight: str
    rating: str
    score: str
    confidence: str
    evidence_summary: str
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    unsupported_areas: list[str] = Field(default_factory=list)
    overridden: bool = False
    override_rationale: str | None = None


class WorkflowStageCandidateRead(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_email: str | None = None
    rank: int
    stage_status: str
    stage_score: str
    stage_score_label: str
    confidence: str
    matched_resume: str | None = None
    proposed_tier: str
    final_tier: str | None = None
    council_tier: str | None = None
    council_recommendation: str | None = None
    proposed_disposition: str
    final_disposition: str | None = None
    advancement_decision: str | None = None
    ai_rationale: str
    manual_rationale: str | None = None
    differentiators: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    osint_summary: str | None = None
    flags: list[str] = Field(default_factory=list)
    dimension_scores: list[WorkflowDimensionScoreRead] = Field(default_factory=list)
    override_count: int = 0


class WorkflowStageRunRequest(BaseModel):
    force: bool = False


class WorkflowStageRunResult(BaseModel):
    case_id: str
    stage_id: str
    status: str
    run_summary: str
    candidate_count: int = 0
    artifact_count: int = 0


class DimensionOverrideInput(BaseModel):
    dimension_id: str
    rating: str | None = None
    score: str | None = None
    rationale: str | None = None


class RubricWeightOverrideInput(BaseModel):
    dimension_id: str
    weight: str
    rationale: str | None = None


class CandidateStageDecisionRequest(BaseModel):
    stage_score: str | None = None
    final_tier: str | None = None
    clear_final_tier: bool = False
    final_disposition: str | None = None
    clear_final_disposition: bool = False
    advancement_decision: str | None = None
    clear_advancement_decision: bool = False
    clear_all_overrides: bool = False
    rationale: str | None = None
    notes: str | None = None
    dimension_overrides: list[DimensionOverrideInput] = Field(default_factory=list)
    rubric_weight_overrides: list[RubricWeightOverrideInput] = Field(default_factory=list)


class StageArtifactCreate(BaseModel):
    artifact_type: str
    title: str
    content: str
    candidate_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageArtifactRead(BaseModel):
    id: str
    stage_id: str
    artifact_type: str
    title: str
    content: str
    candidate_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    created_by: str | None = None


class CandidateStageHistoryRead(BaseModel):
    stage_id: str
    stage_name: str
    stage_type: str
    proposed_tier: str | None = None
    final_tier: str | None = None
    proposed_disposition: str | None = None
    final_disposition: str | None = None
    advancement_decision: str | None = None
    stage_score: str | None = None
    rationale: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None


class WorkflowAuditEventRead(BaseModel):
    id: str
    actor_id: str
    event_type: str
    entity_type: str
    entity_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str


class WorkflowCandidateDossierRead(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_email: str | None = None
    disposition: str
    matched_resume: str | None = None
    resume_confidence: str = "0.00"
    evaluation_summary: str | None = None
    resume_profile: dict[str, Any] | None = None
    stage_record: WorkflowStageCandidateRead
    stage_history: list[CandidateStageHistoryRead] = Field(default_factory=list)
    ratings: list[WorkflowDimensionScoreRead] = Field(default_factory=list)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    expert_reviews: list[dict[str, Any]] = Field(default_factory=list)
    interview_questions: list[dict[str, Any]] = Field(default_factory=list)
    pairwise_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    stage_artifacts: list[StageArtifactRead] = Field(default_factory=list)
    audit_events: list[WorkflowAuditEventRead] = Field(default_factory=list)
    recommendation_summary: dict[str, Any] | None = None


class WorkflowWorkspaceSummaryRead(BaseModel):
    case_id: str
    case_title: str
    organization: str | None = None
    hiring_action_type: str | None = None
    selecting_official: str | None = None
    active_stage_id: str | None = None
    active_stage_name: str | None = None
    active_stage_status: str | None = None
    next_action: str
    document_summary: dict[str, Any] = Field(default_factory=dict)
    matching_summary: dict[str, Any] = Field(default_factory=dict)
    rubric_summary: dict[str, Any] = Field(default_factory=dict)
    recommendation_summary: dict[str, Any] | None = None
    flagged_issues: list[str] = Field(default_factory=list)
    prep_progress: list[dict[str, Any]] = Field(default_factory=list)
    stage_counts: dict[str, int] = Field(default_factory=dict)


class WorkspacePrimaryActionRead(BaseModel):
    label: str
    detail: str
    action: str
    disabled: bool = False
    target_section: str | None = None


class PrepWorkspaceStepRead(BaseModel):
    key: str
    title: str
    status: str
    detail: str
    metric: str | None = None
    next_action: str


class PrepWorkspaceIssueRead(BaseModel):
    title: str
    detail: str
    severity: str
    anchor: str | None = None


class PrepWorkspaceViewRead(BaseModel):
    case_id: str
    case_title: str
    organization: str | None = None
    hiring_action_type: str | None = None
    selecting_official: str | None = None
    status: str
    active_stage_id: str | None = None
    active_stage_name: str | None = None
    next_action: str
    primary_action: WorkspacePrimaryActionRead
    steps: list[PrepWorkspaceStepRead] = Field(default_factory=list)
    issues: list[PrepWorkspaceIssueRead] = Field(default_factory=list)
    templates: list[WorkflowStageTemplateRead] = Field(default_factory=list)
    stages: list[WorkflowStageRead] = Field(default_factory=list)
    document_summary: dict[str, Any] = Field(default_factory=dict)
    matching_summary: dict[str, Any] = Field(default_factory=dict)
    rubric_summary: dict[str, Any] = Field(default_factory=dict)
    recommendation_summary: dict[str, Any] | None = None


class ReviewStageNavItemRead(BaseModel):
    id: str
    template_key: str
    name: str
    order_index: int
    status: str
    last_run_status: str
    last_run_at: str | None = None
    last_run_summary: str | None = None
    candidate_count: int = 0
    flagged_candidate_count: int = 0


class CandidateMatrixRowRead(WorkflowStageCandidateRead):
    pass


class CandidateDossierViewRead(WorkflowCandidateDossierRead):
    pass


class ReviewWorkspaceEmptyStateRead(BaseModel):
    title: str
    detail: str
    action_label: str | None = None
    action: str | None = None
    target_stage_id: str | None = None


class ReviewWorkspaceViewRead(BaseModel):
    case_id: str
    case_title: str
    organization: str | None = None
    hiring_action_type: str | None = None
    selecting_official: str | None = None
    series: str | None = None
    grade: str | None = None
    active_stage_id: str | None = None
    next_action: str
    primary_action: WorkspacePrimaryActionRead
    stage_navigation: list[ReviewStageNavItemRead] = Field(default_factory=list)
    active_stage: WorkflowStageRead | None = None
    candidate_rows: list[CandidateMatrixRowRead] = Field(default_factory=list)
    selected_candidate_id: str | None = None
    dossier: CandidateDossierViewRead | None = None
    empty_state: ReviewWorkspaceEmptyStateRead | None = None
    recommendation_summary: dict[str, Any] | None = None


class DecisionWorkspaceViewRead(BaseModel):
    case_id: str
    case_title: str
    organization: str | None = None
    hiring_action_type: str | None = None
    selecting_official: str | None = None
    series: str | None = None
    grade: str | None = None
    final_stage_id: str | None = None
    next_action: str
    primary_action: WorkspacePrimaryActionRead
    recommendation: SelectionRecommendationRead | None = None
    candidate_rows: list[CandidateMatrixRowRead] = Field(default_factory=list)
    selected_candidate_id: str | None = None
    dossier: CandidateDossierViewRead | None = None
    unresolved_issues: list[str] = Field(default_factory=list)
    export_ready: bool = False
