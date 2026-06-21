from __future__ import annotations

import base64
import hashlib
import secrets
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Principal, get_current_principal
from app.db.session import get_db
from app.domain.enums import AuditEventType
from app.models.auth import User
from app.services import auth_service
from app.services.audit import AuditRecorder
from app.services.oidc import is_placeholder_oidc_issuer

router = APIRouter()
audit = AuditRecorder()
_limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class TOTPLoginRequest(BaseModel):
    pending_token: str
    totp_code: str


class LoginResponse(BaseModel):
    mfa_required: bool
    pending_token: str | None = None
    user_id: str | None = None
    display_name: str | None = None
    roles: list[str] | None = None
    csrf_token: str | None = None


class MeResponse(BaseModel):
    user_id: str
    username: str
    email: str
    display_name: str | None
    roles: list[str]
    is_mfa_required: bool
    totp_enrolled: bool
    last_login_at: str | None


class TOTPSetupResponse(BaseModel):
    provisioning_uri: str
    pending_secret_ref: str  # encrypted secret — must be confirmed before saving


class TOTPConfirmRequest(BaseModel):
    pending_secret_ref: str
    totp_code: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_session_cookie(response: Response, raw_token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name,
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=s.session_cookie_secure,
        path="/",
        max_age=s.session_absolute_timeout_hours * 3600,
    )


def _set_csrf_cookie(response: Response) -> str:
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key="sb_csrf",
        value=csrf_token,
        httponly=False,  # must be readable by JS to set header
        samesite="strict",
        secure=get_settings().session_cookie_secure,
        path="/",
    )
    return csrf_token


def _clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(key=s.session_cookie_name, path="/")
    response.delete_cookie(key="sb_csrf", path="/")


def _get_redis():
    import redis as redis_lib

    s = get_settings()
    return redis_lib.Redis(
        host=s.redis_host,
        port=s.redis_port,
        password=s.redis_password or None,
        db=4,
        decode_responses=True,
    )


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


