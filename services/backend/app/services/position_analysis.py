from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import Document, PositionAnalysis
from app.models.system import ModelRun
from app.schemas.rubrics import RubricCreate, RubricDimensionCreate

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

ROLE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cybersecurity", ("cybersecurity", "incident response", "zero trust", "security operations", "security controls")),
    ("program_manager", ("program management", "program manager", "portfolio", "roadmap", "cross-functional")),
    ("supervisory", ("supervis", "team lead", "performance management", "span of control", "personnel")),
    ("infrastructure", ("infrastructure", "platform", "network", "data center", "hosting")),
    ("application_portfolio", ("application", "software", "systems development", "delivery", "product")),
    ("data", ("data", "analytics", "governance", "reporting", "metrics")),
    ("acquisition", ("acquisition", "procurement", "contract", "vendor", "source selection")),
    ("mission_operations", ("operations", "sustainment", "service delivery", "incident", "continuity")),
    ("policy", ("policy", "governance", "compliance", "directive", "standards")),
    ("technical_specialist", ("engineer", "architect", "technical", "cloud", "devsecops")),
)

FACTOR_LIBRARY: tuple[dict[str, Any], ...] = (
    {
        "key": "leadership_scope",
        "title": "Leadership And Supervisory Scope",
        "description": "Depth of leadership, supervision, oversight, and accountability for teams or contractors.",
        "keywords": ("supervis", "lead", "manager", "performance", "contractor"),
        "weight": 22,
    },
    {
        "key": "technical_alignment",
        "title": "Technical Alignment",
        "description": "Technical relevance to the role's domain, systems, tooling, and delivery expectations.",
        "keywords": ("technical", "system", "architecture", "engineering", "cloud", "platform"),
        "weight": 20,
    },
    {
        "key": "mission_delivery",
        "title": "Mission Delivery",
        "description": "Ability to support mission outcomes, stakeholder needs, and organizational priorities.",
        "keywords": ("mission", "stakeholder", "organization", "program", "outcome"),
        "weight": 18,
    },
    {
        "key": "operations_execution",
        "title": "Operations And Execution",
        "description": "Ownership of production, sustainment, reliability, and operational decision-making.",
        "keywords": ("operations", "sustainment", "reliability", "incident", "continuity"),
        "weight": 15,
    },
    {
        "key": "modernization",
        "title": "Modernization And Delivery",
        "description": "Evidence of transformation, modernization, process improvement, and delivery outcomes.",
        "keywords": ("modernization", "transformation", "agile", "devsecops", "automation", "delivery"),
        "weight": 12,
    },
    {
        "key": "budget_acquisition",
        "title": "Budget And Acquisition",
        "description": "Budget authority, acquisition strategy, contract oversight, and vendor management.",
        "keywords": ("budget", "acquisition", "procurement", "contract", "vendor"),
        "weight": 8,
    },
    {
        "key": "cybersecurity",
        "title": "Cybersecurity And Risk",
        "description": "Cybersecurity responsibility, risk management, and protection of operational systems.",
        "keywords": ("cyber", "security", "risk", "authorization", "privacy"),
        "weight": 5,
    },
)

FALLBACK_DIMENSIONS: tuple[dict[str, Any], ...] = (
    {"title": "Role Fit", "description": "Alignment to the core role requirements and scope.", "weight": 30},
    {"title": "Execution", "description": "Ability to execute the mission and deliver results.", "weight": 25},
    {"title": "Leadership", "description": "Leadership, influence, and accountability.", "weight": 20},
    {"title": "Communication", "description": "Communication, judgment, and stakeholder engagement.", "weight": 15},
    {
        "title": "Evidence Confidence",
        "description": "Strength, specificity, and completeness of supporting evidence.",
        "weight": 10,
    },
)


