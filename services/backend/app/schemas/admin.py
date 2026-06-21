from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedResponse


class AdminSettingsRead(BaseModel):
    user: str
    allowed_actions: list[str]


class AIProviderConfig(BaseModel):
    enabled: bool = True
    label: str
    base_url: str
    default_model: str
    api_key_env_var: str = ""
    notes: str = ""


class AISettingsRead(BaseModel):
    default_provider: str
    providers: dict[str, AIProviderConfig]


class AISettingsUpdate(BaseModel):
    default_provider: str
    providers: dict[str, AIProviderConfig]


class ExpertAgentRead(TimestampedResponse):
    agent_type: str
    display_name: str
    description: str
    enabled: bool
    config: dict


class ExpertAgentUpdate(BaseModel):
    display_name: str
    description: str
    enabled: bool
    config: dict = Field(default_factory=dict)


class OperationsOverviewRead(BaseModel):
    active_case_count: int
    case_status_counts: dict[str, int]
    document_status_counts: dict[str, int]
    model_run_status_counts: dict[str, int]
    enabled_agent_count: int
    export_queue_count: int
    default_provider: str


class SecurityOverviewRead(BaseModel):
    sensitivity_counts: dict[str, int]
    outside_enrichment_case_count: int
    audit_event_count_last_24h: int
    admin_change_count_last_24h: int
    provider_secret_dependencies: list[dict]
    checklist: list[dict]


# --- New schemas for ops/security management ---


class GlobalSessionRead(BaseModel):
    id: str
    user_id: str
    username: str
    email: str
    display_name: str | None
    roles: list[str]
    ip_address: str | None
    user_agent: str | None
    created_at: str
    last_activity_at: str
    idle_expires_at: str
    absolute_expires_at: str
    is_revoked: bool


class FismaControlStatus(BaseModel):
    id: str
    title: str
    status: str  # "pass" | "warn" | "fail"
    detail: str


class AccountStatsRead(BaseModel):
    total_users: int
    active_users: int
    locked_users: int
    users_without_mfa: int
    users_with_totp: int
    users_without_recent_login: int


class AuthEvents24hRead(BaseModel):
    logins: int
    failed_logins: int
    lockouts: int
    password_changes: int
    mfa_enrollments: int


class SecurityPostureRead(BaseModel):
    fisma_controls: list[FismaControlStatus]
    account_stats: AccountStatsRead
    auth_events_24h: AuthEvents24hRead
    active_sessions: int
    recent_auth_events: list[dict]


class ServiceStatusRead(BaseModel):
    name: str
    status: str  # "up" | "degraded" | "down"
    latency_ms: float | None
    detail: str


class ServiceHealthRead(BaseModel):
    services: list[ServiceStatusRead]
    checked_at: str
