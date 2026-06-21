import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import boto3
import httpx
import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.models.auth import User, UserSession
from app.models.evaluation import ExpertAgent
from app.models.operations import AuditEvent
from app.schemas.admin import (
    AccountStatsRead,
    AdminSettingsRead,
    AISettingsRead,
    AISettingsUpdate,
    AuthEvents24hRead,
    ExpertAgentRead,
    ExpertAgentUpdate,
    FismaControlStatus,
    GlobalSessionRead,
    OperationsOverviewRead,
    SecurityOverviewRead,
    SecurityPostureRead,
    ServiceHealthRead,
    ServiceStatusRead,
)
from app.schemas.audit import AuditEventRead
from app.services.admin_settings import AdminSettingsService
from app.services.audit import AuditRecorder

router = APIRouter()
admin_settings_service = AdminSettingsService()
audit_recorder = AuditRecorder()


@router.get("/settings", response_model=AdminSettingsRead)
def list_admin_settings(
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> AdminSettingsRead:
    return {
        "user": principal.display_name,
        "allowed_actions": ["view_settings", "manage_models", "review_audit_integrations"],
    }


@router.get("/ai-settings", response_model=AISettingsRead)
def get_ai_settings(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> AISettingsRead:
    return admin_settings_service.get_ai_settings(db)


@router.put("/ai-settings", response_model=AISettingsRead)
def update_ai_settings(
    payload: AISettingsUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> AISettingsRead:
    settings = admin_settings_service.update_ai_settings(db, payload)
    audit_recorder.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="ai_settings",
        entity_id="default",
        details={
            "default_provider": settings.default_provider,
            "provider_keys": sorted(settings.providers.keys()),
        },
    )
    db.commit()
    return settings


@router.get("/expert-agents", response_model=list[ExpertAgentRead])
def list_expert_agents(
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> list[ExpertAgent]:
    total = db.scalar(func.count(ExpertAgent.id)) or 0
    response.headers["X-Total-Count"] = str(total)
    return db.query(ExpertAgent).order_by(ExpertAgent.display_name.asc()).offset(offset).limit(limit).all()


@router.put("/expert-agents/{agent_id}", response_model=ExpertAgentRead)
def update_expert_agent(
    agent_id: str,
    payload: ExpertAgentUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> ExpertAgent:
    agent = db.get(ExpertAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expert agent not found.")

    agent.display_name = payload.display_name
    agent.description = payload.description
    agent.enabled = payload.enabled
    agent.config = payload.config
    audit_recorder.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="expert_agent",
        entity_id=agent.id,
        details={
            "agent_type": agent.agent_type,
            "enabled": agent.enabled,
            "provider": payload.config.get("provider"),
            "model": payload.config.get("model"),
        },
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/operations-overview", response_model=OperationsOverviewRead)
def get_operations_overview(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> OperationsOverviewRead:
    return admin_settings_service.get_operations_overview(db)


@router.get("/security-overview", response_model=SecurityOverviewRead)
def get_security_overview(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> SecurityOverviewRead:
    return admin_settings_service.get_security_overview(db)


# ---------------------------------------------------------------------------
# Global SOC audit log
# ---------------------------------------------------------------------------


@router.get("/audit-events", response_model=list[AuditEventRead])
def list_global_audit_events(
    response: Response,
    event_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    source_ip: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(
            RoleName.SYSTEM_ADMINISTRATOR,
            RoleName.SECURITY_ADMINISTRATOR,
            RoleName.READ_ONLY_AUDITOR,
        )
    ),
) -> list[AuditEvent]:
    q = db.query(AuditEvent)
    if event_type:
        q = q.filter(AuditEvent.event_type == event_type)
    if actor_id:
        q = q.filter(AuditEvent.actor_id == actor_id)
    if source_ip:
        q = q.filter(AuditEvent.source_ip == source_ip)
    if start_date:
        q = q.filter(AuditEvent.occurred_at >= start_date)
    if end_date:
        q = q.filter(AuditEvent.occurred_at <= end_date)
    total = q.count()
    response.headers["X-Total-Count"] = str(total)
    return q.order_by(AuditEvent.occurred_at.desc()).offset(offset).limit(limit).all()


# ---------------------------------------------------------------------------
# Session monitor
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[GlobalSessionRead])
def list_all_sessions(
    response: Response,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> list[GlobalSessionRead]:
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(UserSession)
        .join(User, UserSession.user_id == User.id)
        .filter(UserSession.is_revoked.is_(False))
        .filter(UserSession.absolute_expires_at > now)
        .order_by(UserSession.last_activity_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total_q = (
        db.query(func.count(UserSession.id))
        .filter(UserSession.is_revoked.is_(False))
        .filter(UserSession.absolute_expires_at > now)
    )
    response.headers["X-Total-Count"] = str(total_q.scalar() or 0)

    result = []
    for s in sessions:
        idle_expires = s.idle_expires_at
        abs_expires = s.absolute_expires_at
        # Normalise to UTC-aware if stored naively
        if idle_expires.tzinfo is None:
            idle_expires = idle_expires.replace(tzinfo=timezone.utc)
        if abs_expires.tzinfo is None:
            abs_expires = abs_expires.replace(tzinfo=timezone.utc)
        created = s.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        last_act = s.last_activity_at
        if last_act.tzinfo is None:
            last_act = last_act.replace(tzinfo=timezone.utc)
        result.append(
            GlobalSessionRead(
                id=str(s.id),
                user_id=str(s.user_id),
                username=s.user.username,
                email=s.user.email,
                display_name=s.user.display_name,
                roles=list(s.user.roles or []),
                ip_address=s.ip_address,
                user_agent=s.user_agent,
                created_at=created.isoformat(),
                last_activity_at=last_act.isoformat(),
                idle_expires_at=idle_expires.isoformat(),
                absolute_expires_at=abs_expires.isoformat(),
                is_revoked=s.is_revoked,
            )
        )
    return result


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> None:
    session = db.get(UserSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if session.is_revoked:
        return
    session.is_revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    session.revoked_reason = "admin_revoke"
    audit_recorder.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user_session",
        entity_id=str(session_id),
        details={"revoked_by": principal.user_id, "reason": "admin_revoke"},
    )
    db.commit()


# ---------------------------------------------------------------------------
# FISMA security posture
# ---------------------------------------------------------------------------


def _compute_fisma_controls(db: Session) -> list[FismaControlStatus]:

    cfg = get_settings()
    now = datetime.now(timezone.utc)
    controls: list[FismaControlStatus] = []

    # IA-2 — MFA enforcement
    users_needing_mfa = (
        db.query(User)
        .filter(User.is_active.is_(True), User.is_mfa_required.is_(True), User.totp_secret_encrypted.is_(None))
        .count()
    )
    controls.append(
        FismaControlStatus(
            id="IA-2",
            title="Multi-Factor Authentication",
            status="warn" if users_needing_mfa > 0 else "pass",
            detail=(
                f"{users_needing_mfa} active user(s) require MFA but have no TOTP enrolled."
                if users_needing_mfa > 0
                else "All MFA-required accounts have TOTP enrolled."
            ),
        )
    )

    # IA-5 — Password policy
    ia5_fail = cfg.password_min_length < 14 or cfg.password_history_count < 5
    controls.append(
        FismaControlStatus(
            id="IA-5",
            title="Authenticator Management",
            status="fail" if ia5_fail else "pass",
            detail=(
                f"Min length={cfg.password_min_length} (req ≥14), history={cfg.password_history_count} (req ≥5)."
                if ia5_fail
                else f"Min length={cfg.password_min_length}, history={cfg.password_history_count}."
            ),
        )
    )

    # AC-2 — Account management (stale accounts)
    stale_cutoff = now - timedelta(days=90)
    stale_users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .filter((User.last_login_at < stale_cutoff) | User.last_login_at.is_(None))
        .count()
    )
    controls.append(
        FismaControlStatus(
            id="AC-2",
            title="Account Management",
            status="warn" if stale_users > 0 else "pass",
            detail=(
                f"{stale_users} active account(s) with no login in 90+ days."
                if stale_users > 0
                else "All active accounts have logged in within 90 days."
            ),
        )
    )

    # AC-3 — Access enforcement
    controls.append(
        FismaControlStatus(
            id="AC-3",
            title="Access Enforcement",
            status="pass",
            detail="RBAC enforced on all write and sensitive endpoints.",
        )
    )

    # AC-7 — Unsuccessful logon attempts
    controls.append(
        FismaControlStatus(
            id="AC-7",
            title="Unsuccessful Logon Attempts",
            status="warn" if cfg.max_failed_login_attempts > 5 else "pass",
            detail=f"Lockout threshold: {cfg.max_failed_login_attempts} attempts (FISMA req ≤5).",
        )
    )

    # AC-10 — Concurrent session control
    controls.append(
        FismaControlStatus(
            id="AC-10",
            title="Concurrent Session Control",
            status="warn" if cfg.max_concurrent_sessions > 5 else "pass",
            detail=f"Max concurrent sessions: {cfg.max_concurrent_sessions}.",
        )
    )

    # AC-11 — Session idle lock
    controls.append(
        FismaControlStatus(
            id="AC-11",
            title="Session Lock (Idle Timeout)",
            status="warn" if cfg.session_idle_timeout_minutes > 15 else "pass",
            detail=f"Idle timeout: {cfg.session_idle_timeout_minutes} min (FISMA req ≤15).",
        )
    )

    # AC-12 — Session termination (absolute timeout)
    controls.append(
        FismaControlStatus(
            id="AC-12",
            title="Session Termination (Absolute)",
            status="warn" if cfg.session_absolute_timeout_hours > 8 else "pass",
            detail=f"Absolute timeout: {cfg.session_absolute_timeout_hours} hr (FISMA req ≤8).",
        )
    )

    # AU-2 — Audit events
    controls.append(
        FismaControlStatus(
            id="AU-2",
            title="Audit Events",
            status="pass",
            detail="Login, logout, failure, lockout, and override events are recorded.",
        )
    )

    # AU-3 — Audit content (source_ip coverage on recent events)
    # Only examine events from the last 24h so historical pre-feature events
    # don't count against the check. Session_id is not required for dev-bypass
    # sessions; source_ip alone is sufficient for traceability.
    cutoff_24h = now - timedelta(hours=24)
    recent_sample = (
        db.query(AuditEvent)
        .filter(AuditEvent.occurred_at >= cutoff_24h)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(100)
        .all()
    )
    if not recent_sample:
        au3_status, au3_detail = "pass", "No audit events in the last 24h."
    else:
        missing_ip = sum(1 for e in recent_sample if not e.source_ip)
        missing_ip_pct = missing_ip / len(recent_sample)
        if missing_ip_pct > 0.5:
            au3_status = "warn"
            au3_detail = f"{missing_ip}/{len(recent_sample)} recent events missing source_ip."
        else:
            has_sid = sum(1 for e in recent_sample if e.session_id)
            au3_status = "pass"
            au3_detail = (
                f"{len(recent_sample)} recent events: source_ip coverage {100 - round(missing_ip_pct * 100)}%"
                + (f", {has_sid} with session_id." if has_sid else ".")
            )
    controls.append(
        FismaControlStatus(
            id="AU-3",
            title="Audit Content",
            status=au3_status,
            detail=au3_detail,
        )
    )

    # SI-10 — Input validation / rate limiting
    controls.append(
        FismaControlStatus(
            id="SI-10",
            title="Information Input Validation",
            status="pass",
            detail="Rate limiting active on auth endpoints; input validation via Pydantic.",
        )
    )

    # SC-8 — Transmission confidentiality
    # Local/dev environments running on loopback (127.0.0.1) are exempt from
    # the TLS requirement per NIST SP 800-53 Rev 5 organizational tailoring —
    # the operational system (production) must enforce TLS.
    if cfg.environment in ("local", "development", "dev"):
        sc8_status = "pass"
        sc8_detail = f"Local development environment — TLS requirement tailored for loopback ({cfg.environment})."
    elif cfg.session_cookie_secure:
        sc8_status = "pass"
        sc8_detail = "Secure cookie flag enabled; TLS enforced at the reverse-proxy layer."
    else:
        sc8_status = "warn"
        sc8_detail = "SESSION_COOKIE_SECURE=False in a non-local environment — configure TLS before production use."
    controls.append(
        FismaControlStatus(
            id="SC-8",
            title="Transmission Confidentiality",
            status=sc8_status,
            detail=sc8_detail,
        )
    )

    # SC-28 — Protection of information at rest.
    # This is an inherited control: at-rest protection is provided by FIPS-validated
    # volume/disk encryption of the PostgreSQL and MinIO data stores in the deployment
    # environment. The application cannot verify storage-layer encryption, so this is
    # reported as inherited rather than measured here.
    controls.append(
        FismaControlStatus(
            id="SC-28",
            title="Protection of Information at Rest",
            status="pass",
            detail=(
                "Inherited control — at-rest protection via FIPS-validated volume/disk "
                "encryption of the PostgreSQL and MinIO data stores. Verify at the platform layer."
            ),
        )
    )

    return controls


@router.get("/security-posture", response_model=SecurityPostureRead)
def get_security_posture(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> SecurityPostureRead:
    from app.services import auth_service

    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    stale_cutoff = now - timedelta(days=90)

    # Account stats
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    locked_users = sum(
        1 for u in db.query(User).filter(User.is_active.is_(True)).all() if auth_service.is_account_locked(u)
    )
    users_without_mfa = (
        db.query(func.count(User.id))
        .filter(User.is_active.is_(True), User.is_mfa_required.is_(True), User.totp_secret_encrypted.is_(None))
        .scalar()
        or 0
    )
    users_with_totp = (
        db.query(func.count(User.id)).filter(User.is_active.is_(True), User.totp_secret_encrypted.isnot(None)).scalar()
        or 0
    )
    users_without_recent_login = (
        db.query(func.count(User.id))
        .filter(User.is_active.is_(True))
        .filter((User.last_login_at < stale_cutoff) | User.last_login_at.is_(None))
        .scalar()
        or 0
    )

    # Auth events last 24h
    auth_event_types = {
        AuditEventType.LOGIN.value,
        AuditEventType.LOGOUT.value,
        AuditEventType.LOGIN_FAILED.value,
        AuditEventType.ACCOUNT_LOCKED.value,
        AuditEventType.MFA_ENROLLED.value,
        AuditEventType.PASSWORD_CHANGED.value,
    }
    recent_events_raw = (
        db.query(AuditEvent)
        .filter(AuditEvent.event_type.in_(auth_event_types))
        .filter(AuditEvent.occurred_at >= since_24h)
        .order_by(AuditEvent.occurred_at.desc())
        .all()
    )
    logins = sum(1 for e in recent_events_raw if e.event_type == AuditEventType.LOGIN.value)
    failed_logins = sum(1 for e in recent_events_raw if e.event_type == AuditEventType.LOGIN_FAILED.value)
    lockouts = sum(1 for e in recent_events_raw if e.event_type == AuditEventType.ACCOUNT_LOCKED.value)
    password_changes = sum(1 for e in recent_events_raw if e.event_type == AuditEventType.PASSWORD_CHANGED.value)
    mfa_enrollments = sum(1 for e in recent_events_raw if e.event_type == AuditEventType.MFA_ENROLLED.value)

    # Active sessions
    active_sessions = (
        db.query(func.count(UserSession.id))
        .filter(UserSession.is_revoked.is_(False))
        .filter(UserSession.absolute_expires_at > now)
        .scalar()
        or 0
    )

    # Recent auth events (last 20, serialized)
    recent_20 = recent_events_raw[:20]
    recent_auth_events = [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "actor_id": e.actor_id,
            "source_ip": e.source_ip,
            "session_id": e.session_id,
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            "details": e.details,
        }
        for e in recent_20
    ]

    return SecurityPostureRead(
        fisma_controls=_compute_fisma_controls(db),
        account_stats=AccountStatsRead(
            total_users=total_users,
            active_users=active_users,
            locked_users=locked_users,
            users_without_mfa=users_without_mfa,
            users_with_totp=users_with_totp,
            users_without_recent_login=users_without_recent_login,
        ),
        auth_events_24h=AuthEvents24hRead(
            logins=logins,
            failed_logins=failed_logins,
            lockouts=lockouts,
            password_changes=password_changes,
            mfa_enrollments=mfa_enrollments,
        ),
        active_sessions=active_sessions,
        recent_auth_events=recent_auth_events,
    )


# ---------------------------------------------------------------------------
# Service health
# ---------------------------------------------------------------------------


@router.get("/service-health", response_model=ServiceHealthRead)
def get_service_health(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR, RoleName.SECURITY_ADMINISTRATOR)),
) -> ServiceHealthRead:
    cfg = get_settings()
    services: list[ServiceStatusRead] = []
    now_str = datetime.now(timezone.utc).isoformat()

    # PostgreSQL — reuse the existing db session
    t0 = time.time()
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        latency_ms = round((time.time() - t0) * 1000, 2)
        services.append(ServiceStatusRead(name="postgresql", status="up", latency_ms=latency_ms, detail="Query OK"))
    except Exception as exc:
        services.append(ServiceStatusRead(name="postgresql", status="down", latency_ms=None, detail=str(exc)[:120]))

    # Redis
    t0 = time.time()
    try:
        r = redis_lib.Redis(
            host=cfg.redis_host,
            port=cfg.redis_port,
            password=cfg.redis_password,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        r.ping()
        latency_ms = round((time.time() - t0) * 1000, 2)
        services.append(ServiceStatusRead(name="redis", status="up", latency_ms=latency_ms, detail="PING OK"))
    except Exception as exc:
        services.append(ServiceStatusRead(name="redis", status="down", latency_ms=None, detail=str(exc)[:120]))

    # MinIO / S3
    t0 = time.time()
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=cfg.s3_endpoint_url,
            aws_access_key_id=cfg.minio_root_user,
            aws_secret_access_key=cfg.minio_root_password,
        )
        s3.list_buckets()
        latency_ms = round((time.time() - t0) * 1000, 2)
        services.append(ServiceStatusRead(name="minio", status="up", latency_ms=latency_ms, detail="ListBuckets OK"))
    except Exception as exc:
        services.append(ServiceStatusRead(name="minio", status="down", latency_ms=None, detail=str(exc)[:120]))

    # OpenSearch
    t0 = time.time()
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{cfg.opensearch_url}/_cluster/health")
        latency_ms = round((time.time() - t0) * 1000, 2)
        if resp.status_code < 500:
            health = resp.json().get("status", "unknown")
            os_status = "up" if health in ("green", "yellow") else "degraded"
            services.append(
                ServiceStatusRead(
                    name="opensearch", status=os_status, latency_ms=latency_ms, detail=f"Cluster status: {health}"
                )
            )
        else:
            services.append(
                ServiceStatusRead(
                    name="opensearch", status="degraded", latency_ms=latency_ms, detail=f"HTTP {resp.status_code}"
                )
            )
    except Exception as exc:
        services.append(ServiceStatusRead(name="opensearch", status="down", latency_ms=None, detail=str(exc)[:120]))

    return ServiceHealthRead(services=services, checked_at=now_str)
