from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PromptTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prompt_templates"

    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(128))
    template_body: Mapped[str] = mapped_column(Text)
    expected_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)


class ModelRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_runs"

    case_id = mapped_column(ForeignKey("review_cases.id", ondelete="SET NULL"), nullable=True)
    candidate_id = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    prompt_template_id = mapped_column(ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(128))
    request_purpose: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class SystemSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(String(128), unique=True)
    setting_value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    classification: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
