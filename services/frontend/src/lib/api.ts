import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "/api/v1",
  withCredentials: true,
});

// Attach CSRF token from cookie on every state-changing request
api.interceptors.request.use((config) => {
  const method = (config.method ?? "get").toLowerCase();
  if (!["get", "head", "options", "trace"].includes(method)) {
    const csrf = document.cookie
      .split("; ")
      .find((c) => c.startsWith("sb_csrf="))
      ?.split("=")[1];
    if (csrf) {
      config.headers["X-CSRF-Token"] = csrf;
    }
  }
  return config;
});

// Redirect to /login on 401 (session expired or never authenticated)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401 && !window.location.pathname.startsWith("/login")) {
      window.location.replace("/login");
    }
    return Promise.reject(err);
  },
);

export type CaseSummary = {
  id: string;
  title: string;
  status: string;
};

export type ReviewCase = {
  id: string;
  title: string;
  series: string | null;
  grade: string | null;
  organization: string | null;
  hiring_action_type: string | null;
  certificate_number: string | null;
  selecting_official: string | null;
  panel_members: Array<Record<string, unknown>>;
  data_sensitivity: string;
  retention_settings: Record<string, unknown>;
  model_provider_settings: Record<string, unknown>;
  outside_enrichment_allowed: boolean;
  status: string;
  created_at: string;
  updated_at: string;
};

export type DocumentRecord = {
  id: string;
  file_name: string;
  content_type: string;
  storage_key: string;
  checksum: string | null;
  document_type: string;
  status: string;
  page_count: number | null;
  metadata_json: Record<string, unknown>;
  malware_scan_status: string;
  created_at: string;
  updated_at: string;
};

export type DocumentProcessingSnapshot = {
  documents: DocumentRecord[];
  summary: {
    total_documents: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    by_stage: Record<string, number>;
    unreadable_or_flagged: number;
  };
};

export type AuditEventRecord = {
  id: string;
  actor_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  immutable_hash: string;
  occurred_at: string;
};

