from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import Rubric
from app.tasks.document_pipeline import evaluate_case


@dataclass(slots=True)
class EvaluationRequest:
    case_id: UUID
    candidate_id: UUID | None = None
    mode: str = "review"


class EvaluationPipeline:
    def launch(self, db: Session, request: EvaluationRequest) -> dict[str, str]:
        if not db.scalar(select(Rubric.id).where(Rubric.case_id == request.case_id)):
            raise HTTPException(status_code=400, detail="Create and lock a rubric before running candidate evaluation.")
        task = evaluate_case.delay(str(request.case_id))
        return {
            "case_id": str(request.case_id),
            "candidate_id": str(request.candidate_id) if request.candidate_id else "",
            "mode": request.mode,
            "status": "queued",
            "task_id": task.id,
        }