# ---------------------------------------------------------------------------
# Login — step 1: username + password
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
@_limiter.limit("10/minute")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    from app.services import auth_service as svc

    user = db.query(User).filter((User.username == payload.username) | (User.email == payload.username)).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

    if svc.is_account_locked(user):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is locked. Try again later or contact an administrator.",
        )

    if not svc.verify_password(payload.password, user.password_hash):
        svc.record_failed_login(db, user)
        if svc.is_account_locked(user):
            audit.record(
                db,
                actor_id=str(user.id),
                event_type=AuditEventType.ACCOUNT_LOCKED,
                entity_type="user",
                entity_id=str(user.id),
                details={"username": user.username, "failed_attempts": user.failed_login_count},
                source_ip=_client_ip(request),
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account locked due to too many failed attempts.",
            )
        audit.record(
            db,
            actor_id=str(user.id),
            event_type=AuditEventType.LOGIN_FAILED,
            entity_type="user",
            entity_id=str(user.id),
            details={"username": user.username, "failed_count": user.failed_login_count},
            source_ip=_client_ip(request),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    # Reset failed counter on successful password verification
    user.failed_login_count = 0
    db.flush()

    # MFA required?
    if user.is_mfa_required and user.totp_secret_encrypted:
        # Issue a short-lived pending token — full session created after TOTP
        pending_token = secrets.token_urlsafe(24)
        redis = _get_redis()
        redis.setex(f"mfa_pending:{pending_token}", 300, str(user.id))
        db.commit()
        return LoginResponse(mfa_required=True, pending_token=pending_token)

    # No MFA — create session immediately
    raw_token = svc.create_session(
        db, user, ip_address=_client_ip(request), user_agent=request.headers.get("User-Agent")
    )
    user.last_login_at = datetime.now(timezone.utc)
    audit.record(
        db,
        actor_id=str(user.id),
        event_type=AuditEventType.LOGIN,
        entity_type="user",
        entity_id=str(user.id),
        details={"username": user.username, "method": "password"},
        source_ip=_client_ip(request),
    )
    db.commit()

    _set_session_cookie(response, raw_token)
    csrf_token = _set_csrf_cookie(response)
    return LoginResponse(
        mfa_required=False,
        user_id=str(user.id),
        display_name=user.display_name or user.username,
        roles=user.roles or [],
        csrf_token=csrf_token,
    )


# ---------------------------------------------------------------------------
# Login — step 2: TOTP verification
# ---------------------------------------------------------------------------


@router.post("/login/totp", response_model=LoginResponse)
def login_totp(
    payload: TOTPLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    redis = _get_redis()
    user_id_str = redis.get(f"mfa_pending:{payload.pending_token}")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA challenge expired or invalid.")

    from uuid import UUID

    user = db.get(User, UUID(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    if not auth_service.verify_totp(user, payload.totp_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code.")

    redis.delete(f"mfa_pending:{payload.pending_token}")

    raw_token = auth_service.create_session(
        db, user, ip_address=_client_ip(request), user_agent=request.headers.get("User-Agent")
    )
    user.last_login_at = datetime.now(timezone.utc)
    audit.record(
        db,
        actor_id=str(user.id),
        event_type=AuditEventType.LOGIN,
        entity_type="user",
        entity_id=str(user.id),
        details={"username": user.username, "method": "password+totp"},
        source_ip=_client_ip(request),
    )
    db.commit()

    _set_session_cookie(response, raw_token)
    csrf_token = _set_csrf_cookie(response)
    return LoginResponse(
        mfa_required=False,
        user_id=str(user.id),
        display_name=user.display_name or user.username,
        roles=user.roles or [],
        csrf_token=csrf_token,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    s = get_settings()
    raw_token = request.cookies.get(s.session_cookie_name)
    if raw_token:
        auth_service.revoke_session(db, raw_token, reason="logout")
        db.commit()
    _clear_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------


@router.get("/me", response_model=MeResponse)
def get_me(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> MeResponse:
    # Dev bypass principal has a non-UUID user_id
    user = None
    try:
        from uuid import UUID as _UUID

        uid = _UUID(principal.user_id)
        user = db.query(User).filter(User.id == uid).first()
    except ValueError:
        pass
    if not user:
        # dev bypass returns synthetic principal
        return MeResponse(
            user_id=principal.user_id,
            username=principal.user_id,
            email="",
            display_name=principal.display_name,
            roles=[r.value for r in principal.roles],
            is_mfa_required=False,
            totp_enrolled=False,
            last_login_at=None,
        )
    return MeResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        roles=user.roles or [],
        is_mfa_required=user.is_mfa_required,
        totp_enrolled=bool(user.totp_secret_encrypted),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


# ---------------------------------------------------------------------------
# TOTP setup and enrollment
# ---------------------------------------------------------------------------


@router.post("/totp/setup", response_model=TOTPSetupResponse)
def totp_setup(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> TOTPSetupResponse:
    user = db.query(User).filter(User.id == principal.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    encrypted_secret, uri = auth_service.setup_totp(user)
    # Don't save yet — return encrypted secret ref so client can confirm first
    return TOTPSetupResponse(provisioning_uri=uri, pending_secret_ref=encrypted_secret)


@router.post("/totp/confirm", status_code=status.HTTP_204_NO_CONTENT)
def totp_confirm(
    payload: TOTPConfirmRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Response:
    user = db.query(User).filter(User.id == principal.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Temporarily assign the pending secret to verify the code
    original = user.totp_secret_encrypted
    user.totp_secret_encrypted = payload.pending_secret_ref
    if not auth_service.verify_totp(user, payload.totp_code):
        user.totp_secret_encrypted = original
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code.")

    # Code verified — persist the secret
    db.flush()
    audit.record(
        db,
        actor_id=str(user.id),
        event_type=AuditEventType.MFA_ENROLLED,
        entity_type="user",
        entity_id=str(user.id),
        details={"username": user.username},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# OIDC redirect flow
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Self-service password change
# ---------------------------------------------------------------------------


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Response:
    user = db.query(User).filter(User.id == principal.user_id).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password change not available for this account."
        )
    if not auth_service.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")
    auth_service.enforce_password_policy(payload.new_password, user)
    old_hash = user.password_hash
    user.password_hash = auth_service.hash_password(payload.new_password)
    history = list(user.password_history or [])
    history.append(old_hash)
    user.password_history = history[-5:]
    user.last_password_change_at = datetime.now(timezone.utc)
    auth_service.revoke_all_user_sessions(db, user.id, reason="password_changed")
    audit.record(
        db,
        actor_id=str(user.id),
        event_type=AuditEventType.PASSWORD_CHANGED,
        entity_type="user",
        entity_id=str(user.id),
        details={"username": user.username, "method": "self_service"},
        source_ip=_client_ip(request),
    )
    db.commit()
    _clear_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# OIDC redirect flow
# ---------------------------------------------------------------------------


@router.get("/oidc/login")
def oidc_login(request: Request, response: Response) -> Any:
    from fastapi.responses import RedirectResponse

    s = get_settings()
    if is_placeholder_oidc_issuer(s.oidc_issuer_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC provider is not configured.",
        )

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()

    redis = _get_redis()
    redis.setex(f"oidc_state:{state}", 600, f"{code_verifier}:{nonce}")

    redirect_uri = f"{s.oidc_redirect_base_url}/api/v1/auth/oidc/callback"
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": s.oidc_audience,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile groups",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    auth_url = f"{s.oidc_issuer_url}/authorize?{params}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/oidc/callback")
def oidc_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Any:
    from fastapi.responses import RedirectResponse

    redis = _get_redis()
    stored = redis.get(f"oidc_state:{state}")
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired state parameter.")
    redis.delete(f"oidc_state:{state}")
    code_verifier, nonce = stored.split(":", 1)

    s = get_settings()
    redirect_uri = f"{s.oidc_redirect_base_url}/api/v1/auth/oidc/callback"

    # Exchange code for tokens
    import httpx as _httpx

    token_url = f"{s.oidc_issuer_url}/token"
    try:
        token_resp = _httpx.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": s.oidc_audience,
                "code_verifier": code_verifier,
            },
            timeout=15,
        )
        token_resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Token exchange failed: {exc}") from exc

    id_token = token_resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No id_token in provider response.")

    from app.services.oidc import get_oidc_validator

    validator = get_oidc_validator()
    claims = validator.validate_id_token(id_token)
    principal = validator.claims_to_principal(claims, db)

    user = db.query(User).filter(User.id == principal.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="User provisioning failed.")

    raw_token = auth_service.create_session(
        db, user, ip_address=_client_ip(request), user_agent=request.headers.get("User-Agent")
    )
    user.last_login_at = datetime.now(timezone.utc)
    audit.record(
        db,
        actor_id=str(user.id),
        event_type=AuditEventType.LOGIN,
        entity_type="user",
        entity_id=str(user.id),
        details={"username": user.username, "method": "oidc"},
        source_ip=_client_ip(request),
    )
    db.commit()

    resp = RedirectResponse(url="/engagements", status_code=302)
    _set_session_cookie(resp, raw_token)
    _set_csrf_cookie(resp)
    return resp
