from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AdjudicationAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "adjudication_actions"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    actor_id: Mapped[str] = mapped_column(String(255))
    action_type: Mapped[str] = mapped_column(String(64))
    target_candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    rationale: Mapped[str] = mapped_column(Text)


class ExportPackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "export_packages"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="CASCADE"))
    export_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str | None] = mapped_column(String(512))
    requested_by: Mapped[str] = mapped_column(String(255))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="SET NULL"), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(128))
    entity_id: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    immutable_hash: Mapped[str] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
