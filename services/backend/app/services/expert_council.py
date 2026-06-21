from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ExpertAgentType
from app.models.case import Rubric
from app.models.evaluation import ExpertAgent
from app.tasks.document_pipeline import run_expert_council


@dataclass(slots=True)
class ExpertCouncilRunPlan:
    case_id: UUID
    candidate_id: UUID | None
    agents: list[ExpertAgentType]


class ExpertCouncilOrchestrator:
    default_agents = [
        ExpertAgentType.PD_ANALYST,
        ExpertAgentType.RESUME_EVIDENCE_ANALYST,
        ExpertAgentType.SUPERVISORY_EXPERT,
        ExpertAgentType.TECHNICAL_DOMAIN_EXPERT,
        ExpertAgentType.MISSION_ALIGNMENT_EXPERT,
        ExpertAgentType.BUDGET_AND_ACQUISITION_EXPERT,
        ExpertAgentType.CYBERSECURITY_EXPERT,
        ExpertAgentType.OPERATIONS_EXPERT,
        ExpertAgentType.MODERNIZATION_EXPERT,
        ExpertAgentType.SKEPTIC_REVIEWER,
        ExpertAgentType.COMPLIANCE_REVIEWER,
        ExpertAgentType.COMPARATIVE_REVIEWER,
        ExpertAgentType.SELECTION_REVIEWER,
    ]

    def build_plan(
        self,
        db: Session,
        case_id: UUID,
        candidate_id: UUID | None = None,
    ) -> ExpertCouncilRunPlan:
        configured_agents = [
            ExpertAgentType(agent_type)
            for agent_type in db.scalars(
                select(ExpertAgent.agent_type)
                .where(ExpertAgent.enabled.is_(True))
                .order_by(ExpertAgent.display_name.asc())
            ).all()
            if agent_type in ExpertAgentType._value2member_map_
        ]
        return ExpertCouncilRunPlan(
            case_id=case_id,
            candidate_id=candidate_id,
            agents=configured_agents or self.default_agents,
        )

    def enqueue(self, db: Session, case_id: UUID, candidate_id: UUID | None = None) -> dict[str, object]:
        if not db.scalar(select(Rubric.id).where(Rubric.case_id == case_id)):
            raise HTTPException(status_code=400, detail="Create and lock a rubric before running the expert council.")
        plan = self.build_plan(db, case_id, candidate_id)
        task = run_expert_council.delay(str(case_id), str(candidate_id) if candidate_id else None)
        return {
            "case_id": str(plan.case_id),
            "candidate_id": str(plan.candidate_id) if plan.candidate_id else None,
            "agent_count": len(plan.agents),
            "agents": [agent.value for agent in plan.agents],
            "status": "queued",
            "task_id": task.id,
        }
