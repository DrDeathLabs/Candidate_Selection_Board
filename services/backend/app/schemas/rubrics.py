from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedResponse


class RubricDimensionCreate(BaseModel):
    title: str
    description: str
    weight: Decimal
    order_index: int
    evidence_links: list[dict] = Field(default_factory=list)
    is_locked: bool = False


class RubricCreate(BaseModel):
    name: str
    position_analysis_id: UUID | None = None
    dimensions: list[RubricDimensionCreate] = Field(default_factory=list)


class RubricUpdate(BaseModel):
    name: str
    status: str | None = None
    is_locked: bool = False
    dimensions: list[RubricDimensionCreate] = Field(default_factory=list)


class RubricLockRequest(BaseModel):
    is_locked: bool


class RubricDimensionRead(TimestampedResponse):
    title: str
    description: str
    weight: Decimal
    order_index: int
    evidence_links: list[dict]
    is_locked: bool


class RubricRead(TimestampedResponse):
    name: str
    status: str
    version: int
    is_locked: bool
    total_weight: Decimal
    dimensions: list[RubricDimensionRead]
