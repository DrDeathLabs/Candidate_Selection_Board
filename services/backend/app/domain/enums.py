from enum import StrEnum


class RoleName(StrEnum):
    SYSTEM_ADMINISTRATOR = "system_administrator"
    CASE_OWNER = "case_owner"
    SELECTING_OFFICIAL = "selecting_official"
    PANEL_REVIEWER = "panel_reviewer"
    HR_REVIEWER = "hr_reviewer"
    READ_ONLY_AUDITOR = "read_only_auditor"
    SECURITY_ADMINISTRATOR = "security_administrator"


class CaseStatus(StrEnum):
    DRAFT = "draft"
    INTAKE = "intake"
    REVIEW = "review"
    SLATE = "slate"
    SELECTION = "selection"
    CLOSED = "closed"


class DataSensitivity(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class DocumentType(StrEnum):
    POSITION_DESCRIPTION = "position_description"
    VACANCY_ANNOUNCEMENT = "vacancy_announcement"
    CERTIFICATE = "certificate"
    RESUME_BUNDLE = "resume_bundle"
    RESUME = "resume"
    TRANSCRIPT = "transcript"
    CERTIFICATION = "certification"
    INTERVIEW_NOTES = "interview_notes"
    OTHER = "other"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class CandidateDisposition(StrEnum):
    UNDER_REVIEW = "under_review"
    INTERVIEW_SLATE = "interview_slate"
    SELECTEE = "selectee"
    ALTERNATE = "alternate"
    DISCARDED = "discarded"


class RubricStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    LOCKED = "locked"


class RatingValue(StrEnum):
    EXCEEDS = "exceeds"
    MEETS = "meets"
    PARTIAL = "partial"
    DOES_NOT_MEET = "does_not_meet"
    UNSUPPORTED = "unsupported"


class ExpertAgentType(StrEnum):
    PD_ANALYST = "pd_analyst"
    RESUME_EVIDENCE_ANALYST = "resume_evidence_analyst"
    SUPERVISORY_EXPERT = "supervisory_expert"
    TECHNICAL_DOMAIN_EXPERT = "technical_domain_expert"
    MISSION_ALIGNMENT_EXPERT = "mission_alignment_expert"
    BUDGET_AND_ACQUISITION_EXPERT = "budget_and_acquisition_expert"
    CYBERSECURITY_EXPERT = "cybersecurity_expert"
    OPERATIONS_EXPERT = "operations_expert"
    MODERNIZATION_EXPERT = "modernization_expert"
    SKEPTIC_REVIEWER = "skeptic_reviewer"
    COMPLIANCE_REVIEWER = "compliance_reviewer"
    COMPARATIVE_REVIEWER = "comparative_reviewer"
    SELECTION_REVIEWER = "selection_reviewer"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RecommendationStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    FINALIZED = "finalized"


class AdjudicationActionType(StrEnum):
    PROMOTE_CANDIDATE = "promote_candidate"
    DEMOTE_CANDIDATE = "demote_candidate"
    DISCARD_CANDIDATE = "discard_candidate"
    RESTORE_CANDIDATE = "restore_candidate"
    OVERRIDE_RATING = "override_rating"
    EDIT_RUBRIC_WEIGHT = "edit_rubric_weight"
    ACCEPT_RECOMMENDATION = "accept_recommendation"
    REJECT_RECOMMENDATION = "reject_recommendation"
    LOCK_SLATE = "lock_slate"
    LOCK_SELECTEE = "lock_selectee"


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class AuditEventType(StrEnum):
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    ACCOUNT_LOCKED = "account_locked"
    PASSWORD_CHANGED = "password_changed"
    MFA_ENROLLED = "mfa_enrolled"
    FILE_UPLOAD = "file_upload"
    FILE_VIEW = "file_view"
    FILE_DELETION = "file_deletion"
    CASE_CREATION = "case_creation"
    CASE_DELETION = "case_deletion"
    RUBRIC_CHANGE = "rubric_change"
    CANDIDATE_MATCH_CHANGE = "candidate_match_change"
    MODEL_RUN = "model_run"
    EXPERT_REVIEW = "expert_review"
    RATING_GENERATION = "rating_generation"
    RATING_OVERRIDE = "rating_override"
    TIER_MOVEMENT = "tier_movement"
    SELECTION_RECOMMENDATION = "selection_recommendation"
    ADJUDICATION_ACTION = "adjudication_action"
    EXPORT_GENERATION = "export_generation"
    EXPORT_DOWNLOAD = "export_download"
    ADMIN_SETTING_CHANGE = "admin_setting_change"


class ModelRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
