from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import AdjudicationActionType
from app.schemas.common import TimestampedResponse


class AdjudicationActionCreate(BaseModel):
    action_type: AdjudicationActionType
    rationale: str
    target_candidate_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AdjudicationActionRead(TimestampedResponse):
    actor_id: str
    action_type: str
    target_candidate_id: UUID | None
    payload: dict[str, Any]
    rationale: str
