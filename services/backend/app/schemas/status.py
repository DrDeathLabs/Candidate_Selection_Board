from __future__ import annotations

from pydantic import BaseModel


class DocumentStatusSummary(BaseModel):
    total_documents: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_stage: dict[str, int]
    unreadable_or_flagged: int
