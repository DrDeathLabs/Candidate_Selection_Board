from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import CaseStatus, DataSensitivity
from app.schemas.common import ORMModel, TimestampedResponse


class CaseCreate(BaseModel):
    title: str
    series: str | None = None
    grade: str | None = None
    organization: str | None = None
    hiring_action_type: str | None = None
    certificate_number: str | None = None
    selecting_official: str | None = None
    panel_members: list[dict[str, Any]] = Field(default_factory=list)
    data_sensitivity: DataSensitivity = DataSensitivity.MODERATE
    retention_settings: dict[str, Any] = Field(default_factory=dict)
    model_provider_settings: dict[str, Any] = Field(default_factory=dict)
    outside_enrichment_allowed: bool = False


class CaseRead(TimestampedResponse):
    title: str
    series: str | None
    grade: str | None
    organization: str | None
    hiring_action_type: str | None
    certificate_number: str | None
    selecting_official: str | None
    panel_members: list[dict[str, Any]]
    data_sensitivity: DataSensitivity
    retention_settings: dict[str, Any]
    model_provider_settings: dict[str, Any]
    outside_enrichment_allowed: bool
    status: CaseStatus


class CaseSummary(ORMModel):
    id: UUID
    title: str
    status: CaseStatus
