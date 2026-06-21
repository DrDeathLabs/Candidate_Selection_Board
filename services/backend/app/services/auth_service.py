from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pyotp
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.models.auth import User, UserSession

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def enforce_password_policy(plain: str, user: "User | None" = None) -> None:
    from fastapi import HTTPException
    from fastapi import status as http_status

    s = get_settings()
    if len(plain) < s.password_min_length:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {s.password_min_length} characters.",
        )
    if not any(c.isupper() for c in plain):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, detail="Password must contain an uppercase letter.")
    if not any(c.islower() for c in plain):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, detail="Password must contain a lowercase letter.")
    if not any(c.isdigit() for c in plain):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, detail="Password must contain a digit.")
    special = set("!@#$%^&*()-_=+[]{}|;:,.<>?/")
    if not any(c in special for c in plain):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, detail="Password must contain a special character.")
    if user and user.password_history:
        for old_hash in user.password_history[-s.password_history_count :]:
            if _pwd_context.verify(plain, old_hash):
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    detail="Password was recently used. Choose a different password.",
                )


# ---------------------------------------------------------------------------
# Session utilities
# ---------------------------------------------------------------------------


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_session(
    db: Session,
    user: "User",
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    from app.models.auth import UserSession

    s = get_settings()
    now = datetime.now(timezone.utc)

    # Enforce concurrent session limit — revoke oldest if over the limit
    active_sessions = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user.id,
            UserSession.is_revoked == False,  # noqa: E712
            UserSession.absolute_expires_at > now,
        )
        .order_by(UserSession.created_at.asc())
        .all()
    )
    while len(active_sessions) >= s.max_concurrent_sessions:
        oldest = active_sessions.pop(0)
        oldest.is_revoked = True
        oldest.revoked_at = now
        oldest.revoked_reason = "concurrent_session_limit"

    raw_token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        session_token_hash=_token_hash(raw_token),
        created_at=now,
        absolute_expires_at=now + timedelta(hours=s.session_absolute_timeout_hours),
        idle_expires_at=now + timedelta(minutes=s.session_idle_timeout_minutes),
        last_activity_at=now,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    db.flush()
    return raw_token


def validate_session(db: Session, raw_token: str) -> "tuple[User, UserSession]":
    from fastapi import HTTPException
    from fastapi import status as http_status

    from app.models.auth import UserSession

    now = datetime.now(timezone.utc)
    token_hash = _token_hash(raw_token)
    session = (
        db.query(UserSession)
        .filter(
            UserSession.session_token_hash == token_hash,
            UserSession.is_revoked == False,  # noqa: E712
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")

    if session.absolute_expires_at.replace(tzinfo=timezone.utc) < now:
        session.is_revoked = True
        session.revoked_at = now
        session.revoked_reason = "absolute_timeout"
        db.flush()
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Session expired.")

    idle_expires = session.idle_expires_at
    if idle_expires.tzinfo is None:
        idle_expires = idle_expires.replace(tzinfo=timezone.utc)
    if idle_expires < now:
        session.is_revoked = True
        session.revoked_at = now
        session.revoked_reason = "idle_timeout"
        db.flush()
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Session expired due to inactivity.")

    s = get_settings()
    session.idle_expires_at = now + timedelta(minutes=s.session_idle_timeout_minutes)
    session.last_activity_at = now

    from app.models.auth import User

    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="User account is inactive.")

    return user, session


def revoke_session(db: Session, raw_token: str, reason: str = "logout") -> None:
    from app.models.auth import UserSession

    token_hash = _token_hash(raw_token)
    session = db.query(UserSession).filter(UserSession.session_token_hash == token_hash).first()
    if session:
        session.is_revoked = True
        session.revoked_at = datetime.now(timezone.utc)
        session.revoked_reason = reason
        db.flush()


def revoke_all_user_sessions(db: Session, user_id: object, reason: str = "admin_revoke") -> int:
    from app.models.auth import UserSession

    now = datetime.now(timezone.utc)
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.is_revoked == False)  # noqa: E712
        .all()
    )
    for sess in sessions:
        sess.is_revoked = True
        sess.revoked_at = now
        sess.revoked_reason = reason
    db.flush()
    return len(sessions)


# ---------------------------------------------------------------------------
# Account lockout utilities
# ---------------------------------------------------------------------------


def record_failed_login(db: Session, user: "User") -> None:
    s = get_settings()
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= s.max_failed_login_attempts:
        user.locked_at = datetime.now(timezone.utc)
    db.flush()


def is_account_locked(user: "User") -> bool:
    if not user.locked_at:
        return False
    s = get_settings()
    locked_ts = user.locked_at
    if locked_ts.tzinfo is None:
        locked_ts = locked_ts.replace(tzinfo=timezone.utc)
    lockout_expires = locked_ts + timedelta(minutes=s.account_lockout_minutes)
    if datetime.now(timezone.utc) >= lockout_expires:
        return False
    return True


def unlock_account(db: Session, user: "User") -> None:
    user.locked_at = None
    user.failed_login_count = 0
    db.flush()


# ---------------------------------------------------------------------------
# TOTP utilities
# ---------------------------------------------------------------------------


def _get_fernet_key(key_str: str) -> bytes:
    # Derive a 32-byte key from the config string and encode for Fernet
    raw = hashlib.sha256(key_str.encode()).digest()  # always 32 bytes
    return base64.urlsafe_b64encode(raw)


def setup_totp(user: "User") -> tuple[str, str]:
    """Return (encrypted_secret, provisioning_uri)."""
    from cryptography.fernet import Fernet

    s = get_settings()
    secret = pyotp.random_base32()
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name=s.totp_issuer_name,
    )
    fernet = Fernet(_get_fernet_key(s.totp_encryption_key))
    encrypted = fernet.encrypt(secret.encode()).decode()
    return encrypted, uri


def verify_totp(user: "User", code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    from cryptography.fernet import Fernet, InvalidToken

    s = get_settings()
    fernet = Fernet(_get_fernet_key(s.totp_encryption_key))
    try:
        secret = fernet.decrypt(user.totp_secret_encrypted.encode()).decode()
    except InvalidToken:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def get_totp_uri(user: "User") -> str | None:
    """Return provisioning URI for already-enrolled user (for display)."""
    if not user.totp_secret_encrypted:
        return None
    from cryptography.fernet import Fernet, InvalidToken

    s = get_settings()
    fernet = Fernet(_get_fernet_key(s.totp_encryption_key))
    try:
        secret = fernet.decrypt(user.totp_secret_encrypted.encode()).decode()
    except InvalidToken:
        return None
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=s.totp_issuer_name)
