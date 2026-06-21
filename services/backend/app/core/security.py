from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.enums import RoleName

# Context var carries the current principal across the request lifetime so
# AuditRecorder can auto-populate session_id and source_ip without callers
# having to pass them through explicitly.
_current_principal: ContextVar["Principal | None"] = ContextVar("_current_principal", default=None)


@dataclass(slots=True)
class Principal:
    user_id: str
    display_name: str
    roles: list[RoleName]
    session_id: str | None = field(default=None)
    source_ip: str | None = field(default=None)


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    ) or None


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> Principal:
    from app.core.config import get_settings
    from app.services import auth_service

    settings = get_settings()
    ip = _client_ip(request)

    # 1. Session cookie (primary path for browser clients)
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        user, session = auth_service.validate_session(db, token)
        roles = [RoleName(r) for r in (user.roles or []) if r in RoleName._value2member_map_]
        principal = Principal(
            user_id=str(user.id),
            display_name=user.display_name or user.username,
            roles=roles,
            session_id=str(session.id),
            source_ip=ip,
        )
        _current_principal.set(principal)
        return principal

    # 2. Bearer JWT (OIDC token for service-to-service or API clients)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_jwt = auth_header[7:]
        from app.services.oidc import get_oidc_validator

        try:
            validator = get_oidc_validator()
            claims = validator.validate_id_token(raw_jwt)
            principal = validator.claims_to_principal(claims, db)
            principal.source_ip = ip
            _current_principal.set(principal)
            return principal
        except HTTPException:
            raise

    # 3. Dev bypass (local development only — never enable in production)
    if settings.dev_auth_bypass:
        principal = Principal(
            user_id="local-dev-admin",
            display_name="Local Developer",
            roles=[RoleName.SYSTEM_ADMINISTRATOR, RoleName.CASE_OWNER],
            session_id=None,
            source_ip=ip,
        )
        _current_principal.set(principal)
        return principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(*required_roles: RoleName) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not any(role in principal.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role for this action.",
            )
        return principal

    return dependency