export type ExpertAgentRecord = {
  id: string;
  agent_type: string;
  display_name: string;
  description: string;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkflowQueueResponse = {
  case_id: string;
  candidate_id?: string | null;
  mode?: string;
  status: string;
  task_id: string;
  agent_count?: number;
  agents?: string[];
};

export type WorkflowStageTemplateRecord = {
  key: string;
  name: string;
  description: string;
  default_workspace: string;
  default_config: Record<string, unknown>;
  supports_artifacts: boolean;
  supports_ai_run: boolean;
  supports_candidate_decisions: boolean;
};

export type WorkflowStageRecord = {
  id: string;
  template_key: string;
  name: string;
  description: string;
  workspace: string;
  order_index: number;
  enabled: boolean;
  config: Record<string, unknown>;
  guidance: string | null;
  status: string;
  last_run_status: string;
  last_run_at: string | null;
  last_run_summary: string | null;
  candidate_count: number;
  flagged_candidate_count: number;
};

export type WorkflowPlanRecord = {
  case_id: string;
  case_title: string;
  current_stage_id: string | null;
  next_action: string;
  updated_at: string;
  templates: WorkflowStageTemplateRecord[];
  stages: WorkflowStageRecord[];
};

export type WorkflowDimensionScoreRecord = {
  dimension_id: string;
  title: string;
  weight: string;
  rating: string;
  score: string;
  confidence: string;
  evidence_summary: string;
  strengths: string[];
  concerns: string[];
  unsupported_areas: string[];
  overridden: boolean;
  override_rationale: string | null;
};

export type WorkflowStageCandidateRecord = {
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  rank: number;
  stage_status: string;
  stage_score: string;
  stage_score_label: string;
  confidence: string;
  matched_resume: string | null;
  proposed_tier: string;
  final_tier: string | null;
  council_tier: string | null;
  council_recommendation: string | null;
  proposed_disposition: string;
  final_disposition: string | null;
  advancement_decision: string | null;
  ai_rationale: string;
  manual_rationale: string | null;
  differentiators: string[];
  risks: string[];
  osint_summary: string | null;
  flags: string[];
  dimension_scores: WorkflowDimensionScoreRecord[];
  override_count: number;
};

export type WorkflowStageRunResultRecord = {
  case_id: string;
  stage_id: string;
  status: string;
  run_summary: string;
  candidate_count: number;
  artifact_count: number;
};

export type WorkflowStageInput = {
  template_key: string;
  name: string;
  description: string;
  workspace: string;
  order_index: number;
  enabled: boolean;
  config: Record<string, unknown>;
  guidance?: string | null;
};

export type WorkflowPlanUpdatePayload = {
  stages: WorkflowStageInput[];
};

export type DimensionOverridePayload = {
  dimension_id: string;
  rating?: string | null;
  score?: string | null;
  rationale?: string | null;
};

export type RubricWeightOverridePayload = {
  dimension_id: string;
  weight: string;
  rationale?: string | null;
};

export type CandidateStageDecisionPayload = {
  stage_score?: string | null;
  final_tier?: string | null;
  clear_final_tier?: boolean;
  final_disposition?: string | null;
  clear_final_disposition?: boolean;
  advancement_decision?: string | null;
  clear_advancement_decision?: boolean;
  clear_all_overrides?: boolean;
  rationale?: string | null;
  notes?: string | null;
  dimension_overrides?: DimensionOverridePayload[];
  rubric_weight_overrides?: RubricWeightOverridePayload[];
};

export type StageArtifactPayload = {
  artifact_type: string;
  title: string;
  content: string;
  candidate_id?: string | null;
  metadata: Record<string, unknown>;
};

export type StageArtifactRecord = {
  id: string;
  stage_id: string;
  artifact_type: string;
  title: string;
  content: string;
  candidate_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  created_by: string;
};

export type CandidateStageHistoryRecord = {
  stage_id: string;
  stage_name: string;
  stage_type: string;
  proposed_tier: string | null;
  final_tier: string | null;
  proposed_disposition: string | null;
  final_disposition: string | null;
  advancement_decision: string | null;
  stage_score: string | null;
  rationale: string | null;
  updated_at: string | null;
  updated_by: string | null;
};

export type WorkflowAuditEventRecord = {
  id: string;
  actor_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  occurred_at: string;
};

export type ResumeWorkExperience = {
  title: string;
  employer: string;
  grade_level: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  location: string | null;
  is_supervisory: boolean;
  team_size: number | null;
  budget: string | null;
  highlights: string[];
};

export type ResumeEducation = {
  degree: string;
  field: string | null;
  institution: string;
  graduation_year: number | null;
};

export type ResumeCertification = {
  name: string;
  issuer: string | null;
  year: number | null;
};

export type ResumeClearance = {
  level: string;
  status: string | null;
};

export type ResumeProfile = {
  name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  linkedin: string | null;
  clearance: ResumeClearance | null;
  summary: string | null;
  work_experience: ResumeWorkExperience[];
  education: ResumeEducation[];
  certifications: ResumeCertification[];
  skills: string[];
  total_years_experience: number | null;
};

export type WorkflowCandidateDossierRecord = {
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  disposition: string;
  matched_resume: string | null;
  resume_confidence: string;
  evaluation_summary: string | null;
  resume_profile: ResumeProfile | null;
  stage_record: WorkflowStageCandidateRecord;
  stage_history: CandidateStageHistoryRecord[];
  ratings: WorkflowDimensionScoreRecord[];
  facts: Array<Record<string, unknown>>;
  expert_reviews: Array<Record<string, unknown>>;
  interview_questions: Array<Record<string, unknown>>;
  pairwise_comparisons: Array<Record<string, unknown>>;
  stage_artifacts: StageArtifactRecord[];
  audit_events: WorkflowAuditEventRecord[];
  recommendation_summary: Record<string, unknown> | null;
};

export type WorkflowWorkspaceSummaryRecord = {
  case_id: string;
  case_title: string;
  organization: string | null;
  hiring_action_type: string | null;
  selecting_official: string | null;
  active_stage_id: string | null;
  active_stage_name: string | null;
  active_stage_status: string | null;
  next_action: string;
  document_summary: Record<string, number>;
  matching_summary: Record<string, number>;
  rubric_summary: Record<string, unknown>;
  recommendation_summary: Record<string, unknown> | null;
  flagged_issues: string[];
  prep_progress: Array<Record<string, unknown>>;
  stage_counts: Record<string, number>;
};

export type WorkspacePrimaryAction = {
  label: string;
  detail: string;
  action: string;
  disabled: boolean;
  target_section?: string | null;
};

export type PrepWorkspaceStepRecord = {
  key: string;
  title: string;
  status: string;
  detail: string;
  metric: string | null;
  next_action: string;
};

export type PrepWorkspaceIssueRecord = {
  title: string;
  detail: string;
  severity: string;
  anchor?: string | null;
};

export type PrepWorkspaceView = {
  case_id: string;
  case_title: string;
  organization: string | null;
  hiring_action_type: string | null;
  selecting_official: string | null;
  status: string;
  active_stage_id: string | null;
  active_stage_name: string | null;
  next_action: string;
  primary_action: WorkspacePrimaryAction;
  steps: PrepWorkspaceStepRecord[];
  issues: PrepWorkspaceIssueRecord[];
  templates: WorkflowStageTemplateRecord[];
  stages: WorkflowStageRecord[];
  document_summary: Record<string, number>;
  matching_summary: Record<string, number>;
  rubric_summary: Record<string, unknown>;
  recommendation_summary: Record<string, unknown> | null;
};

export type ReviewStageNavItem = {
  id: string;
  template_key: string;
  name: string;
  order_index: number;
  status: string;
  last_run_status: string;
  last_run_at: string | null;
  last_run_summary: string | null;
  candidate_count: number;
  flagged_candidate_count: number;
};

export type CandidateMatrixRow = WorkflowStageCandidateRecord;
export type CandidateDossierView = WorkflowCandidateDossierRecord;

export type ReviewWorkspaceView = {
  case_id: string;
  case_title: string;
  organization: string | null;
  hiring_action_type: string | null;
  selecting_official: string | null;
  series: string | null;
  grade: string | null;
  active_stage_id: string | null;
  next_action: string;
  primary_action: WorkspacePrimaryAction;
  stage_navigation: ReviewStageNavItem[];
  active_stage: WorkflowStageRecord | null;
  candidate_rows: CandidateMatrixRow[];
  selected_candidate_id: string | null;
  dossier: CandidateDossierView | null;
  empty_state: {
    title: string;
    detail: string;
    action_label?: string | null;
    action?: string | null;
    target_stage_id?: string | null;
  } | null;
  recommendation_summary: Record<string, unknown> | null;
};

export type DecisionWorkspaceView = {
  case_id: string;
  case_title: string;
  organization: string | null;
  hiring_action_type: string | null;
  selecting_official: string | null;
  series: string | null;
  grade: string | null;
  final_stage_id: string | null;
  next_action: string;
  primary_action: WorkspacePrimaryAction;
  recommendation: SelectionRecommendationRecord | null;
  candidate_rows: CandidateMatrixRow[];
  selected_candidate_id: string | null;
  dossier: CandidateDossierView | null;
  unresolved_issues: string[];
  export_ready: boolean;
};

export type PositionAnalysisRecord = {
  id: string;
  case_id: string;
  role_type: string | null;
  status: string;
  duties: Array<Record<string, unknown>>;
  critical_factors: Array<Record<string, unknown>>;
  recommended_dimensions: Array<Record<string, unknown>>;
  evidence_map: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type RubricDimensionRecord = {
  id: string;
  title: string;
  description: string;
  weight: string;
  order_index: number;
  evidence_links: Array<Record<string, unknown>>;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
};

export type RubricRecord = {
  id: string;
  name: string;
  status: string;
  version: number;
  is_locked: boolean;
  total_weight: string;
  dimensions: RubricDimensionRecord[];
  created_at: string;
  updated_at: string;
};

export type RubricDimensionInput = {
  title: string;
  description: string;
  weight: number;
  order_index: number;
  evidence_links: Array<Record<string, unknown>>;
  is_locked?: boolean;
};

export type RubricUpdatePayload = {
  name: string;
  status?: string | null;
  is_locked: boolean;
  dimensions: RubricDimensionInput[];
};

export type RankedCandidateRecord = {
  candidate_id: string;
  candidate_name: string;
  disposition: string;
  score: string;
  confidence: string;
  evaluation_score: string;
  expert_confidence: string;
  resume_confidence: string;
  interview_score: string | null;
  challenge_count: number;
  matched_resume: string | null;
  consensus_summary: string | null;
  strengths: string[];
  concerns: string[];
  notes: string | null;
};

export type SelectionRecommendationRecord = {
  id: string;
  case_id: string;
  recommendation_type: string;
  status: string;
  selectee_candidate_id: string | null;
  selectee_candidate_name: string | null;
  alternate_candidate_ids: string[];
  alternate_candidate_names: string[];
  interview_slate_candidate_ids: string[];
  interview_slate_candidate_names: string[];
  discarded_candidate_ids: string[];
  discarded_candidate_names: string[];
  rationale: string;
  non_selection_rationale: Record<string, unknown>;
  evidence_ledger: Array<Record<string, unknown>>;
  confidence: string;
  remaining_validation_issues: string[];
  rankings: RankedCandidateRecord[];
  created_at: string;
  updated_at: string;
};

export type AdjudicationActionRecord = {
  id: string;
  actor_id: string;
  action_type: string;
  target_candidate_id: string | null;
  payload: Record<string, unknown>;
  rationale: string;
  created_at: string;
  updated_at: string;
};

export type AdjudicationActionPayload = {
  action_type: string;
  rationale: string;
  target_candidate_id?: string | null;
  payload: Record<string, unknown>;
};

export type CandidateEvaluationRatingRecord = {
  id: string;
  dimension_id: string;
  rating: string;
  score: string;
  confidence: string;
  evidence_summary: string;
  strengths: string[];
  concerns: string[];
  unsupported_areas: string[];
};

export type CandidateEvaluationRecord = {
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  disposition: string;
  matched_resume: string | null;
  resume_confidence: string;
  overall_score: string;
  fact_count: number;
  ratings: CandidateEvaluationRatingRecord[];
};

export type CandidateFactRecord = {
  id: string;
  candidate_id: string;
  candidate_name: string;
  fact_type: string;
  fact_value: Record<string, unknown>;
  confidence: string;
  unsupported: boolean;
  notes: string | null;
  evidence_quote: string | null;
  source_page: number | null;
};

export type ExpertReviewFindingRecord = {
  title: string;
  detail: string;
  severity: string;
};

export type ExpertReviewRecord = {
  id: string;
  candidate_id: string;
  candidate_name: string;
  agent_type: string;
  status: string;
  summary: string;
  findings: ExpertReviewFindingRecord[];
  strengths: string[];
  concerns: string[];
  confidence: string;
  created_at: string;
  updated_at: string;
};

export type PairwiseDimensionResultRecord = {
  dimension_id: string;
  left_score: string;
  right_score: string;
  leader: string;
};

export type PairwiseComparisonRecord = {
  id: string;
  left_candidate_id: string;
  left_candidate_name: string;
  right_candidate_id: string;
  right_candidate_name: string;
  winner_candidate_id: string | null;
  winner_candidate_name: string | null;
  rationale: string;
  dimension_results: PairwiseDimensionResultRecord[];
  confidence: string;
};

export type InterviewQuestionRecord = {
  id: string;
  candidate_id: string;
  candidate_name: string;
  category: string;
  question_text: string;
  rationale: string;
  evidence_references: Array<Record<string, unknown>>;
};

export type ExportPackageRecord = {
  id: string;
  export_type: string;
  status: string;
  storage_key: string | null;
};

export type AdminSettingsRecord = {
  user: string;
  allowed_actions: string[];
};

export type OperationsOverviewRecord = {
  active_case_count: number;
  case_status_counts: Record<string, number>;
  document_status_counts: Record<string, number>;
  model_run_status_counts: Record<string, number>;
  enabled_agent_count: number;
  export_queue_count: number;
  default_provider: string;
};

export type SecurityOverviewRecord = {
  sensitivity_counts: Record<string, number>;
  outside_enrichment_case_count: number;
  audit_event_count_last_24h: number;
  admin_change_count_last_24h: number;
  provider_secret_dependencies: Array<{
    provider: string;
    enabled: boolean;
    api_key_env_var: string;
    base_url: string;
  }>;
  checklist: Array<{
    title: string;
    status: string;
    detail: string;
  }>;
};

export type AIProviderConfigRecord = {
  enabled: boolean;
  label: string;
  base_url: string;
  default_model: string;
  api_key_env_var: string;
  notes: string;
};

export type AISettingsRecord = {
  default_provider: string;
  providers: Record<string, AIProviderConfigRecord>;
};

export type AISettingsUpdatePayload = AISettingsRecord;

export type ExpertAgentUpdatePayload = {
  display_name: string;
  description: string;
  enabled: boolean;
  config: Record<string, unknown>;
};

export type ResumeSegmentRecord = {
  id: string;
  document_id: string;
  candidate_id: string | null;
  inferred_name: string | null;
  inferred_email: string | null;
  start_page: number;
  end_page: number;
  confidence: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CandidateMatchRecord = {
  id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  resume_segment_id: string | null;
  resume_document_name: string | null;
  segment_start_page: number | null;
  segment_end_page: number | null;
  inferred_name: string | null;
  inferred_email: string | null;
  matched_name: string | null;
  matched_email: string | null;
  confidence: string;
  is_duplicate: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CandidateReconciliationSummary = {
  case_id: string;
  candidate_count: number;
  matched_count: number;
  unmatched_count: number;
  duplicate_count: number;
  resume_segment_count: number;
  unmatched_segment_count: number;
};

export type CandidateReconciliationResult = {
  summary: CandidateReconciliationSummary;
  matches: CandidateMatchRecord[];
  segments: ResumeSegmentRecord[];
};

export type CandidateMatchUpdatePayload = {
  resume_segment_id: string | null;
  notes?: string | null;
};

export type CandidateCreatePayload = {
  full_name: string;
  email?: string | null;
  certificate_identifier?: string | null;
};

export type CandidateMergePayload = {
  source_candidate_id: string;
  target_candidate_id: string;
};

export type CaseCreatePayload = {
  title: string;
  series?: string | null;
  grade?: string | null;
  organization?: string | null;
  hiring_action_type?: string | null;
  certificate_number?: string | null;
  selecting_official?: string | null;
  panel_members: Array<Record<string, unknown>>;
  data_sensitivity: string;
  retention_settings: Record<string, unknown>;
  model_provider_settings: Record<string, unknown>;
  outside_enrichment_allowed: boolean;
};

export type DocumentCreatePayload = {
  file_name: string;
  content_type: string;
  storage_key?: string | null;
  checksum?: string | null;
  document_type: string;
  page_count?: number | null;
  metadata_json: Record<string, unknown>;
};

export type DocumentUploadResult = {
  document: DocumentRecord;
  processing_task_id: string;
};

export async function listCases() {
  const response = await api.get<CaseSummary[]>("/cases/");
  return response.data;
}

export async function createCase(payload: CaseCreatePayload) {
  const response = await api.post<ReviewCase>("/cases/", payload);
  return response.data;
}

export async function deleteCase(caseId: string) {
  await api.delete(`/cases/${caseId}`);
}

export async function getCase(caseId: string) {
  const response = await api.get<ReviewCase>(`/cases/${caseId}`);
  return response.data;
}

export async function registerDocument(caseId: string, payload: DocumentCreatePayload) {
  const response = await api.post<DocumentRecord>(`/cases/${caseId}/documents/`, payload);
  return response.data;
}

export async function uploadDocumentBinary(
  caseId: string,
  payload: { file: File; documentType: string; metadataSource: string },
) {
  const formData = new FormData();
  formData.append("file", payload.file);
  formData.append("document_type", payload.documentType);
  formData.append("metadata_source", payload.metadataSource);
  const response = await api.post<DocumentUploadResult>(`/cases/${caseId}/documents/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function listDocuments(caseId: string) {
  const response = await api.get<DocumentRecord[]>(`/cases/${caseId}/documents/`);
  return response.data;
}

export async function getProcessingSnapshot(caseId: string) {
  const response = await api.get<DocumentProcessingSnapshot>(`/cases/${caseId}/documents/processing-snapshot`);
  return response.data;
}

export async function listAuditEvents(caseId: string) {
  const response = await api.get<AuditEventRecord[]>(`/cases/${caseId}/audit-events/`);
  return response.data;
}

export async function listAdjudicationActions(caseId: string) {
  const response = await api.get<AdjudicationActionRecord[]>(`/cases/${caseId}/adjudications/`);
  return response.data;
}

export async function createAdjudicationAction(caseId: string, payload: AdjudicationActionPayload) {
  const response = await api.post<AdjudicationActionRecord>(`/cases/${caseId}/adjudications/`, payload);
  return response.data;
}

export async function listExports(caseId: string) {
  const response = await api.get<ExportPackageRecord[]>(`/cases/${caseId}/exports/`);
  return response.data;
}

export async function requestExport(caseId: string, exportType: string, parameters: Record<string, unknown> = {}) {
  const response = await api.post<{ export_id: string; status: string }>(`/cases/${caseId}/exports/`, {
    export_type: exportType,
    parameters,
  });
  return response.data;
}

export async function listExpertAgents() {
  const response = await api.get<ExpertAgentRecord[]>("/admin/expert-agents");
  return response.data;
}

export async function updateExpertAgent(agentId: string, payload: ExpertAgentUpdatePayload) {
  const response = await api.put<ExpertAgentRecord>(`/admin/expert-agents/${agentId}`, payload);
  return response.data;
}

export async function getAdminSettings() {
  const response = await api.get<AdminSettingsRecord>("/admin/settings");
  return response.data;
}

export async function getOperationsOverview() {
  const response = await api.get<OperationsOverviewRecord>("/admin/operations-overview");
  return response.data;
}

export async function getSecurityOverview() {
  const response = await api.get<SecurityOverviewRecord>("/admin/security-overview");
  return response.data;
}

export async function getAISettings() {
  const response = await api.get<AISettingsRecord>("/admin/ai-settings");
  return response.data;
}

export async function updateAISettings(payload: AISettingsUpdatePayload) {
  const response = await api.put<AISettingsRecord>("/admin/ai-settings", payload);
  return response.data;
}

export async function queueEvaluation(caseId: string) {
  const response = await api.post<WorkflowQueueResponse>(`/cases/${caseId}/workflow/evaluate`);
  return response.data;
}

export async function queueExpertCouncil(caseId: string) {
  const response = await api.post<WorkflowQueueResponse>(`/cases/${caseId}/workflow/expert-council`);
  return response.data;
}

export async function listCandidateEvaluations(caseId: string) {
  const response = await api.get<CandidateEvaluationRecord[]>(`/cases/${caseId}/evaluations/candidates`);
  return response.data;
}

export async function listCandidateFacts(caseId: string) {
  const response = await api.get<CandidateFactRecord[]>(`/cases/${caseId}/evaluations/facts`);
  return response.data;
}

export async function listExpertReviewsForCase(caseId: string) {
  const response = await api.get<ExpertReviewRecord[]>(`/cases/${caseId}/evaluations/expert-reviews`);
  return response.data;
}

export async function listPairwiseComparisons(caseId: string) {
  const response = await api.get<PairwiseComparisonRecord[]>(`/cases/${caseId}/evaluations/comparisons`);
  return response.data;
}

export async function listInterviewQuestions(caseId: string) {
  const response = await api.get<InterviewQuestionRecord[]>(`/cases/${caseId}/evaluations/interview-questions`);
  return response.data;
}

export type DimensionAssessment = {
  dimension: string;
  assessment: string;  // EXCEEDS / MEETS / PARTIAL / ABSENT
  evidence_quote: string;
  gap?: string;
};

export type DeliberationTurnRecord = {
  speaker: string;
  display_name: string;
  phase: string;
  content: string;
  summary: string;
  findings: Array<{ title: string; detail: string; severity: string }>;
  strengths: string[];
  concerns: string[];
  confidence: number;
  evidence_quality: string;  // DOCUMENTED / INFERRED / ABSENT
  dimension_assessments: DimensionAssessment[];
  responding_to: string[];
  timestamp: string;
};

export type BoardMeetingRecord = {
  id: string;
  case_id: string;
  candidate_id: string;
  candidate_name: string;
  status: string;
  agent_count: number;
  round_count: number;
  phase1_turns: DeliberationTurnRecord[];
  phase2_turns: DeliberationTurnRecord[];
  phase3_synthesis: {
    recommendation?: string;
    tier?: string;
    confidence?: number;
    agreements?: string[];
    open_questions?: string[];
  };
  all_turns: DeliberationTurnRecord[];
  full_transcript: string;
  meeting_notes: Record<string, unknown>;
  meeting_summary: string;
  created_at: string;
  updated_at: string;
};

export async function listBoardMeetings(caseId: string) {
  const response = await api.get<BoardMeetingRecord[]>(`/cases/${caseId}/evaluations/board-meetings`);
  return response.data;
}

export async function getBoardMeeting(caseId: string, candidateId: string) {
  const response = await api.get<BoardMeetingRecord>(`/cases/${caseId}/evaluations/board-meetings/${candidateId}`);
  return response.data;
}

export async function deleteBoardMeeting(caseId: string, candidateId: string) {
  const response = await api.delete<{ deleted: number }>(`/cases/${caseId}/evaluations/board-meetings/${candidateId}`);
  return response.data;
}

export async function deleteAllBoardMeetings(caseId: string) {
  const response = await api.delete<{ deleted: number }>(`/cases/${caseId}/evaluations/board-meetings`);
  return response.data;
}

export async function stopCouncil(caseId: string) {
  const response = await api.post<{ status: string }>(`/cases/${caseId}/evaluations/stop-council`);
  return response.data;
}

export async function getPositionAnalysis(caseId: string) {
  const response = await api.get<PositionAnalysisRecord>(`/cases/${caseId}/analysis/position`);
  return response.data;
}

export async function runPositionAnalysis(caseId: string) {
  const response = await api.post<PositionAnalysisRecord>(`/cases/${caseId}/analysis/position/run`);
  return response.data;
}

export async function getCandidateReconciliationSummary(caseId: string) {
  const response = await api.get<CandidateReconciliationSummary>(`/cases/${caseId}/candidates/reconciliation`);
  return response.data;
}

export async function listCandidatesForCase(caseId: string) {
  const response = await api.get<CandidateRecord[]>(`/cases/${caseId}/candidates/`);
  return response.data;
}

export async function listCandidateMatches(caseId: string) {
  const response = await api.get<CandidateMatchRecord[]>(`/cases/${caseId}/candidates/matches`);
  return response.data;
}

export async function listResumeSegments(caseId: string) {
  const response = await api.get<ResumeSegmentRecord[]>(`/cases/${caseId}/candidates/resume-segments`);
  return response.data;
}

export async function runCandidateReconciliation(caseId: string) {
  const response = await api.post<CandidateReconciliationResult>(`/cases/${caseId}/candidates/reconcile`);
  return response.data;
}

export async function updateCandidateMatch(caseId: string, candidateId: string, payload: CandidateMatchUpdatePayload) {
  const response = await api.put<CandidateReconciliationResult>(`/cases/${caseId}/candidates/${candidateId}/match`, payload);
  return response.data;
}

export type CandidateRecord = {
  id: string;
  full_name: string;
  email: string | null;
  certificate_identifier: string | null;
  disposition: string;
  profile: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export async function createCandidate(caseId: string, payload: CandidateCreatePayload) {
  const response = await api.post<CandidateRecord>(`/cases/${caseId}/candidates/`, payload);
  return response.data;
}

export async function mergeCandidates(caseId: string, payload: CandidateMergePayload) {
  const response = await api.post<CandidateReconciliationResult>(`/cases/${caseId}/candidates/merge`, payload);
  return response.data;
}

export async function listRubrics(caseId: string) {
  const response = await api.get<RubricRecord[]>(`/cases/${caseId}/rubrics/`);
  return response.data;
}

export async function getRubric(caseId: string, rubricId: string) {
  const response = await api.get<RubricRecord>(`/cases/${caseId}/rubrics/${rubricId}`);
  return response.data;
}

export async function createRubricFromAnalysis(caseId: string) {
  const response = await api.post<RubricRecord>(`/cases/${caseId}/rubrics/from-analysis`);
  return response.data;
}

export async function updateRubric(caseId: string, rubricId: string, payload: RubricUpdatePayload) {
  const response = await api.put<RubricRecord>(`/cases/${caseId}/rubrics/${rubricId}`, payload);
  return response.data;
}

export async function setRubricLock(caseId: string, rubricId: string, isLocked: boolean) {
  const response = await api.post<RubricRecord>(`/cases/${caseId}/rubrics/${rubricId}/lock`, { is_locked: isLocked });
  return response.data;
}

export async function getSelectionRecommendation(caseId: string) {
  const response = await api.get<SelectionRecommendationRecord>(`/cases/${caseId}/selection/recommendation`);
  return response.data;
}

export async function generateSelectionRecommendation(caseId: string) {
  const response = await api.post<SelectionRecommendationRecord>(`/cases/${caseId}/selection/recommendation/generate`);
  return response.data;
}

export async function getWorkflowPlan(caseId: string) {
  const response = await api.get<WorkflowPlanRecord>(`/cases/${caseId}/workflow-plan`);
  return response.data;
}

export async function replaceWorkflowPlan(caseId: string, payload: WorkflowPlanUpdatePayload) {
  const response = await api.put<WorkflowPlanRecord>(`/cases/${caseId}/workflow-plan`, payload);
  return response.data;
}

export async function getWorkflowWorkspaceSummary(caseId: string) {
  const response = await api.get<WorkflowWorkspaceSummaryRecord>(`/cases/${caseId}/workflow-plan/summary`);
  return response.data;
}

export async function getPrepWorkspace(caseId: string) {
  const response = await api.get<PrepWorkspaceView>(`/cases/${caseId}/prep-workspace`);
  return response.data;
}

export async function getReviewWorkspace(caseId: string, params: { stage?: string | null; candidate?: string | null } = {}) {
  const response = await api.get<ReviewWorkspaceView>(`/cases/${caseId}/review-workspace`, {
    params: {
      stage: params.stage || undefined,
      candidate: params.candidate || undefined,
    },
  });
  return response.data;
}

export async function getDecisionWorkspace(caseId: string, params: { candidate?: string | null } = {}) {
  const response = await api.get<DecisionWorkspaceView>(`/cases/${caseId}/decision-workspace`, {
    params: {
      candidate: params.candidate || undefined,
    },
  });
  return response.data;
}

export async function addWorkflowStage(caseId: string, payload: WorkflowStageInput) {
  const response = await api.post<WorkflowPlanRecord>(`/cases/${caseId}/workflow-plan/stages`, payload);
  return response.data;
}

export async function updateWorkflowStage(caseId: string, stageId: string, payload: Partial<WorkflowStageInput>) {
  const response = await api.put<WorkflowStageRecord>(`/cases/${caseId}/workflow-plan/stages/${stageId}`, payload);
  return response.data;
}

export async function clearStageOverrides(caseId: string, stageId: string) {
  const response = await api.post<WorkflowStageRecord>(`/cases/${caseId}/workflow-plan/stages/${stageId}/clear-overrides`);
  return response.data;
}

export async function importScreeningQuestions(caseId: string, stageId: string): Promise<{ imported: number; questions: Array<{ number: number; question: string; context: string }> }> {
  const response = await api.post<{ imported: number; questions: Array<{ number: number; question: string; context: string }> }>(
    `/cases/${caseId}/workflow-plan/stages/${stageId}/import-screening-questions`
  );
  return response.data;
}

export async function runWorkflowStage(caseId: string, stageId: string, force = false) {
  const response = await api.post<WorkflowStageRunResultRecord>(`/cases/${caseId}/workflow-plan/stages/${stageId}/run`, { force });
  return response.data;
}

export async function listWorkflowStageCandidates(caseId: string, stageId: string) {
  const response = await api.get<WorkflowStageCandidateRecord[]>(`/cases/${caseId}/workflow-plan/stages/${stageId}/candidates`);
  return response.data;
}

export async function recordWorkflowStageDecision(
  caseId: string,
  stageId: string,
  candidateId: string,
  payload: CandidateStageDecisionPayload,
) {
  const response = await api.post<WorkflowCandidateDossierRecord>(
    `/cases/${caseId}/workflow-plan/stages/${stageId}/candidates/${candidateId}/decision`,
    payload,
  );
  return response.data;
}

export async function createWorkflowStageArtifact(caseId: string, stageId: string, payload: StageArtifactPayload) {
  const response = await api.post<StageArtifactRecord>(`/cases/${caseId}/workflow-plan/stages/${stageId}/artifacts`, payload);
  return response.data;
}

export async function recordNarrativeResponse(caseId: string, stageId: string, candidateId: string, responseText: string) {
  const response = await api.post<StageArtifactRecord>(
    `/cases/${caseId}/workflow-plan/stages/${stageId}/candidates/${candidateId}/response`,
    { response_text: responseText },
  );
  return response.data;
}

export async function resetCandidateNarrativeArtifacts(caseId: string, stageId: string, candidateId: string) {
  await api.delete(`/cases/${caseId}/workflow-plan/stages/${stageId}/candidates/${candidateId}/artifacts`);
}

export async function getWorkflowCandidateDossier(caseId: string, candidateId: string, stageId: string) {
  const response = await api.get<WorkflowCandidateDossierRecord>(`/cases/${caseId}/candidates/${candidateId}/dossier`, {
    params: { stage_id: stageId },
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Ops & security management types
// ---------------------------------------------------------------------------

export interface GlobalAuditEventRecord {
  id: string;
  case_id: string | null;
  actor_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  immutable_hash: string;
  occurred_at: string;
  session_id: string | null;
  source_ip: string | null;
}

export interface GlobalSessionRecord {
  id: string;
  user_id: string;
  username: string;
  email: string;
  display_name: string | null;
  roles: string[];
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
  last_activity_at: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  is_revoked: boolean;
}

export interface FismaControlStatusRecord {
  id: string;
  title: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface AccountStatsRecord {
  total_users: number;
  active_users: number;
  locked_users: number;
  users_without_mfa: number;
  users_with_totp: number;
  users_without_recent_login: number;
}

export interface AuthEvents24hRecord {
  logins: number;
  failed_logins: number;
  lockouts: number;
  password_changes: number;
  mfa_enrollments: number;
}

export interface SecurityPostureRecord {
  fisma_controls: FismaControlStatusRecord[];
  account_stats: AccountStatsRecord;
  auth_events_24h: AuthEvents24hRecord;
  active_sessions: number;
  recent_auth_events: Record<string, unknown>[];
}

export interface ServiceStatusRecord {
  name: string;
  status: "up" | "degraded" | "down";
  latency_ms: number | null;
  detail: string;
}

export interface ServiceHealthRecord {
  services: ServiceStatusRecord[];
  checked_at: string;
}

export interface GlobalAuditQueryParams {
  event_type?: string;
  actor_id?: string;
  source_ip?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Ops & security management API functions
// ---------------------------------------------------------------------------

export async function listGlobalAuditEvents(params: GlobalAuditQueryParams = {}): Promise<{ data: GlobalAuditEventRecord[]; total: number }> {
  const response = await api.get<GlobalAuditEventRecord[]>("/admin/audit-events", { params });
  const total = parseInt(response.headers["x-total-count"] ?? "0", 10);
  return { data: response.data, total };
}

export async function listAllSessions(params: { limit?: number; offset?: number } = {}): Promise<{ data: GlobalSessionRecord[]; total: number }> {
  const response = await api.get<GlobalSessionRecord[]>("/admin/sessions", { params });
  const total = parseInt(response.headers["x-total-count"] ?? "0", 10);
  return { data: response.data, total };
}

export async function revokeSession(sessionId: string): Promise<void> {
  await api.delete(`/admin/sessions/${sessionId}`);
}

export async function getSecurityPosture(): Promise<SecurityPostureRecord> {
  const response = await api.get<SecurityPostureRecord>("/admin/security-posture");
  return response.data;
}

export async function getServiceHealth(): Promise<ServiceHealthRecord> {
  const response = await api.get<ServiceHealthRecord>("/admin/service-health");
  return response.data;
}
