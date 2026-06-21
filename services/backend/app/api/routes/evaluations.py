from __future__ import annotations

from uuid import UUID

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.domain.enums import RoleName
from app.services.review_workflow import ReviewWorkflowService

router = APIRouter()
review_workflow = ReviewWorkflowService()
_settings = get_settings()


def _redis() -> redis_lib.Redis:
    return redis_lib.Redis(
        host=_settings.redis_host,
        port=_settings.redis_port,
        password=_settings.redis_password or None,
        db=2,
        decode_responses=True,
    )


def _stop_key(case_id: UUID) -> str:
    return f"council_stop:{case_id}"


@router.get("/candidates")
def list_candidate_evaluations(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    return review_workflow.list_candidate_evaluations(db, case_id)


@router.get("/facts")
def list_candidate_facts(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    return review_workflow.list_candidate_facts(db, case_id)


@router.get("/expert-reviews")
def list_expert_reviews(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    return review_workflow.list_expert_reviews(db, case_id)


@router.get("/comparisons")
def list_pairwise_comparisons(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    return review_workflow.list_pairwise_comparisons(db, case_id)


@router.get("/interview-questions")
def list_interview_questions(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    return review_workflow.list_interview_questions(db, case_id)


@router.get("/board-meetings")
def list_board_meetings(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> list[dict]:
    return review_workflow.list_board_meetings(db, case_id)


@router.get("/board-meetings/{candidate_id}")
def get_board_meeting(
    case_id: UUID,
    candidate_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    result = review_workflow.get_board_meeting(db, case_id, candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Board meeting not found")
    return result


@router.delete("/board-meetings")
def delete_all_board_meetings(
    case_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> dict:
    deleted = review_workflow.delete_all_board_meetings(db, case_id)
    db.commit()
    return {"deleted": deleted}


@router.delete("/board-meetings/{candidate_id}")
def delete_board_meeting(
    case_id: UUID,
    candidate_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> dict:
    ok = review_workflow.delete_board_meeting(db, case_id, candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Board meeting not found")
    db.commit()
    return {"deleted": 1}


@router.post("/stop-council")
def stop_council(
    case_id: UUID,
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> dict:
    r = _redis()
    r.set(_stop_key(case_id), "1", ex=3600)
    return {"status": "stop_requested", "case_id": str(case_id)}


@router.delete("/stop-council")
def clear_stop_council(
    case_id: UUID,
    principal: Principal = Depends(
        require_roles(RoleName.CASE_OWNER, RoleName.SELECTING_OFFICIAL, RoleName.SYSTEM_ADMINISTRATOR)
    ),
) -> dict:
    r = _redis()
    r.delete(_stop_key(case_id))
    return {"status": "cleared", "case_id": str(case_id)}
