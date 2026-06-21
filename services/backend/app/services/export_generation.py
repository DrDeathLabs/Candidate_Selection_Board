"""Decision-package export generation.

Builds a ZIP "decision package" for a case — a human-readable summary plus the
structured evaluation record — and stores it in object storage. Reused by the
exports API route. The package is intentionally not cryptographically signed;
tamper-evidence, if needed, is left to the storage layer / deployment.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.case import Candidate, ReviewCase, RubricDimension
from app.models.evaluation import (
    BoardMeetingTranscript,
    CandidateFact,
    CandidateRating,
    ConsensusResult,
    ExpertReview,
    SelectionRecommendation,
)
from app.models.operations import AdjudicationAction, AuditEvent, ExportPackage
from app.services.storage import ObjectStorageService


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _dump(data: Any) -> str:
    return json.dumps(data, default=_json_default, indent=2, sort_keys=False)


def _slug(name: str | None, fallback: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip("-")
    return base or fallback


def _rows(objects: list[Any], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{f: getattr(obj, f) for f in fields} for obj in objects]


def build_package_bytes(db: Session, case: ReviewCase) -> bytes:
    """Assemble the decision-package ZIP for a case and return its bytes."""
    case_id = case.id
    candidates = db.query(Candidate).filter(Candidate.case_id == case_id).order_by(Candidate.full_name).all()
    candidate_name = {c.id: c.full_name for c in candidates}

    # Rubric dimension titles for rating readability.
    dimension_title: dict[Any, str] = {dim.id: dim.title for dim in db.query(RubricDimension).all()}

    recommendation = (
        db.query(SelectionRecommendation)
        .filter(SelectionRecommendation.case_id == case_id)
        .order_by(SelectionRecommendation.created_at.desc())
        .first()
    )
    adjudications = (
        db.query(AdjudicationAction)
        .filter(AdjudicationAction.case_id == case_id)
        .order_by(AdjudicationAction.created_at.asc())
        .all()
    )
    audit_events = (
        db.query(AuditEvent).filter(AuditEvent.case_id == case_id).order_by(AuditEvent.occurred_at.asc()).all()
    )

    case_doc = {
        "case": {
            "id": str(case.id),
            "title": case.title,
            "series": case.series,
            "grade": case.grade,
            "organization": case.organization,
            "hiring_action_type": case.hiring_action_type,
            "certificate_number": case.certificate_number,
            "selecting_official": case.selecting_official,
            "panel_members": case.panel_members,
            "status": case.status,
            "created_at": case.created_at,
        },
        "recommendation": None,
        "adjudication_actions": _rows(
            adjudications, ("actor_id", "action_type", "target_candidate_id", "rationale", "payload", "created_at")
        ),
        "candidate_index": [
            {"id": str(c.id), "full_name": c.full_name, "email": c.email, "disposition": c.disposition}
            for c in candidates
        ],
    }
    if recommendation is not None:
        case_doc["recommendation"] = {
            "recommendation_type": recommendation.recommendation_type,
            "status": recommendation.status,
            "selectee": candidate_name.get(recommendation.selectee_candidate_id),
            "selectee_candidate_id": str(recommendation.selectee_candidate_id)
            if recommendation.selectee_candidate_id
            else None,
            "alternates": [candidate_name.get(_as_uuid(cid), cid) for cid in recommendation.alternate_candidate_ids],
            "interview_slate": recommendation.interview_slate_candidate_ids,
            "discarded": recommendation.discarded_candidate_ids,
            "rationale": recommendation.rationale,
            "non_selection_rationale": recommendation.non_selection_rationale,
            "confidence": recommendation.confidence,
            "remaining_validation_issues": recommendation.remaining_validation_issues,
        }

    # Per-candidate dossiers.
    candidate_docs: dict[str, dict[str, Any]] = {}
    transcripts_text: dict[str, str] = {}
    for cand in candidates:
        ratings = (
            db.query(CandidateRating)
            .filter(CandidateRating.candidate_id == cand.id)
            .order_by(CandidateRating.created_at.asc())
            .all()
        )
        facts = db.query(CandidateFact).filter(CandidateFact.candidate_id == cand.id).all()
        reviews = db.query(ExpertReview).filter(ExpertReview.candidate_id == cand.id).all()
        consensus = db.query(ConsensusResult).filter(ConsensusResult.candidate_id == cand.id).all()
        transcripts = (
            db.query(BoardMeetingTranscript)
            .filter(BoardMeetingTranscript.candidate_id == cand.id)
            .order_by(BoardMeetingTranscript.created_at.asc())
            .all()
        )

        slug = _slug(cand.full_name, f"candidate-{str(cand.id)[:8]}")
        candidate_docs[slug] = {
            "candidate": {
                "id": str(cand.id),
                "full_name": cand.full_name,
                "email": cand.email,
                "disposition": cand.disposition,
                "profile": cand.profile,
            },
            "ratings": [
                {
                    "dimension": dimension_title.get(r.rubric_dimension_id, str(r.rubric_dimension_id)),
                    "rating": r.rating,
                    "score": r.score,
                    "confidence": r.confidence,
                    "evidence_summary": r.evidence_summary,
                    "strengths": r.strengths,
                    "concerns": r.concerns,
                    "overridden": r.overridden,
                    "override_rationale": r.override_rationale,
                }
                for r in ratings
            ],
            "facts": _rows(facts, ("fact_type", "fact_value", "confidence", "unsupported", "notes")),
            "expert_reviews": _rows(
                reviews, ("agent_type", "status", "summary", "findings", "strengths", "concerns", "confidence")
            ),
            "consensus": _rows(
                consensus,
                ("consensus_summary", "agreement_points", "dissent_points", "unresolved_issues", "confidence"),
            ),
        }

        transcript_blocks: list[str] = []
        for t in transcripts:
            header = f"=== Board meeting — {t.candidate_name or cand.full_name} ({t.status}) ==="
            body = t.full_transcript or t.meeting_summary or "(no transcript recorded)"
            transcript_blocks.append(f"{header}\n\n{body}")
        if transcript_blocks:
            transcripts_text[slug] = "\n\n\n".join(transcript_blocks)

    summary_md = _render_summary(case, candidates, candidate_name, case_doc, candidate_docs, audit_events)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.md", summary_md)
        zf.writestr("case.json", _dump(case_doc))
        zf.writestr(
            "audit-trail.json",
            _dump(
                _rows(audit_events, ("event_type", "actor_id", "entity_type", "entity_id", "details", "occurred_at"))
            ),
        )
        for slug, doc in candidate_docs.items():
            zf.writestr(f"candidates/{slug}.json", _dump(doc))
        for slug, text in transcripts_text.items():
            zf.writestr(f"board-meetings/{slug}.txt", text)
    return buffer.getvalue()


def _as_uuid(value: Any) -> Any:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return value


def _render_summary(
    case: ReviewCase,
    candidates: list[Candidate],
    candidate_name: dict[Any, str],
    case_doc: dict[str, Any],
    candidate_docs: dict[str, dict[str, Any]],
    audit_events: list[AuditEvent],
) -> str:
    lines: list[str] = []
    lines.append(f"# Decision Package — {case.title}")
    lines.append("")
    lines.append(f"- **Organization:** {case.organization or 'n/a'}")
    lines.append(f"- **Hiring action:** {case.hiring_action_type or 'n/a'}")
    lines.append(f"- **Certificate:** {case.certificate_number or 'n/a'}")
    lines.append(f"- **Selecting official:** {case.selecting_official or 'n/a'}")
    lines.append(f"- **Status:** {case.status}")
    lines.append(f"- **Generated:** {datetime.utcnow().isoformat()}Z")
    lines.append(f"- **Candidates:** {len(candidates)}")
    lines.append("")

    rec = case_doc.get("recommendation")
    if rec:
        lines.append("## Recommendation")
        lines.append("")
        lines.append(f"- **Selectee:** {rec.get('selectee') or 'none recorded'}")
        alts = rec.get("alternates") or []
        lines.append(f"- **Alternates:** {', '.join(str(a) for a in alts) if alts else 'none'}")
        if rec.get("rationale"):
            lines.append("")
            lines.append("**Rationale:**")
            lines.append("")
            lines.append(str(rec["rationale"]))
        lines.append("")

    lines.append("## Candidates")
    lines.append("")
    for cand in candidates:
        slug = next((s for s, d in candidate_docs.items() if d["candidate"]["id"] == str(cand.id)), None)
        doc = candidate_docs.get(slug, {}) if slug else {}
        lines.append(f"### {cand.full_name}")
        lines.append("")
        lines.append(f"- **Email:** {cand.email or 'n/a'}")
        lines.append(f"- **Disposition:** {cand.disposition}")
        ratings = doc.get("ratings", [])
        if ratings:
            lines.append("")
            lines.append("| Dimension | Rating | Score |")
            lines.append("| --- | --- | --- |")
            for r in ratings:
                lines.append(f"| {r['dimension']} | {r['rating']} | {r['score']} |")
        reviews = doc.get("expert_reviews", [])
        if reviews:
            lines.append("")
            lines.append("**Expert review highlights:**")
            lines.append("")
            for rev in reviews:
                summary = (rev.get("summary") or "").strip()
                if summary:
                    lines.append(f"- _{rev.get('agent_type')}_: {summary}")
        lines.append("")

    lines.append(f"_Audit events captured in this case: {len(audit_events)} (see `audit-trail.json`)._")
    lines.append("")
    return "\n".join(lines)


def generate_export_package(db: Session, export: ExportPackage) -> ExportPackage:
    """Generate the decision package for an ExportPackage row, store it, and mark it complete.

    Sets export.status to "complete" (with storage_key) on success or "failed"
    (with an error note in parameters) on error. Commits the row in both cases.
    """
    case = db.get(ReviewCase, export.case_id)
    if case is None:
        export.status = "failed"
        export.parameters = {**(export.parameters or {}), "error": "case not found"}
        db.commit()
        return export

    try:
        data = build_package_bytes(db, case)
        storage = ObjectStorageService()
        object_ref = storage.build_object_ref(str(export.case_id), f"exports/decision-package-{export.id}.zip")
        storage.upload_bytes(object_ref, data, content_type="application/zip")
        export.storage_key = object_ref.key
        export.status = "complete"
        export.parameters = {**(export.parameters or {}), "byte_size": len(data)}
    except Exception as exc:  # noqa: BLE001 — record failure rather than 500 the request
        export.status = "failed"
        export.parameters = {**(export.parameters or {}), "error": str(exc)[:500]}
    db.commit()
    db.refresh(export)
    return export
