"""Council deliberation service — multi-agent board meeting orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.case import Candidate
from app.models.evaluation import BoardMeetingTranscript, ExpertAgent
from app.services.ai_inference import AIGatewayClient, GatewayInvocationRequest, GatewayInvocationResponse

logger = logging.getLogger(__name__)

PHASE_HEADERS = {
    "opening": "PHASE I — OPENING STATEMENTS",
    "deliberation": "PHASE II — BOARD DELIBERATION",
    "synthesis": "PHASE III — CHAIR SYNTHESIS",
}

AGENT_DISPLAY: dict[str, str] = {
    "pd_analyst": "PD Analyst",
    "resume_evidence_analyst": "Resume Evidence Analyst",
    "supervisory_expert": "Supervisory Expert",
    "technical_domain_expert": "Technical Domain Expert",
    "mission_alignment_expert": "Mission Alignment Expert",
    "budget_and_acquisition_expert": "Budget & Acquisition Expert",
    "cybersecurity_expert": "Cybersecurity Expert",
    "operations_expert": "Operations Expert",
    "modernization_expert": "Modernization Expert",
    "compliance_reviewer": "Compliance Reviewer",
    "skeptic_reviewer": "Skeptic Reviewer",
    "comparative_reviewer": "Comparative Reviewer",
    "selection_reviewer": "Chair — Selection Reviewer",
    "council_chair": "Council Chair",
}

PHASE1_TYPES = {
    "pd_analyst",
    "resume_evidence_analyst",
    "supervisory_expert",
    "technical_domain_expert",
    "mission_alignment_expert",
    "budget_and_acquisition_expert",
    "cybersecurity_expert",
    "operations_expert",
    "modernization_expert",
    "compliance_reviewer",
}
PHASE2_TYPES = {"skeptic_reviewer", "comparative_reviewer"}
PHASE3_TYPES = {"selection_reviewer"}


@dataclass
class DeliberationTurn:
    speaker: str
    display_name: str
    phase: str
    content: str
    responding_to: list[str] = field(default_factory=list)
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    confidence: float = 0.65
    evidence_quality: str = ""  # DOCUMENTED / INFERRED / ABSENT
    dimension_assessments: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DeliberationState:
    case_id: UUID
    candidate_id: UUID
    candidate_name: str
    position_title: str
    turns: list[DeliberationTurn] = field(default_factory=list)
    status: str = "opening"
    chair_recommendation: str = ""
    chair_tier: str = ""
    chair_confidence: float = 0.0
    chair_agreements: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    composite_score: Decimal = field(default_factory=lambda: Decimal("0.00"))
    score_based_tier: str = ""
    tier_a_threshold: Decimal = field(default_factory=lambda: Decimal("82.00"))
    tier_b_threshold: Decimal = field(default_factory=lambda: Decimal("68.00"))


class CouncilDeliberationService:
    def __init__(self) -> None:
        self.client = AIGatewayClient()

    # ─── Public orchestration ──────────────────────────────────────────────────

    def run_council_session(
        self,
        db: Session,
        case: Any,
        position_analysis: Any,
        rubric: Any,
        context: Any,
        facts: list[Any],
        ratings: list[Any],
        agents: list[ExpertAgent],
        composite_score: Decimal = Decimal("0.00"),
        tier_a_threshold: Decimal = Decimal("82.00"),
        tier_b_threshold: Decimal = Decimal("68.00"),
    ) -> DeliberationState:
        score_based_tier = (
            "Tier A"
            if composite_score >= tier_a_threshold
            else "Tier B"
            if composite_score >= tier_b_threshold
            else "Tier C"
        )
        state = DeliberationState(
            case_id=case.id,
            candidate_id=context.candidate.id,
            candidate_name=context.candidate.full_name,
            position_title=case.title,
            composite_score=composite_score,
            score_based_tier=score_based_tier,
            tier_a_threshold=tier_a_threshold,
            tier_b_threshold=tier_b_threshold,
        )

        # Round 0 — chair opens the session
        self._open_session(state, agents)

        # Round 1 — opening statements from specialist agents
        phase1 = [a for a in agents if a.agent_type in PHASE1_TYPES]
        self._run_opening_round(state, db, case, position_analysis, rubric, context, facts, ratings, phase1)

        # Round 2 — deliberation: skeptic → domain responses → comparative
        phase2_map = {a.agent_type: a for a in agents if a.agent_type in PHASE2_TYPES}
        state.status = "deliberating"
        self._run_deliberation_round(
            state, db, case, position_analysis, rubric, context, facts, ratings, agents, phase2_map
        )

        # Round 3 — chair synthesis
        phase3 = [a for a in agents if a.agent_type in PHASE3_TYPES]
        state.status = "synthesizing"
        if phase3:
            self._run_synthesis(state, db, case, position_analysis, rubric, context, facts, ratings, phase3[0])

        state.status = "complete"
        return state

    def format_full_transcript(self, state: DeliberationState, case: Any) -> str:
        header = (
            f"CANDIDATE SELECTION BOARD MEETING TRANSCRIPT\n"
            f"{'═' * 70}\n"
            f"Case:      {case.title}\n"
            f"Candidate: {state.candidate_name}\n"
            f"Convened:  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Agents:    {sum(1 for t in state.turns if t.speaker != 'council_chair')}\n"
            f"{'═' * 70}\n"
        )
        return header + self._format_turns(state.turns) + f"\n{'═' * 70}\nEND OF TRANSCRIPT"

    def build_meeting_notes(self, state: DeliberationState) -> dict[str, Any]:
        ph1 = [t for t in state.turns if t.phase == "opening" and t.speaker != "council_chair"]
        ph2 = [t for t in state.turns if t.phase == "deliberation"]
        skeptic = next((t for t in ph2 if t.speaker == "skeptic_reviewer"), None)
        responses = [t for t in ph2 if "skeptic_reviewer" in t.responding_to]
        avg_conf = (sum(t.confidence for t in ph1) / len(ph1)) if ph1 else 0.0
        all_strengths = list(dict.fromkeys(s for t in ph1 for s in t.strengths))
        all_concerns = list(dict.fromkeys(c for t in ph1 for c in t.concerns))
        return {
            "candidate": state.candidate_name,
            "position": state.position_title,
            "board_date": datetime.now(timezone.utc).isoformat(),
            "phase_1": {
                "agents_participated": len(ph1),
                "initial_strengths": all_strengths[:6],
                "initial_concerns": all_concerns[:6],
                "average_confidence": round(avg_conf, 2),
            },
            "phase_2": {
                "skeptic_summary": skeptic.summary if skeptic else "",
                "challenges_raised": (skeptic.concerns or []) if skeptic else [],
                "domain_responses": len(responses),
            },
            "phase_3": {
                "recommendation": state.chair_recommendation,
                "tier": state.chair_tier,
                "final_confidence": round(state.chair_confidence, 2),
                "board_agreements": state.chair_agreements,
                "unresolved_questions": state.open_questions,
            },
        }

    def generate_meeting_summary(self, db: Session, state: DeliberationState, agent: ExpertAgent | None) -> str:
        fallback = (
            f"The selection board reviewed {state.candidate_name}. "
            f"Recommendation: {state.chair_recommendation or 'HOLD'} — "
            f"Tier {state.chair_tier or 'B'} (confidence {state.chair_confidence:.2f}). "
            f"{'; '.join(state.chair_agreements[:2]) or 'See meeting notes for details.'}."
        )
        if not agent:
            return fallback

        excerpt = self._format_turns(state.turns[-3:])
        prompt = (
            f"A selection board reviewed {state.candidate_name} for the position of {state.position_title}.\n\n"
            f"Board conclusion: {state.chair_recommendation} — Tier {state.chair_tier} "
            f"(confidence {state.chair_confidence:.2f})\n"
            f"Agreements: {', '.join(state.chair_agreements[:3])}\n"
            f"Open questions: {', '.join(state.open_questions[:3])}\n\n"
            f"Recent deliberation:\n{excerpt}\n\n"
            f"Write a 2-3 sentence executive summary suitable for a selection package cover sheet. "
            f"Plain prose, no markdown, no headers."
        )
        req = GatewayInvocationRequest(
            purpose="council_summary",
            prompt=prompt,
            system_prompt="You are a selection board secretary. Write clear, professional meeting summaries.",
            provider=str(agent.config.get("provider") or "ollama"),
            model=str(agent.config.get("model") or "gpt-oss:120b-cloud"),
            temperature=0.3,
            max_tokens=400,
            metadata={"agent_type": "summary", "case_id": str(state.case_id), "candidate_id": str(state.candidate_id)},
        )
        try:
            resp = self.client.invoke(req)
            if resp.accepted and resp.content:
                return resp.content.strip()
        except Exception:
            logger.exception("Council summary generation failed — using fallback")
        return fallback

    def _turn_to_dict(self, t: DeliberationTurn) -> dict[str, Any]:
        return {
            "speaker": t.speaker,
            "display_name": t.display_name,
            "phase": t.phase,
            "content": t.content,
            "summary": t.summary,
            "findings": t.findings,
            "strengths": t.strengths,
            "concerns": t.concerns,
            "confidence": t.confidence,
            "evidence_quality": t.evidence_quality,
            "dimension_assessments": t.dimension_assessments,
            "responding_to": t.responding_to,
            "timestamp": t.timestamp,
        }

    def _persist_partial(self, db: Session, state: DeliberationState) -> None:
        """Upsert the current partial transcript after each agent turn."""
        ph1 = [t for t in state.turns if t.phase == "opening"]
        ph2 = [t for t in state.turns if t.phase == "deliberation"]
        existing = (
            db.query(BoardMeetingTranscript).filter_by(case_id=state.case_id, candidate_id=state.candidate_id).first()
        )
        if existing:
            existing.candidate_name = state.candidate_name
            existing.status = "in_progress"
            existing.phase1_turns = [self._turn_to_dict(t) for t in ph1]
            existing.phase2_turns = [self._turn_to_dict(t) for t in ph2]
            existing.agent_count = len(ph1)
            existing.round_count = len(ph2)
        else:
            db.add(
                BoardMeetingTranscript(
                    case_id=state.case_id,
                    candidate_id=state.candidate_id,
                    candidate_name=state.candidate_name,
                    status="in_progress",
                    phase1_turns=[self._turn_to_dict(t) for t in ph1],
                    phase2_turns=[self._turn_to_dict(t) for t in ph2],
                    agent_count=len(ph1),
                    round_count=len(ph2),
                )
            )
        db.flush()
        db.commit()

    def persist_board_meeting(
        self,
        db: Session,
        state: DeliberationState,
        full_transcript: str,
        meeting_notes: dict[str, Any],
        meeting_summary: str,
    ) -> None:
        ph1 = [t for t in state.turns if t.phase == "opening"]
        ph2 = [t for t in state.turns if t.phase == "deliberation"]
        synthesis = {}
        if state.chair_recommendation:
            synthesis = {
                "recommendation": state.chair_recommendation,
                "tier": state.chair_tier,
                "confidence": state.chair_confidence,
                "agreements": state.chair_agreements,
                "open_questions": state.open_questions,
            }

        existing = (
            db.query(BoardMeetingTranscript).filter_by(case_id=state.case_id, candidate_id=state.candidate_id).first()
        )

        if existing:
            existing.candidate_name = state.candidate_name
            existing.status = "complete"
            existing.agent_count = len(ph1)
            existing.round_count = len(ph2)
            existing.phase1_turns = [self._turn_to_dict(t) for t in ph1]
            existing.phase2_turns = [self._turn_to_dict(t) for t in ph2]
            existing.phase3_synthesis = synthesis
            existing.full_transcript = full_transcript
            existing.meeting_notes = meeting_notes
            existing.meeting_summary = meeting_summary
        else:
            db.add(
                BoardMeetingTranscript(
                    case_id=state.case_id,
                    candidate_id=state.candidate_id,
                    candidate_name=state.candidate_name,
                    status="complete",
                    agent_count=len(ph1),
                    round_count=len(ph2),
                    phase1_turns=[self._turn_to_dict(t) for t in ph1],
                    phase2_turns=[self._turn_to_dict(t) for t in ph2],
                    phase3_synthesis=synthesis,
                    full_transcript=full_transcript,
                    meeting_notes=meeting_notes,
                    meeting_summary=meeting_summary,
                )
            )
        db.flush()

        # Write council result back to candidate profile so the review matrix picks it up
        if state.chair_tier and state.chair_recommendation:
            candidate = db.get(Candidate, state.candidate_id)
            if candidate:
                profile = dict(candidate.profile or {})
                profile["council_result"] = {
                    "council_tier": state.chair_tier,
                    "council_recommendation": state.chair_recommendation,
                    "council_confidence": round(state.chair_confidence, 2),
                    "council_updated_at": datetime.now(timezone.utc).isoformat(),
                }
                candidate.profile = profile
                db.flush()

    def list_board_meetings(self, db: Session, case_id: UUID) -> list[dict[str, Any]]:
        rows = db.query(BoardMeetingTranscript).filter_by(case_id=case_id).all()
        return [self._bmt_to_dict(r) for r in rows]

    def get_board_meeting(self, db: Session, case_id: UUID, candidate_id: UUID) -> dict[str, Any] | None:
        row = db.query(BoardMeetingTranscript).filter_by(case_id=case_id, candidate_id=candidate_id).first()
        return self._bmt_to_dict(row) if row else None

    def delete_board_meeting(self, db: Session, case_id: UUID, candidate_id: UUID) -> bool:
        row = db.query(BoardMeetingTranscript).filter_by(case_id=case_id, candidate_id=candidate_id).first()
        if not row:
            return False
        db.delete(row)
        db.flush()
        return True

    def delete_all_board_meetings(self, db: Session, case_id: UUID) -> int:
        rows = db.query(BoardMeetingTranscript).filter_by(case_id=case_id).all()
        for row in rows:
            db.delete(row)
        db.flush()
        return len(rows)

    # ─── Round runners ─────────────────────────────────────────────────────────

    def _open_session(self, state: DeliberationState, agents: list[ExpertAgent]) -> None:
        names = [AGENT_DISPLAY.get(a.agent_type, a.display_name) for a in agents]
        content = (
            f"CANDIDATE SELECTION BOARD CONVENED\n"
            f"Position: {state.position_title}\n"
            f"Candidate: {state.candidate_name}\n"
            f"Board: {len(agents)} agents — {', '.join(names)}\n\n"
            f"The board will review the record of {state.candidate_name}. Phase I: opening statements from "
            f"specialist agents. Phase II: the Skeptic Reviewer challenges specific claims, challenged agents "
            f"respond, and the Comparative Reviewer places the candidate in context. "
            f"Phase III: the Chair synthesizes a final recommendation."
        )
        state.turns.append(
            DeliberationTurn(
                speaker="council_chair",
                display_name="Council Chair",
                phase="opening",
                content=content,
                summary=f"Board convened for {state.candidate_name}",
            )
        )

    def _run_opening_round(
        self,
        state: DeliberationState,
        db: Session,
        case: Any,
        position_analysis: Any,
        rubric: Any,
        context: Any,
        facts: list[Any],
        ratings: list[Any],
        agents: list[ExpertAgent],
    ) -> None:
        schema = {
            "type": "object",
            "properties": {
                "opening_statement": {"type": "string"},
                "summary": {"type": "string"},
                "evidence_quality": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "detail": {"type": "string"},
                            "severity": {"type": "string"},
                        },
                        "required": ["title", "detail", "severity"],
                    },
                },
                "strengths": {"type": "array", "items": {"type": "string"}},
                "concerns": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "dimension_assessments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "dimension": {"type": "string"},
                            "assessment": {"type": "string"},
                            "evidence_quote": {"type": "string"},
                            "gap": {"type": "string"},
                        },
                        "required": ["dimension", "assessment", "evidence_quote"],
                    },
                },
            },
            "required": [
                "opening_statement",
                "summary",
                "findings",
                "strengths",
                "concerns",
                "confidence",
                "evidence_quality",
                "dimension_assessments",
            ],
        }

        for agent in agents:
            prior = self._format_turns(state.turns)
            prompt = self._prompt_opening(
                case,
                position_analysis,
                rubric,
                context,
                facts,
                ratings,
                agent,
                prior,
                composite_score=state.composite_score,
                score_based_tier=state.score_based_tier,
                tier_a_threshold=state.tier_a_threshold,
                tier_b_threshold=state.tier_b_threshold,
            )
            resp = self._call(
                agent, prompt, schema, state.case_id, context.candidate.id, f"council_opening:{agent.agent_type}"
            )

            if resp.accepted and isinstance(resp.structured_output, dict):
                d = resp.structured_output
                turn = DeliberationTurn(
                    speaker=agent.agent_type,
                    display_name=AGENT_DISPLAY.get(agent.agent_type, agent.display_name),
                    phase="opening",
                    content=str(d.get("opening_statement") or d.get("summary") or ""),
                    summary=str(d.get("summary") or ""),
                    findings=d.get("findings") or [],
                    strengths=d.get("strengths") or [],
                    concerns=d.get("concerns") or [],
                    confidence=float(d.get("confidence") or 0.65),
                    evidence_quality=str(d.get("evidence_quality") or "INFERRED").upper(),
                    dimension_assessments=d.get("dimension_assessments") or [],
                )
            else:
                turn = DeliberationTurn(
                    speaker=agent.agent_type,
                    display_name=AGENT_DISPLAY.get(agent.agent_type, agent.display_name),
                    phase="opening",
                    content=f"[{agent.display_name}] Assessment unavailable.",
                    confidence=0.5,
                    evidence_quality="ABSENT",
                )
            state.turns.append(turn)
            self._persist_partial(db, state)

    def _run_deliberation_round(
        self,
        state: DeliberationState,
        db: Session,
        case: Any,
        position_analysis: Any,
        rubric: Any,
        context: Any,
        facts: list[Any],
        ratings: list[Any],
        all_agents: list[ExpertAgent],
        phase2_map: dict[str, ExpertAgent],
    ) -> None:
        agent_map = {a.agent_type: a for a in all_agents}
        challenged_types: list[str] = []

        # Skeptic challenges
        skeptic = phase2_map.get("skeptic_reviewer")
        if skeptic:
            prior = self._format_turns(state.turns)
            prompt = self._prompt_skeptic(
                case,
                context,
                skeptic,
                prior,
                composite_score=state.composite_score,
                score_based_tier=state.score_based_tier,
                tier_a_threshold=state.tier_a_threshold,
                tier_b_threshold=state.tier_b_threshold,
            )
            skeptic_schema = {
                "type": "object",
                "properties": {
                    "opening_statement": {"type": "string"},
                    "challenges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "challenged_agent": {"type": "string"},
                                "claim": {"type": "string"},
                                "challenge": {"type": "string"},
                                "severity": {"type": "string"},
                            },
                            "required": ["challenged_agent", "claim", "challenge", "severity"],
                        },
                    },
                    "summary": {"type": "string"},
                    "concerns": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["opening_statement", "challenges", "summary", "confidence"],
            }
            resp = self._call(skeptic, prompt, skeptic_schema, state.case_id, context.candidate.id, "council_skeptic")

            if resp.accepted and isinstance(resp.structured_output, dict):
                d = resp.structured_output
                challenges: list[dict] = d.get("challenges") or []
                challenged_types = [c.get("challenged_agent", "") for c in challenges if c.get("challenged_agent")]
                challenge_lines = "\n".join(
                    f"  [{c.get('severity', 'MEDIUM').upper()}] Re: {c.get('challenged_agent', '')} — {c.get('claim', '')}\n"
                    f"    {c.get('challenge', '')}"
                    for c in challenges
                )
                content = str(d.get("opening_statement") or "")
                if challenge_lines:
                    content = f"{content}\n\nCHALLENGES RAISED:\n{challenge_lines}"
                turn = DeliberationTurn(
                    speaker="skeptic_reviewer",
                    display_name="Skeptic Reviewer",
                    phase="deliberation",
                    content=content,
                    summary=str(d.get("summary") or ""),
                    concerns=d.get("concerns") or [],
                    confidence=float(d.get("confidence") or 0.65),
                )
            else:
                turn = DeliberationTurn(
                    speaker="skeptic_reviewer",
                    display_name="Skeptic Reviewer",
                    phase="deliberation",
                    content="[Skeptic Reviewer] Could not complete challenge analysis.",
                    confidence=0.5,
                )
            state.turns.append(turn)
            self._persist_partial(db, state)

        # Domain expert responses to challenges
        for agent_type in challenged_types:
            responding_agent = agent_map.get(agent_type)
            if not responding_agent or agent_type not in PHASE1_TYPES:
                continue
            prior = self._format_turns(state.turns)
            prompt = self._prompt_response(case, context, facts, ratings, responding_agent, prior)
            resp_schema = {
                "type": "object",
                "properties": {
                    "response_statement": {"type": "string"},
                    "challenge_disposition": {"type": "string"},
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["response_statement", "challenge_disposition", "summary", "confidence"],
            }
            resp = self._call(
                responding_agent,
                prompt,
                resp_schema,
                state.case_id,
                context.candidate.id,
                f"council_response:{agent_type}",
            )

            if resp.accepted and isinstance(resp.structured_output, dict):
                d = resp.structured_output
                disposition = str(d.get("challenge_disposition") or "qualified")
                content = str(d.get("response_statement") or "")
                turn = DeliberationTurn(
                    speaker=responding_agent.agent_type,
                    display_name=f"{AGENT_DISPLAY.get(agent_type, responding_agent.display_name)} — responding to Skeptic",
                    phase="deliberation",
                    content=content,
                    summary=f"Challenge {disposition}: {d.get('summary') or ''}",
                    confidence=float(d.get("confidence") or 0.65),
                    responding_to=["skeptic_reviewer"],
                )
            else:
                turn = DeliberationTurn(
                    speaker=responding_agent.agent_type,
                    display_name=f"{AGENT_DISPLAY.get(agent_type, responding_agent.display_name)} — responding to Skeptic",
                    phase="deliberation",
                    content=f"[{responding_agent.display_name}] Response pending.",
                    confidence=0.5,
                    responding_to=["skeptic_reviewer"],
                )
            state.turns.append(turn)
            self._persist_partial(db, state)

        # Comparative reviewer
        comparative = phase2_map.get("comparative_reviewer")
        if comparative:
            prior = self._format_turns(state.turns)
            prompt = self._prompt_comparative(case, context, comparative, prior)
            comp_schema = {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "summary": {"type": "string"},
                    "differentiators": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["statement", "summary", "confidence"],
            }
            resp = self._call(
                comparative, prompt, comp_schema, state.case_id, context.candidate.id, "council_comparative"
            )

            if resp.accepted and isinstance(resp.structured_output, dict):
                d = resp.structured_output
                turn = DeliberationTurn(
                    speaker="comparative_reviewer",
                    display_name="Comparative Reviewer",
                    phase="deliberation",
                    content=str(d.get("statement") or ""),
                    summary=str(d.get("summary") or ""),
                    strengths=d.get("differentiators") or [],
                    confidence=float(d.get("confidence") or 0.65),
                )
            else:
                turn = DeliberationTurn(
                    speaker="comparative_reviewer",
                    display_name="Comparative Reviewer",
                    phase="deliberation",
                    content="[Comparative Reviewer] No comparative assessment available.",
                    confidence=0.5,
                )
            state.turns.append(turn)
            self._persist_partial(db, state)

    def _run_synthesis(
        self,
        state: DeliberationState,
        db: Session,
        case: Any,
        position_analysis: Any,
        rubric: Any,
        context: Any,
        facts: list[Any],
        ratings: list[Any],
        chair: ExpertAgent,
    ) -> None:
        prior = self._format_turns(state.turns)
        prompt = self._prompt_synthesis(
            case,
            rubric,
            context,
            chair,
            prior,
            composite_score=state.composite_score,
            score_based_tier=state.score_based_tier,
            tier_a_threshold=state.tier_a_threshold,
            tier_b_threshold=state.tier_b_threshold,
        )
        schema = {
            "type": "object",
            "properties": {
                "synthesis_statement": {"type": "string"},
                "recommendation": {"type": "string"},
                "tier": {"type": "string"},
                "confidence": {"type": "number"},
                "agreements": {"type": "array", "items": {"type": "string"}},
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["synthesis_statement", "recommendation", "tier", "confidence", "agreements", "open_questions"],
        }
        resp = self._call(chair, prompt, schema, state.case_id, context.candidate.id, "council_synthesis")

        if resp.accepted and isinstance(resp.structured_output, dict):
            d = resp.structured_output
            state.chair_recommendation = str(d.get("recommendation") or "HOLD")
            state.chair_tier = str(d.get("tier") or "B")
            state.chair_confidence = float(d.get("confidence") or 0.65)
            state.chair_agreements = d.get("agreements") or []
            state.open_questions = d.get("open_questions") or []

            content = str(d.get("synthesis_statement") or "")
            footer = (
                f"\n\nBOARD CONCLUSION: {state.chair_recommendation} — TIER {state.chair_tier} | "
                f"Confidence: {state.chair_confidence:.2f}\n"
                f"AGREEMENTS: {'; '.join(state.chair_agreements[:3])}\n"
                f"OPEN QUESTIONS: {'; '.join(state.open_questions[:3])}"
            )
            turn = DeliberationTurn(
                speaker="selection_reviewer",
                display_name="Chair — Selection Reviewer",
                phase="synthesis",
                content=content + footer,
                summary=str(d.get("rationale") or ""),
                strengths=state.chair_agreements,
                concerns=state.open_questions,
                confidence=state.chair_confidence,
            )
        else:
            turn = DeliberationTurn(
                speaker="selection_reviewer",
                display_name="Chair — Selection Reviewer",
                phase="synthesis",
                content="[Chair] Synthesis incomplete. Manual review required.",
                confidence=0.5,
            )
        state.turns.append(turn)
        self._persist_partial(db, state)

    # ─── Prompt builders ───────────────────────────────────────────────────────

    def _prompt_opening(
        self,
        case,
        position_analysis,
        rubric,
        context,
        facts,
        ratings,
        agent,
        prior: str,
        composite_score: Decimal = Decimal("0.00"),
        score_based_tier: str = "",
        tier_a_threshold: Decimal = Decimal("82.00"),
        tier_b_threshold: Decimal = Decimal("68.00"),
    ) -> str:
        dims = "\n".join(
            f"  - {d.title} (weight {d.weight}): {d.description}" for d in (rubric.dimensions if rubric else [])
        )
        dim_names = [d.title for d in (rubric.dimensions if rubric else [])]

        # Full facts — no cap
        facts_full = "\n".join(f"  [{f.fact_type}] {f.fact_value}" for f in facts) or "  (none extracted)"

        # Full evidence summaries — no truncation
        ratings_full = (
            "\n".join(
                f"  [{r.rating} | score {r.score}] {getattr(r, 'dimension_title', '')} — {r.evidence_summary}"
                for r in ratings
            )
            or "  (no prior dimension ratings)"
        )

        # Full resume text
        resume_body = (context.resume_text or "").strip()
        if not resume_body:
            resume_body = "\n".join(q["quote_text"] for q in context.top_quotes) or "(resume text unavailable)"

        parts = [
            "CANDIDATE SELECTION BOARD SESSION — OPENING STATEMENT",
            f"Position: {case.title}",
            f"Candidate: {context.candidate.full_name}",
            f"Your role: {agent.display_name} — {agent.description}",
            "",
            "POSITION REQUIREMENTS:",
            str(position_analysis.recommended_dimensions if position_analysis else "See rubric"),
            "",
            f"RUBRIC DIMENSIONS (evaluate ALL of these):\n{dims}",
            "",
            f"RESUME — {context.candidate.full_name}:",
            resume_body,
            "",
            "EXTRACTED FACTS:",
            facts_full,
            "",
            "PRIOR DIMENSION RATINGS FROM AI ANALYSIS:",
            ratings_full,
            "",
            "SCORING CONTEXT (rubric-weighted composite from prior AI dimension analysis):",
            f"  Composite score : {composite_score:.2f} / 100.00",
            f"  Score-based tier: {score_based_tier}",
            f"  Thresholds      : Tier A ≥ {tier_a_threshold:.2f} | Tier B ≥ {tier_b_threshold:.2f} | Tier C < {tier_b_threshold:.2f}",
            "",
            "  The composite score reflects the weighted dimension ratings already in the system.",
            "  Your role: assess whether the resume evidence SUPPORTS or CONTRADICTS this placement.",
            "  If your qualitative findings warrant a different tier, state so explicitly and give",
            "  specific reasons. The chair will weigh all board arguments in the final recommendation.",
        ]
        if prior:
            parts += ["", "BOARD TRANSCRIPT SO FAR:", prior]
        parts += [
            "",
            f"Present your opening assessment to the board as the {agent.display_name}.",
            "",
            "INSTRUCTIONS:",
            "- Read the full resume text above before assessing.",
            "- For EVERY rubric dimension listed, produce one entry in dimension_assessments.",
            "  - assessment: EXCEEDS / MEETS / PARTIAL / ABSENT",
            "  - evidence_quote: the exact resume phrase you are citing, or 'NOT DOCUMENTED' if absent.",
            "  - gap: what is missing or unclear (omit if fully documented).",
            "- Set evidence_quality to one of:",
            "    DOCUMENTED — explicit, verbatim evidence for every major claim",
            "    INFERRED   — reasonable reading of the record; key claims lack direct quotes",
            "    ABSENT     — the resume does not address one or more critical requirements",
            "- Set confidence to reflect evidence completeness, NOT your certainty about the candidate:",
            "    0.90–1.00  All claims are directly quoted from the resume",
            "    0.70–0.89  Most claims documented; minor inference on 1–2 items",
            "    0.50–0.69  Significant inference; key areas lack direct documentation",
            "    0.20–0.49  Mostly inferred; the record is thin on your domain's requirements",
            "    0.10–0.19  Little to no evidence in your domain; candidate record is silent",
            "- Do NOT speculate beyond what is written. If the resume is silent on a requirement, say 'NOT DOCUMENTED' and flag it.",
            f"- Dimensions to evaluate: {', '.join(dim_names) or 'see rubric above'}",
            "- Other board members will see your assessment. Be precise and cite sources.",
        ]
        return "\n".join(parts)

    def _prompt_skeptic(
        self,
        case,
        context,
        agent,
        prior: str,
        composite_score: Decimal = Decimal("0.00"),
        score_based_tier: str = "",
        tier_a_threshold: Decimal = Decimal("82.00"),
        tier_b_threshold: Decimal = Decimal("68.00"),
    ) -> str:
        return (
            f"CANDIDATE SELECTION BOARD SESSION — DELIBERATION PHASE\n"
            f"Position: {case.title}\n"
            f"Candidate: {context.candidate.full_name}\n"
            f"Your role: {agent.display_name} — {agent.description}\n\n"
            f"SCORING CONTEXT:\n"
            f"  Composite score: {composite_score:.2f} / 100.00  |  Score-based tier: {score_based_tier}\n"
            f"  Tier thresholds: A ≥ {tier_a_threshold:.2f} | B ≥ {tier_b_threshold:.2f} | C < {tier_b_threshold:.2f}\n\n"
            f"FULL BOARD TRANSCRIPT:\n{prior}\n\n"
            f"You are the Skeptic Reviewer. Identify 2-3 specific claims by named board members that deserve challenge.\n"
            f"For each challenge:\n"
            f"  - Set 'challenged_agent' to the agent_type string (e.g., 'pd_analyst', 'budget_and_acquisition_expert')\n"
            f"  - Paraphrase the specific assertion in 'claim'\n"
            f"  - State what evidence is missing or overstated in 'challenge'\n"
            f"  - Set severity to HIGH, MEDIUM, or LOW\n\n"
            f"Be direct. If claims are well-supported, say so. Look for gaps between assertion and documented evidence.\n"
            f"Note: if the board's aggregate assessment implies a tier different from the composite score, flag this discrepancy."
        )

    def _prompt_response(self, case, context, facts, ratings, agent, prior: str) -> str:
        ratings_full = (
            "\n".join(
                f"  [{r.rating} | score {r.score}] {getattr(r, 'dimension_title', '')} — {r.evidence_summary}"
                for r in ratings
            )
            or "  (no prior ratings)"
        )
        resume_body = (context.resume_text or "").strip() or "(resume text unavailable)"
        return (
            f"CANDIDATE SELECTION BOARD SESSION — CHALLENGE RESPONSE\n"
            f"Position: {case.title}\n"
            f"Candidate: {context.candidate.full_name}\n"
            f"Your role: {agent.display_name} — {agent.description}\n\n"
            f"RESUME TEXT:\n{resume_body}\n\n"
            f"DIMENSION RATINGS:\n{ratings_full}\n\n"
            f"FULL BOARD TRANSCRIPT:\n{prior}\n\n"
            f"Respond specifically to challenges directed at claims within your domain. "
            f"Cite exact resume language. "
            f"State whether you: (a) sustain the challenge and revise your position, "
            f"(b) overturn the challenge with specific resume evidence, or "
            f"(c) qualify the challenge — partial revision with interview probe recommended. "
            f"Set 'challenge_disposition' to 'sustained', 'overturned', or 'qualified'."
        )

    def _prompt_comparative(self, case, context, agent, prior: str) -> str:
        return (
            f"CANDIDATE SELECTION BOARD SESSION — COMPARATIVE REVIEW\n"
            f"Position: {case.title}\n"
            f"Candidate under review: {context.candidate.full_name}\n"
            f"Your role: {agent.display_name} — {agent.description}\n\n"
            f"FULL BOARD TRANSCRIPT:\n{prior}\n\n"
            f"Place this candidate in context relative to the candidate pool and position requirements. "
            f"Note relative standing, differentiating strengths, and how the raised concerns compare "
            f"to what you would expect across the applicant pool."
        )

    def _prompt_synthesis(
        self,
        case,
        rubric,
        context,
        chair,
        prior: str,
        composite_score: Decimal = Decimal("0.00"),
        score_based_tier: str = "",
        tier_a_threshold: Decimal = Decimal("82.00"),
        tier_b_threshold: Decimal = Decimal("68.00"),
    ) -> str:
        return (
            f"CANDIDATE SELECTION BOARD SESSION — CHAIR SYNTHESIS\n"
            f"Position: {case.title}\n"
            f"Candidate: {context.candidate.full_name}\n"
            f"Your role: {chair.display_name} — {chair.description}\n\n"
            f"SCORING CONTEXT:\n"
            f"  Composite score: {composite_score:.2f} / 100.00  |  Score-based tier: {score_based_tier}\n"
            f"  Tier thresholds: A ≥ {tier_a_threshold:.2f} | B ≥ {tier_b_threshold:.2f} | C < {tier_b_threshold:.2f}\n\n"
            f"Your tier recommendation must explicitly address the composite score:\n"
            f"  - If affirming the score-based tier: note what the board's review confirmed.\n"
            f"  - If departing from the score-based tier: state exactly why the qualitative evidence\n"
            f"    does not support that placement (e.g., 'Despite a score of {composite_score:.2f} / {score_based_tier},\n"
            f"    the board finds the evidence of X insufficient because...').\n\n"
            f"COMPLETE BOARD TRANSCRIPT:\n{prior}\n\n"
            f"You are the Chair. Synthesize the board's deliberation into a final position.\n"
            f"Produce:\n"
            f"  - synthesis_statement: the board's final assessment (3-5 sentences)\n"
            f"  - recommendation: ADVANCE, HOLD, or DECLINE\n"
            f"  - tier: A (top), B (competitive), or C (marginal)\n"
            f"  - confidence: 0.0-1.0\n"
            f"  - agreements: 2-4 points the board agreed on\n"
            f"  - open_questions: 2-3 unresolved issues warranting interview probes\n"
            f"  - rationale: one concise paragraph explaining the recommendation\n\n"
            f"Weight the Skeptic's challenges and domain expert responses appropriately. "
            f"The recommendation must reflect the board's deliberated position, not just opening statements."
        )

    # ─── Helpers ───────────────────────────────────────────────────────────────

    def _format_turns(self, turns: list[DeliberationTurn]) -> str:
        if not turns:
            return ""
        lines: list[str] = []
        current_phase = None
        for turn in turns:
            if turn.phase != current_phase:
                current_phase = turn.phase
                header = PHASE_HEADERS.get(turn.phase, turn.phase.upper())
                lines.append(f"\n{header}\n{'─' * 50}")
            lines.append(f"\n[{turn.display_name.upper()}]")
            lines.append(turn.content)
            if turn.phase == "opening" and turn.confidence:
                lines.append(f"Confidence: {turn.confidence:.2f}")
        return "\n".join(lines)

    def _call(
        self,
        agent: ExpertAgent,
        prompt: str,
        schema: dict[str, Any] | None,
        case_id: UUID,
        candidate_id: UUID,
        purpose: str,
    ) -> GatewayInvocationResponse:
        req = GatewayInvocationRequest(
            purpose=purpose,
            prompt=prompt,
            system_prompt=(
                "You are an evidence-focused selection board agent. "
                "Engage with what other board members have said. "
                "Use only the supplied record and transcript. "
                "If evidence is missing, say so instead of inferring."
            ),
            provider=str(agent.config.get("provider") or "ollama"),
            model=str(agent.config.get("model") or "gpt-oss:120b-cloud"),
            temperature=float(agent.config.get("temperature", 0.3)),
            max_tokens=int(agent.config.get("max_tokens", 8000)),
            response_schema=schema,
            metadata={
                "agent_type": agent.agent_type,
                "case_id": str(case_id),
                "candidate_id": str(candidate_id),
            },
        )
        try:
            return self.client.invoke(req)
        except Exception as exc:
            return GatewayInvocationResponse(
                accepted=False,
                provider=req.provider or "ollama",
                model=req.model or "gpt-oss:120b-cloud",
                content="",
                structured_output=None,
                usage={},
                validation_errors=[{"message": str(exc)}],
                fallback_used=True,
            )

    def _bmt_to_dict(self, row: BoardMeetingTranscript) -> dict[str, Any]:
        all_turns = list(row.phase1_turns or []) + list(row.phase2_turns or [])
        return {
            "id": str(row.id),
            "case_id": str(row.case_id),
            "candidate_id": str(row.candidate_id),
            "candidate_name": row.candidate_name,
            "status": row.status,
            "agent_count": row.agent_count,
            "round_count": row.round_count,
            "phase1_turns": row.phase1_turns or [],
            "phase2_turns": row.phase2_turns or [],
            "phase3_synthesis": row.phase3_synthesis or {},
            "all_turns": all_turns,
            "full_transcript": row.full_transcript or "",
            "meeting_notes": row.meeting_notes or {},
            "meeting_summary": row.meeting_summary or "",
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        }