class PositionAnalysisService:
    def analyze_case(self, db: Session, case_id: UUID) -> PositionAnalysis:
        documents = db.scalars(
            select(Document).where(
                Document.case_id == case_id,
                Document.status == "ready",
                Document.document_type.in_(("position_description", "vacancy_announcement")),
            )
        ).all()
        if not documents:
            raise HTTPException(
                status_code=400, detail="No ready position description or vacancy documents found for this case."
            )

        source_text = self._build_source_text(documents)
        if not source_text.strip():
            raise HTTPException(status_code=400, detail="Parsed position analysis source text is empty.")

        duties = self._extract_duties(source_text)
        role_type = self._classify_role_type(source_text)
        critical_factors = self._extract_critical_factors(source_text, duties)
        recommended_dimensions = self._build_recommended_dimensions(critical_factors)
        evidence_map = {
            "document_count": len(documents),
            "source_documents": [
                {
                    "id": str(document.id),
                    "file_name": document.file_name,
                    "document_type": document.document_type,
                    "page_count": document.page_count,
                }
                for document in documents
            ],
            "source_excerpt": source_text[:2000],
        }

        analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == case_id))
        if analysis is None:
            analysis = PositionAnalysis(case_id=case_id)
            db.add(analysis)

        analysis.role_type = role_type
        analysis.status = "ready"
        analysis.duties = duties
        analysis.critical_factors = critical_factors
        analysis.recommended_dimensions = recommended_dimensions
        analysis.evidence_map = evidence_map

        db.add(
            ModelRun(
                case_id=case_id,
                candidate_id=None,
                prompt_template_id=None,
                provider="deterministic",
                model_name="heuristic-pd-analyzer",
                request_purpose="position_analysis",
                status="completed",
                input_tokens=None,
                output_tokens=None,
                total_cost=Decimal("0.0000"),
                request_payload={"document_ids": [str(document.id) for document in documents]},
                response_payload={
                    "role_type": role_type,
                    "duty_count": len(duties),
                    "critical_factor_count": len(critical_factors),
                    "recommended_dimension_count": len(recommended_dimensions),
                },
                validation_errors=[],
                started_at=None,
                completed_at=None,
            )
        )
        db.commit()
        db.refresh(analysis)
        return analysis

    def get_case_analysis(self, db: Session, case_id: UUID) -> PositionAnalysis:
        analysis = db.scalar(select(PositionAnalysis).where(PositionAnalysis.case_id == case_id))
        if analysis is None:
            raise HTTPException(status_code=404, detail="Position analysis not found for this case.")
        return analysis

    def build_rubric_create(self, analysis: PositionAnalysis, rubric_name: str) -> RubricCreate:
        dimensions = analysis.recommended_dimensions or list(FALLBACK_DIMENSIONS)
        return RubricCreate(
            name=rubric_name,
            position_analysis_id=analysis.id,
            dimensions=[
                RubricDimensionCreate(
                    title=str(dimension["title"]),
                    description=str(dimension["description"]),
                    weight=Decimal(str(dimension["weight"])),
                    order_index=index,
                    evidence_links=dimension.get("evidence_links") or [],
                )
                for index, dimension in enumerate(dimensions, start=1)
            ],
        )

    def _build_source_text(self, documents: list[Document]) -> str:
        MAX_TEXT_CHARS = 500_000  # ~500KB cap — prevents OOM on very large position docs
        chunks: list[str] = []
        total = 0
        for document in documents:
            if total >= MAX_TEXT_CHARS:
                break
            parse_summary = document.metadata_json.get("parse_summary", {})
            full_text = str(parse_summary.get("full_text") or "").strip()
            if full_text:
                remaining = MAX_TEXT_CHARS - total
                chunks.append(full_text[:remaining])
                total += len(full_text)
        return "\n\n".join(chunks)

    def _extract_duties(self, source_text: str) -> list[dict[str, Any]]:
        candidate_lines = []
        for raw_line in source_text.splitlines():
            line = raw_line.strip().strip("-*•")
            if len(line) < 30 or len(line) > 260:
                continue
            lowered = line.lower()
            if any(
                keyword in lowered
                for keyword in (
                    "respons",
                    "lead",
                    "manage",
                    "oversee",
                    "direct",
                    "coordinate",
                    "develop",
                    "implement",
                    "support",
                    "advise",
                )
            ):
                candidate_lines.append(line)

        if not candidate_lines:
            candidate_lines = [
                sentence.strip()
                for sentence in SENTENCE_SPLIT_PATTERN.split(source_text)
                if 40 <= len(sentence.strip()) <= 260
            ]

        duties: list[dict[str, Any]] = []
        seen: set[str] = set()
        for line in candidate_lines:
            normalized = re.sub(r"\s+", " ", line.lower())
            if normalized in seen:
                continue
            seen.add(normalized)
            duties.append(
                {
                    "title": self._shorten_title(line),
                    "description": line,
                    "evidence": line[:180],
                }
            )
            if len(duties) == 6:
                break

        if not duties:
            duties.append(
                {
                    "title": "Position Scope Review",
                    "description": source_text[:220],
                    "evidence": source_text[:180],
                }
            )
        return duties

    def _classify_role_type(self, source_text: str) -> str:
        text = source_text.lower()
        scores = [
            (role_type, sum(text.count(keyword) for keyword in keywords)) for role_type, keywords in ROLE_PATTERNS
        ]
        scores.sort(key=lambda entry: entry[1], reverse=True)
        if not scores or scores[0][1] == 0:
            return "hybrid"
        if len(scores) > 1 and scores[1][1] > 0 and scores[0][1] - scores[1][1] <= 1:
            return "hybrid"
        return scores[0][0]

    def _extract_critical_factors(self, source_text: str, duties: list[dict[str, Any]]) -> list[dict[str, Any]]:
        text = source_text.lower()
        factors: list[dict[str, Any]] = []
        for factor in FACTOR_LIBRARY:
            evidence = [
                duty["description"]
                for duty in duties
                if any(keyword in duty["description"].lower() for keyword in factor["keywords"])
            ]
            score = sum(text.count(keyword) for keyword in factor["keywords"])
            if score == 0 and not evidence:
                continue
            factors.append(
                {
                    "key": factor["key"],
                    "title": factor["title"],
                    "description": factor["description"],
                    "weight_hint": factor["weight"],
                    "evidence": evidence[:3] or [source_text[:180]],
                }
            )

        if not factors:
            factors = [
                {
                    "key": "general_fit",
                    "title": "General Position Fit",
                    "description": "Core alignment to the documented duties and expectations.",
                    "weight_hint": 100,
                    "evidence": [duty["description"] for duty in duties[:3]],
                }
            ]
        return factors

    def _build_recommended_dimensions(self, critical_factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total_hint = sum(int(factor.get("weight_hint", 0)) for factor in critical_factors) or 100
        dimensions: list[dict[str, Any]] = []
        running_total = 0
        for index, factor in enumerate(critical_factors, start=1):
            raw_weight = (Decimal(str(factor.get("weight_hint", 0))) / Decimal(str(total_hint))) * Decimal("100")
            weight = int(raw_weight.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if index == len(critical_factors):
                weight = 100 - running_total
            running_total += weight
            dimensions.append(
                {
                    "title": factor["title"],
                    "description": factor["description"],
                    "weight": max(weight, 1),
                    "order_index": index,
                    "evidence_links": [
                        {"type": "position_analysis", "excerpt": evidence} for evidence in factor.get("evidence", [])
                    ],
                }
            )

        total_weight = sum(int(dimension["weight"]) for dimension in dimensions)
        if dimensions and total_weight != 100:
            dimensions[-1]["weight"] = int(dimensions[-1]["weight"]) + (100 - total_weight)
        return dimensions

    def _shorten_title(self, text: str) -> str:
        words = re.split(r"\s+", text.strip())
        return " ".join(words[:8]).strip().rstrip(".,:;")
