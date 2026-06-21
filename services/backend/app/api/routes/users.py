from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import Principal, require_roles
from app.db.session import get_db
from app.domain.enums import AuditEventType, RoleName
from app.models.auth import User, UserSession
from app.services import auth_service
from app.services.audit import AuditRecorder

router = APIRouter()
audit = AuditRecorder()


class UserRead(BaseModel):
    id: str
    username: str
    email: str
    display_name: str | None
    roles: list[str]
    is_active: bool
    is_mfa_required: bool
    totp_enrolled: bool
    failed_login_count: int
    is_locked: bool
    last_login_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_orm(cls, user: User) -> "UserRead":
        return cls(
            id=str(user.id),
            username=user.username,
            email=user.email,
            display_name=user.display_name,
            roles=user.roles or [],
            is_active=user.is_active,
            is_mfa_required=user.is_mfa_required,
            totp_enrolled=bool(user.totp_secret_encrypted),
            failed_login_count=user.failed_login_count or 0,
            is_locked=auth_service.is_account_locked(user),
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )


class UserCreate(BaseModel):
    username: str
    email: str
    display_name: str | None = None
    password: str
    roles: list[str] = []
    is_mfa_required: bool = True


class UserUpdate(BaseModel):
    email: str | None = None
    display_name: str | None = None
    roles: list[str] | None = None
    is_mfa_required: bool | None = None
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class AdminPasswordResetRequest(BaseModel):
    new_password: str


class SessionRead(BaseModel):
    id: str
    created_at: str
    last_activity_at: str
    ip_address: str | None
    is_revoked: bool


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


# ---------------------------------------------------------------------------
# Admin user management
# ---------------------------------------------------------------------------


@router.get("", response_model=list[UserRead])
def list_users(
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> list[UserRead]:
    total = db.scalar(func.count(User.id)) or 0
    response.headers["X-Total-Count"] = str(total)
    users = db.query(User).order_by(User.username.asc()).offset(offset).limit(limit).all()
    return [UserRead.from_orm(u) for u in users]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> UserRead:
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists.")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")

    auth_service.enforce_password_policy(payload.password)
    user = User(
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        password_hash=auth_service.hash_password(payload.password),
        roles=payload.roles,
        is_mfa_required=payload.is_mfa_required,
        created_by=principal.user_id,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "create_user", "username": user.username, "roles": user.roles},
        source_ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return UserRead.from_orm(user)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> UserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return UserRead.from_orm(user)


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> UserRead:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if payload.email is not None:
        user.email = payload.email
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.roles is not None:
        user.roles = payload.roles
    if payload.is_mfa_required is not None:
        user.is_mfa_required = payload.is_mfa_required
    if payload.is_active is not None:
        user.is_active = payload.is_active
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "update_user", "username": user.username},
        source_ip=_client_ip(request),
    )
    db.commit()
    db.refresh(user)
    return UserRead.from_orm(user)


@router.post("/{user_id}/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = False
    revoked = auth_service.revoke_all_user_sessions(db, user.id, reason="account_disabled")
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "disable_user", "username": user.username, "sessions_revoked": revoked},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = True
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "enable_user", "username": user.username},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/unlock", status_code=status.HTTP_204_NO_CONTENT)
def unlock_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    auth_service.unlock_account(db, user)
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "unlock_user", "username": user.username},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: UUID,
    payload: AdminPasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    auth_service.enforce_password_policy(payload.new_password, user)
    old_hash = user.password_hash
    user.password_hash = auth_service.hash_password(payload.new_password)
    if old_hash:
        history = list(user.password_history or [])
        history.append(old_hash)
        user.password_history = history[-5:]
    auth_service.revoke_all_user_sessions(db, user.id, reason="password_reset")
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.PASSWORD_CHANGED,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "admin_password_reset", "username": user.username},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/sessions", response_model=list[SessionRead])
def list_user_sessions(
    user_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> list[SessionRead]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.is_revoked == False)  # noqa: E712
        .order_by(UserSession.last_activity_at.desc())
        .all()
    )
    return [
        SessionRead(
            id=str(s.id),
            created_at=s.created_at.isoformat(),
            last_activity_at=s.last_activity_at.isoformat(),
            ip_address=s.ip_address,
            is_revoked=s.is_revoked,
        )
        for s in sessions
    ]


@router.delete("/{user_id}/sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_sessions(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_roles(RoleName.SYSTEM_ADMINISTRATOR)),
) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    revoked = auth_service.revoke_all_user_sessions(db, user.id, reason="admin_revoke")
    audit.record(
        db,
        actor_id=principal.user_id,
        event_type=AuditEventType.ADMIN_SETTING_CHANGE,
        entity_type="user",
        entity_id=str(user.id),
        details={"action": "revoke_sessions", "count": revoked},
        source_ip=_client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
