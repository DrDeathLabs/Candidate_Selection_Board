from __future__ import annotations

import time
from typing import Any

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings


class OIDCValidator:
    """Validates OIDC ID tokens via JWKS and maps group claims to internal roles."""

    def __init__(self) -> None:
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0.0
        _TTL = 3600.0

    def _fetch_jwks(self) -> dict:
        s = get_settings()
        now = time.time()
        if self._jwks is not None and now - self._jwks_fetched_at < 3600.0:
            return self._jwks
        try:
            response = httpx.get(s.oidc_jwks_url, timeout=10)
            response.raise_for_status()
            self._jwks = response.json()
            self._jwks_fetched_at = now
            return self._jwks
        except Exception:
            if self._jwks is not None:
                return self._jwks
            raise

    def validate_id_token(self, raw_jwt: str) -> dict[str, Any]:
        from fastapi import HTTPException, status

        s = get_settings()
        # Skip validation entirely if using the dev placeholder issuer
        if "login.example.gov" in s.oidc_issuer_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OIDC provider not configured. Set OIDC_ISSUER_URL, OIDC_AUDIENCE, and OIDC_JWKS_URL.",
            )
        try:
            jwks = self._fetch_jwks()
            claims = jwt.decode(
                raw_jwt,
                jwks,
                algorithms=["RS256"],
                audience=s.oidc_audience,
                issuer=s.oidc_issuer_url,
            )
            return claims
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid JWT: {exc}",
            ) from exc

    def claims_to_principal(self, claims: dict[str, Any], db: Session) -> Any:
        from app.core.security import Principal
        from app.domain.enums import RoleName
        from app.models.auth import User

        sub = claims.get("sub", "")
        email = claims.get("email", "")
        name = claims.get("name") or claims.get("preferred_username") or email

        groups: list[str] = claims.get("groups", []) or claims.get("roles", [])
        s = get_settings()
        prefix = s.oidc_group_prefix
        role_map = {
            f"{prefix}admin": RoleName.SYSTEM_ADMINISTRATOR,
            f"{prefix}case-owner": RoleName.CASE_OWNER,
            f"{prefix}selecting": RoleName.SELECTING_OFFICIAL,
            f"{prefix}reviewer": RoleName.PANEL_REVIEWER,
            f"{prefix}hr": RoleName.HR_REVIEWER,
            f"{prefix}auditor": RoleName.READ_ONLY_AUDITOR,
            f"{prefix}security": RoleName.SECURITY_ADMINISTRATOR,
        }
        roles = [role_map[g] for g in groups if g in role_map]
        if not roles:
            roles = [RoleName.PANEL_REVIEWER]

        user = db.query(User).filter(User.oidc_sub == sub).first()
        if user is None and email:
            user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                username=email or sub,
                email=email or f"{sub}@oidc.local",
                display_name=str(name),
                oidc_sub=sub,
                roles=[r.value for r in roles],
                is_active=True,
                is_mfa_required=False,
            )
            db.add(user)
            db.flush()
        else:
            if not user.oidc_sub:
                user.oidc_sub = sub
            user.roles = [r.value for r in roles]
            db.flush()

        return Principal(user_id=str(user.id), display_name=str(name) or sub, roles=roles)


_oidc_validator = OIDCValidator()


def get_oidc_validator() -> OIDCValidator:
    return _oidc_validator
