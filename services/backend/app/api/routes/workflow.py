from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import Principal, get_current_principal
from app.db.session import get_db
from app.services.evaluation import EvaluationPipeline, EvaluationRequest
from app.services.expert_council import ExpertCouncilOrchestrator

router = APIRouter()
evaluation_pipeline = EvaluationPipeline()
expert_council = ExpertCouncilOrchestrator()


@router.post("/evaluate")
def queue_evaluation(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, str]:
    return evaluation_pipeline.launch(db, EvaluationRequest(case_id=case_id))


@router.post("/expert-council")
def queue_expert_council(
    case_id: UUID,
    candidate_id: UUID | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    return expert_council.enqueue(db, case_id, candidate_id)
