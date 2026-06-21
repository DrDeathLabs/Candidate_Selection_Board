from __future__ import annotations

from typing import Any

from app.schemas.common import TimestampedResponse


class PositionAnalysisRead(TimestampedResponse):
    case_id: str
    role_type: str | None
    status: str
    duties: list[dict[str, Any]]
    critical_factors: list[dict[str, Any]]
    recommended_dimensions: list[dict[str, Any]]
    evidence_map: dict[str, Any]
