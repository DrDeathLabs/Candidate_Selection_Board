from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.case import Candidate, CandidateMatch, Document, ResumeSegment
from app.models.evaluation import (
    CandidateFact,
    CandidateRating,
    ChallengeFinding,
    ConsensusResult,
    EvidenceItem,
    ExpertReview,
    InterviewQuestion,
    InterviewResult,
    PairwiseComparison,
    SelectionRecommendation,
)
from app.models.operations import AdjudicationAction
from app.models.system import ModelRun
from app.schemas.candidates import (
    CandidateMatchDetail,
    CandidateReconciliationResult,
    CandidateReconciliationSummary,
    ResumeSegmentRead,
)
from app.services.ai_inference import AIGatewayClient, GatewayInvocationRequest

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
NAME_LINE_PATTERN = re.compile(r"^name:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
TITLE_CASE_NAME_PATTERN = re.compile(r"^[A-Z][a-z]+(?: [A-Z][a-z.'-]+){1,3}$")


@dataclass(slots=True)
class IdentityBlock:
    name: str | None
    email: str | None
    text: str
    start_page: int
    end_page: int
    confidence: Decimal


class ReconciliationService:
    def reconcile_case(self, db: Session, case_id: UUID) -> CandidateReconciliationResult:
        documents = db.scalars(select(Document).where(Document.case_id == case_id)).all()
        try:
            self._refresh_resume_segments(db, documents)
            db.flush()
            self._refresh_candidates(db, case_id, documents)
            db.flush()
            self._refresh_candidate_matches(db, case_id)
        except Exception:
            db.rollback()
            raise
        db.commit()
        return self._build_result(db, case_id)

    def get_case_result(self, db: Session, case_id: UUID) -> CandidateReconciliationResult:
        return self._build_result(db, case_id)

    def assign_segment_to_candidate(
        self,
        db: Session,
        case_id: UUID,
        candidate_id: UUID,
        resume_segment_id: UUID | None,
        notes: str | None = None,
    ) -> CandidateReconciliationResult:
        candidate = db.scalar(select(Candidate).where(Candidate.case_id == case_id, Candidate.id == candidate_id))
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found for this case.")

        candidate_match = db.scalar(
            select(CandidateMatch).where(CandidateMatch.case_id == case_id, CandidateMatch.candidate_id == candidate_id)
        )
        if candidate_match is None:
            candidate_match = CandidateMatch(
                case_id=case_id,
                candidate_id=candidate_id,
                resume_segment_id=None,
                matched_name=None,
                matched_email=None,
                confidence=Decimal("0.00"),
                is_duplicate=False,
                notes="No resume segment matched this candidate.",
            )
            db.add(candidate_match)
            db.flush()

        current_segment = None
        if candidate_match.resume_segment_id is not None:
            current_segment = db.scalar(
                select(ResumeSegment).where(ResumeSegment.id == candidate_match.resume_segment_id)
            )

        if current_segment is not None and current_segment.candidate_id == candidate_id:
            current_segment.candidate_id = None

        if resume_segment_id is None:
            self._set_match_unassigned(candidate_match, notes or "Cleared manually from the reconciliation workspace.")
            db.commit()
            return self._build_result(db, case_id)

        segment = db.scalar(
            select(ResumeSegment)
            .join(Document)
            .where(ResumeSegment.id == resume_segment_id, Document.case_id == case_id)
        )
        if segment is None:
            raise HTTPException(status_code=404, detail="Resume segment not found for this case.")

        conflicting_matches = db.scalars(
            select(CandidateMatch).where(
                CandidateMatch.case_id == case_id,
                CandidateMatch.resume_segment_id == segment.id,
                CandidateMatch.candidate_id != candidate_id,
            )
        ).all()
        for conflicting_match in conflicting_matches:
            self._set_match_unassigned(
                conflicting_match,
                "Cleared after this resume segment was reassigned to another candidate.",
            )

        score, score_note = self._score_match(candidate, segment)
        segment.candidate_id = candidate.id
        candidate_match.resume_segment_id = segment.id
        candidate_match.matched_name = segment.inferred_name
        candidate_match.matched_email = segment.inferred_email
        candidate_match.confidence = Decimal(f"{score:.2f}")
        candidate_match.is_duplicate = False
        candidate_match.notes = notes or f"Manually assigned. {score_note}"
        db.commit()
        return self._build_result(db, case_id)

    def create_manual_candidate(
        self,
        db: Session,
        case_id: UUID,
        full_name: str,
        email: str | None,
        certificate_identifier: str | None,
    ) -> Candidate:
        candidate = Candidate(
            case_id=case_id,
            full_name=full_name.strip(),
            email=email.strip() if email else None,
            certificate_identifier=certificate_identifier.strip() if certificate_identifier else None,
            profile={"source": "manual"},
        )
        db.add(candidate)
        db.flush()
        db.add(
            CandidateMatch(
                case_id=case_id,
                candidate_id=candidate.id,
                resume_segment_id=None,
                matched_name=None,
                matched_email=None,
                confidence=Decimal("0.00"),
                is_duplicate=False,
                notes="Created manually. No resume segment assigned yet.",
            )
        )
        db.commit()
        db.refresh(candidate)
        return candidate

    def merge_candidates(
        self,
        db: Session,
        case_id: UUID,
        source_candidate_id: UUID,
        target_candidate_id: UUID,
    ) -> CandidateReconciliationResult:
        if source_candidate_id == target_candidate_id:
            raise HTTPException(status_code=400, detail="Source and target candidates must be different.")

        source = db.scalar(select(Candidate).where(Candidate.case_id == case_id, Candidate.id == source_candidate_id))
        target = db.scalar(select(Candidate).where(Candidate.case_id == case_id, Candidate.id == target_candidate_id))
        if source is None or target is None:
            raise HTTPException(status_code=404, detail="Both candidates must exist in this case.")

        self._merge_candidate_fields(source, target)

        target_match = self._get_or_create_match(
            db, case_id, target.id, "Merge target created without a candidate match row."
        )
        source_match = db.scalar(
            select(CandidateMatch).where(CandidateMatch.case_id == case_id, CandidateMatch.candidate_id == source.id)
        )

        chosen_segment_id = target_match.resume_segment_id
        if chosen_segment_id is None and source_match and source_match.resume_segment_id is not None:
            chosen_segment_id = source_match.resume_segment_id

        self._reassign_candidate_references(db, source.id, target.id)
        self._merge_selection_recommendations(db, source.id, target.id)
        self._merge_pairwise_comparisons(db, case_id, source.id, target.id)

        source_segments = db.scalars(select(ResumeSegment).where(ResumeSegment.candidate_id == source.id)).all()
        for segment in source_segments:
            segment.candidate_id = target.id if segment.id == chosen_segment_id else None

        if chosen_segment_id is not None:
            chosen_segment = db.scalar(select(ResumeSegment).where(ResumeSegment.id == chosen_segment_id))
            if chosen_segment is not None:
                chosen_segment.candidate_id = target.id
                score, score_note = self._score_match(target, chosen_segment)
                target_match.resume_segment_id = chosen_segment.id
                target_match.matched_name = chosen_segment.inferred_name
                target_match.matched_email = chosen_segment.inferred_email
                target_match.confidence = Decimal(f"{score:.2f}")
                target_match.is_duplicate = False
                target_match.notes = f"Merged candidate records. {score_note}"
        else:
            self._set_match_unassigned(target_match, "Merged candidate records. No resume segment assigned.")

        if source_match is not None:
            db.delete(source_match)

        db.delete(source)
        db.commit()
        return self._build_result(db, case_id)

    def _refresh_resume_segments(self, db: Session, documents: list[Document]) -> None:
        ai_client = AIGatewayClient()
        for document in documents:
            if document.status != "ready":
                continue
            if document.document_type not in {"resume_bundle", "resume"}:
                continue

            db.execute(delete(ResumeSegment).where(ResumeSegment.document_id == document.id))
            for block in self._extract_resume_blocks(document):
                segment = ResumeSegment(
                    document_id=document.id,
                    candidate_id=None,
                    inferred_name=block.name,
                    inferred_email=block.email,
                    start_page=block.start_page,
                    end_page=block.end_page,
                    confidence=block.confidence,
                    notes=block.text[:800] if block.text else None,
                )
                db.add(segment)
                db.flush()

                if block.text:
                    profile = self._extract_structured_profile(ai_client, block.text)
                    if profile:
                        segment.parsed_profile = profile
                        extracted_name = profile.get("name")
                        if extracted_name:
                            # Normalize all-caps PDF headers (e.g. "DR. SARAH CHEN") to title case
                            normalized = self._normalize_name_to_title(extracted_name)
                            segment.inferred_name = normalized
                            profile["name"] = normalized

    def _refresh_candidates(self, db: Session, case_id: UUID, documents: list[Document]) -> None:
        existing = db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        by_email = {candidate.email.lower(): candidate for candidate in existing if candidate.email}
        by_name = {self._normalize_name(candidate.full_name): candidate for candidate in existing}

        extracted_identities = self._extract_certificate_identities(documents)
        if not extracted_identities:
            segments = db.scalars(select(ResumeSegment).join(Document).where(Document.case_id == case_id)).all()
            extracted_identities = [
                IdentityBlock(
                    # parsed_profile["name"] is authoritative when AI extraction succeeded
                    name=((segment.parsed_profile or {}).get("name") or segment.inferred_name),
                    email=((segment.parsed_profile or {}).get("email") or segment.inferred_email),
                    text=segment.notes or "",
                    start_page=segment.start_page,
                    end_page=segment.end_page,
                    confidence=segment.confidence,
                )
                for segment in segments
                if segment.inferred_name
                or segment.inferred_email
                or (segment.parsed_profile and segment.parsed_profile.get("name"))
            ]

        for index, identity in enumerate(extracted_identities, start=1):
            candidate = None
            if identity.email:
                candidate = by_email.get(identity.email.lower())
            if candidate is None and identity.name:
                candidate = by_name.get(self._normalize_name(identity.name))

            if candidate is None:
                full_name = identity.name or f"Candidate {index}"
                candidate = Candidate(
                    case_id=case_id,
                    full_name=full_name,
                    email=identity.email,
                    certificate_identifier=f"CERT-{index:03d}",
                    profile={"source": "certificate" if documents else "resume_segment"},
                )
                db.add(candidate)
                db.flush()
                if candidate.email:
                    by_email[candidate.email.lower()] = candidate
                by_name[self._normalize_name(candidate.full_name)] = candidate
                continue

            changed = False
            if identity.email and not candidate.email:
                candidate.email = identity.email
                changed = True
            if identity.name and candidate.full_name != identity.name:
                candidate.full_name = identity.name
                changed = True
            if changed:
                by_name[self._normalize_name(candidate.full_name)] = candidate
                if candidate.email:
                    by_email[candidate.email.lower()] = candidate

    def _refresh_candidate_matches(self, db: Session, case_id: UUID) -> None:
        db.execute(delete(CandidateMatch).where(CandidateMatch.case_id == case_id))
        segments = db.scalars(select(ResumeSegment).join(Document).where(Document.case_id == case_id)).all()
        candidates = db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()

        matched_segment_ids: set[UUID] = set()
        for candidate in candidates:
            best_segment, confidence, notes = self._best_segment_for_candidate(candidate, segments)
            if best_segment:
                duplicate = best_segment.id in matched_segment_ids
                if not duplicate:
                    best_segment.candidate_id = candidate.id
                matched_segment_ids.add(best_segment.id)
                db.add(
                    CandidateMatch(
                        case_id=case_id,
                        candidate_id=candidate.id,
                        resume_segment_id=best_segment.id,
                        matched_name=best_segment.inferred_name,
                        matched_email=best_segment.inferred_email,
                        confidence=confidence,
                        is_duplicate=duplicate,
                        notes=notes,
                    )
                )
            else:
                db.add(
                    CandidateMatch(
                        case_id=case_id,
                        candidate_id=candidate.id,
                        resume_segment_id=None,
                        matched_name=None,
                        matched_email=None,
                        confidence=Decimal("0.00"),
                        is_duplicate=False,
                        notes="No resume segment matched this candidate.",
                    )
                )

    def _build_result(self, db: Session, case_id: UUID) -> CandidateReconciliationResult:
        candidates = db.scalars(select(Candidate).where(Candidate.case_id == case_id)).all()
        matches = db.scalars(select(CandidateMatch).where(CandidateMatch.case_id == case_id)).all()
        segments = db.scalars(
            select(ResumeSegment).join(Document).where(Document.case_id == case_id).order_by(ResumeSegment.start_page)
        ).all()
        documents_by_id = {
            document.id: document for document in db.scalars(select(Document).where(Document.case_id == case_id)).all()
        }
        candidates_by_id = {candidate.id: candidate for candidate in candidates}

        matched_count = sum(1 for match in matches if match.resume_segment_id is not None)
        duplicate_count = sum(1 for match in matches if match.is_duplicate)
        unmatched_segments = sum(1 for segment in segments if segment.candidate_id is None)

        match_details = [
            CandidateMatchDetail(
                id=match.id,
                candidate_id=match.candidate_id,
                candidate_name=candidates_by_id[match.candidate_id].full_name,
                candidate_email=candidates_by_id[match.candidate_id].email,
                resume_segment_id=match.resume_segment_id,
                resume_document_name=documents_by_id[segment.document_id].file_name
                if (segment := self._find_segment(segments, match.resume_segment_id))
                else None,
                segment_start_page=segment.start_page if segment else None,
                segment_end_page=segment.end_page if segment else None,
                inferred_name=segment.inferred_name if segment else None,
                inferred_email=segment.inferred_email if segment else None,
                matched_name=match.matched_name,
                matched_email=match.matched_email,
                confidence=match.confidence,
                is_duplicate=match.is_duplicate,
                notes=match.notes,
            )
            for match in matches
        ]

        return CandidateReconciliationResult(
            summary=CandidateReconciliationSummary(
                case_id=str(case_id),
                candidate_count=len(candidates),
                matched_count=matched_count,
                unmatched_count=max(len(candidates) - matched_count, 0),
                duplicate_count=duplicate_count,
                resume_segment_count=len(segments),
                unmatched_segment_count=unmatched_segments,
            ),
            matches=match_details,
            segments=[ResumeSegmentRead.model_validate(segment) for segment in segments],
        )

    def _extract_resume_blocks(self, document: Document) -> list[IdentityBlock]:
        parse_summary = document.metadata_json.get("parse_summary", {})
        pages = parse_summary.get("pages") or []
        full_text = parse_summary.get("full_text") or ""

        if document.document_type == "resume":
            identity = self._extract_identity(full_text or self._join_pages(pages))
            return [
                IdentityBlock(
                    name=identity["name"],
                    email=identity["email"],
                    text=full_text or self._join_pages(pages),
                    start_page=1,
                    end_page=document.page_count or max(len(pages), 1),
                    confidence=Decimal("0.95"),
                )
            ]

        if len(pages) > 1:
            return self._split_pages_into_segments(pages)
        return self._split_text_into_segments(full_text or self._join_pages(pages))

    def _split_pages_into_segments(self, pages: list[dict[str, Any]]) -> list[IdentityBlock]:
        segments: list[IdentityBlock] = []
        current: IdentityBlock | None = None
        for page in pages:
            text = str(page.get("text", "")).strip()
            identity = self._extract_identity(text)
            page_number = int(page.get("page_number", 1))
            if current is None:
                current = IdentityBlock(
                    identity["name"], identity["email"], text, page_number, page_number, Decimal("0.88")
                )
                continue

            same_identity = self._identity_matches(current.name, current.email, identity["name"], identity["email"])
            if same_identity:
                current = IdentityBlock(
                    current.name or identity["name"],
                    current.email or identity["email"],
                    f"{current.text}\n\n{text}".strip(),
                    current.start_page,
                    page_number,
                    current.confidence,
                )
            else:
                segments.append(current)
                current = IdentityBlock(
                    identity["name"], identity["email"], text, page_number, page_number, Decimal("0.88")
                )

        if current is not None:
            segments.append(current)
        return segments

    def _split_text_into_segments(self, full_text: str) -> list[IdentityBlock]:
        if not full_text.strip():
            return []
        blocks = [block.strip() for block in re.split(r"(?=^Name:\s+)", full_text, flags=re.MULTILINE) if block.strip()]
        if len(blocks) == 1:
            blocks = [block.strip() for block in re.split(r"\n{2,}", full_text) if block.strip()]

        segments: list[IdentityBlock] = []
        for block in blocks:
            identity = self._extract_identity(block)
            segments.append(
                IdentityBlock(
                    name=identity["name"],
                    email=identity["email"],
                    text=block,
                    start_page=1,
                    end_page=1,
                    confidence=Decimal("0.80"),
                )
            )
        return segments

    def _extract_certificate_identities(self, documents: list[Document]) -> list[IdentityBlock]:
        identities: list[IdentityBlock] = []
        for document in documents:
            if document.document_type != "certificate":
                continue
            parse_summary = document.metadata_json.get("parse_summary", {})
            full_text = str(parse_summary.get("full_text") or "")
            if not full_text.strip():
                continue
            blocks = [block.strip() for block in re.split(r"\n{2,}", full_text) if block.strip()]
            for block in blocks:
                identity = self._extract_identity(block)
                if identity["name"] or identity["email"]:
                    identities.append(
                        IdentityBlock(
                            name=identity["name"],
                            email=identity["email"],
                            text=block,
                            start_page=1,
                            end_page=1,
                            confidence=Decimal("0.92"),
                        )
                    )
        return identities

    def _extract_identity(self, text: str) -> dict[str, str | None]:
        email_match = EMAIL_PATTERN.search(text)
        email = email_match.group(0).strip() if email_match else None

        name_match = NAME_LINE_PATTERN.search(text)
        if name_match:
            name = name_match.group(1).strip()
        else:
            name = None
            for raw_line in text.splitlines():
                line = raw_line.strip().strip("-*")
                if TITLE_CASE_NAME_PATTERN.match(line):
                    name = line
                    break
        return {"name": name, "email": email}

    def _best_segment_for_candidate(
        self,
        candidate: Candidate,
        segments: list[ResumeSegment],
    ) -> tuple[ResumeSegment | None, Decimal, str]:
        best_segment: ResumeSegment | None = None
        best_score = 0.0
        best_note = "No viable match."

        for segment in segments:
            score, note = self._score_match(candidate, segment)
            if score > best_score:
                best_segment = segment
                best_score = score
                best_note = note

        if best_segment is None or best_score < 0.45:
            return None, Decimal("0.00"), "No resume segment matched above threshold."
        return best_segment, Decimal(f"{best_score:.2f}"), best_note

    def _score_match(self, candidate: Candidate, segment: ResumeSegment) -> tuple[float, str]:
        candidate_email = candidate.email.lower() if candidate.email else None
        segment_email = segment.inferred_email.lower() if segment.inferred_email else None
        if candidate_email and segment_email and candidate_email == segment_email:
            return 0.99, "Exact email match."

        candidate_name = self._normalize_name(candidate.full_name)
        segment_name = self._normalize_name(segment.inferred_name)
        if candidate_name and segment_name and candidate_name == segment_name:
            return 0.93, "Exact normalized name match."

        if candidate_name and segment_name:
            ratio = SequenceMatcher(a=candidate_name, b=segment_name).ratio()
            if ratio >= 0.75:
                return ratio, "Fuzzy normalized name match."

        return 0.0, "No strong candidate-to-segment signal."

    def _identity_matches(
        self,
        left_name: str | None,
        left_email: str | None,
        right_name: str | None,
        right_email: str | None,
    ) -> bool:
        if left_email and right_email:
            return left_email.lower() == right_email.lower()
        left_normalized = self._normalize_name(left_name)
        right_normalized = self._normalize_name(right_name)
        return bool(left_normalized and right_normalized and left_normalized == right_normalized)

    _PROFILE_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "email": {"type": ["string", "null"]},
            "phone": {"type": ["string", "null"]},
            "location": {"type": ["string", "null"]},
            "linkedin": {"type": ["string", "null"]},
            "clearance": {
                "type": ["object", "null"],
                "properties": {
                    "level": {"type": "string"},
                    "status": {"type": ["string", "null"]},
                },
            },
            "summary": {"type": ["string", "null"]},
            "work_experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "employer": {"type": "string"},
                        "grade_level": {"type": ["string", "null"]},
                        "start_date": {"type": ["string", "null"]},
                        "end_date": {"type": ["string", "null"]},
                        "is_current": {"type": "boolean"},
                        "location": {"type": ["string", "null"]},
                        "is_supervisory": {"type": "boolean"},
                        "team_size": {"type": ["integer", "null"]},
                        "budget": {"type": ["string", "null"]},
                        "highlights": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "degree": {"type": "string"},
                        "field": {"type": ["string", "null"]},
                        "institution": {"type": "string"},
                        "graduation_year": {"type": ["integer", "null"]},
                    },
                },
            },
            "certifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "issuer": {"type": ["string", "null"]},
                        "year": {"type": ["integer", "null"]},
                    },
                },
            },
            "skills": {"type": "array", "items": {"type": "string"}},
            "total_years_experience": {"type": ["integer", "null"]},
        },
        "required": ["name", "work_experience", "education", "certifications", "skills"],
    }

    def _extract_structured_profile(self, ai_client: AIGatewayClient, text: str) -> dict[str, Any] | None:
        """Call the AI gateway to extract a fully structured resume profile from raw text."""
        try:
            response = ai_client.invoke(
                GatewayInvocationRequest(
                    purpose="resume_structured_extraction",
                    system_prompt=(
                        "You are a precise resume parser. Extract all structured information from the "
                        "resume text exactly as stated. Do not infer, embellish, or add information "
                        "not present in the source text. Return only valid JSON."
                    ),
                    prompt=(
                        "Extract the following structured fields from this resume. "
                        "For name: use the full name exactly as written, including honorifics (Dr., Jr., etc.). "
                        "For work_experience: capture every position with exact title, employer, dates, "
                        "supervisory scope, team size, budget managed, and key accomplishments as highlights. "
                        "For education, certifications, and skills: capture every item listed. "
                        "For total_years_experience: calculate from career start to present.\n\n"
                        f"RESUME TEXT:\n{text}"
                    ),
                    temperature=0.0,
                    max_tokens=4000,
                    response_schema=self._PROFILE_SCHEMA,
                )
            )
            if response.accepted and response.structured_output and isinstance(response.structured_output, dict):
                return response.structured_output
            if response.content:
                try:
                    return json.loads(response.content)
                except json.JSONDecodeError:
                    pass
            logger.warning("AI structured extraction returned no usable output")
            return None
        except Exception:
            logger.exception("AI structured profile extraction failed — skipping")
            return None

    def _normalize_name_to_title(self, name: str) -> str:
        """Convert an all-caps name from a PDF header to proper title case."""
        if not name:
            return name
        # Only apply title-case conversion if the name is all-uppercase
        stripped = name.strip()
        if stripped == stripped.upper() and any(c.isalpha() for c in stripped):
            return stripped.title()
        return stripped

    def _normalize_name(self, value: str | None) -> str:
        if not value:
            return ""
        cleaned = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
        return re.sub(r"\s+", " ", cleaned).strip()

    def _join_pages(self, pages: list[dict[str, Any]]) -> str:
        return "\n\n".join(str(page.get("text", "")).strip() for page in pages if str(page.get("text", "")).strip())

    def _find_segment(self, segments: list[ResumeSegment], segment_id: UUID | None) -> ResumeSegment | None:
        if segment_id is None:
            return None
        for segment in segments:
            if segment.id == segment_id:
                return segment
        return None

    def _set_match_unassigned(self, match: CandidateMatch, notes: str) -> None:
        match.resume_segment_id = None
        match.matched_name = None
        match.matched_email = None
        match.confidence = Decimal("0.00")
        match.is_duplicate = False
        match.notes = notes

    def _get_or_create_match(self, db: Session, case_id: UUID, candidate_id: UUID, notes: str) -> CandidateMatch:
        candidate_match = db.scalar(
            select(CandidateMatch).where(CandidateMatch.case_id == case_id, CandidateMatch.candidate_id == candidate_id)
        )
        if candidate_match is not None:
            return candidate_match

        candidate_match = CandidateMatch(
            case_id=case_id,
            candidate_id=candidate_id,
            resume_segment_id=None,
            matched_name=None,
            matched_email=None,
            confidence=Decimal("0.00"),
            is_duplicate=False,
            notes=notes,
        )
        db.add(candidate_match)
        db.flush()
        return candidate_match

    def _merge_candidate_fields(self, source: Candidate, target: Candidate) -> None:
        if not target.email and source.email:
            target.email = source.email
        if not target.certificate_identifier and source.certificate_identifier:
            target.certificate_identifier = source.certificate_identifier

        merged_profile = dict(source.profile or {})
        merged_profile.update(target.profile or {})
        merged_profile["merged_candidate_ids"] = sorted(
            {
                *(str(candidate_id) for candidate_id in (merged_profile.get("merged_candidate_ids") or [])),
                str(source.id),
            }
        )
        target.profile = merged_profile

    def _reassign_candidate_references(self, db: Session, source_candidate_id: UUID, target_candidate_id: UUID) -> None:
        source_candidate_id_str = str(source_candidate_id)
        target_candidate_id_str = str(target_candidate_id)

        for model, column_name in (
            (EvidenceItem, "candidate_id"),
            (CandidateFact, "candidate_id"),
            (CandidateRating, "candidate_id"),
            (ExpertReview, "candidate_id"),
            (ConsensusResult, "candidate_id"),
            (ChallengeFinding, "candidate_id"),
            (InterviewQuestion, "candidate_id"),
            (InterviewResult, "candidate_id"),
            (ModelRun, "candidate_id"),
            (AdjudicationAction, "target_candidate_id"),
        ):
            rows = db.scalars(select(model).where(getattr(model, column_name) == source_candidate_id)).all()
            for row in rows:
                setattr(row, column_name, target_candidate_id)

        recommendations = db.scalars(select(SelectionRecommendation)).all()
        for recommendation in recommendations:
            if recommendation.selectee_candidate_id == source_candidate_id:
                recommendation.selectee_candidate_id = target_candidate_id
            recommendation.alternate_candidate_ids = self._replace_candidate_id_in_list(
                recommendation.alternate_candidate_ids,
                source_candidate_id_str,
                target_candidate_id_str,
            )
            recommendation.interview_slate_candidate_ids = self._replace_candidate_id_in_list(
                recommendation.interview_slate_candidate_ids,
                source_candidate_id_str,
                target_candidate_id_str,
            )
            recommendation.discarded_candidate_ids = self._replace_candidate_id_in_list(
                recommendation.discarded_candidate_ids,
                source_candidate_id_str,
                target_candidate_id_str,
            )

    def _merge_selection_recommendations(
        self, db: Session, source_candidate_id: UUID, target_candidate_id: UUID
    ) -> None:
        recommendations = db.scalars(select(SelectionRecommendation)).all()
        for recommendation in recommendations:
            if recommendation.selectee_candidate_id == source_candidate_id:
                recommendation.selectee_candidate_id = target_candidate_id

    def _merge_pairwise_comparisons(
        self, db: Session, case_id: UUID, source_candidate_id: UUID, target_candidate_id: UUID
    ) -> None:
        comparisons = db.scalars(select(PairwiseComparison).where(PairwiseComparison.case_id == case_id)).all()
        for comparison in comparisons:
            if comparison.left_candidate_id == source_candidate_id:
                comparison.left_candidate_id = target_candidate_id
            if comparison.right_candidate_id == source_candidate_id:
                comparison.right_candidate_id = target_candidate_id
            if comparison.winner_candidate_id == source_candidate_id:
                comparison.winner_candidate_id = target_candidate_id
            if comparison.left_candidate_id == comparison.right_candidate_id:
                db.delete(comparison)

    def _replace_candidate_id_in_list(
        self, values: list[str], source_candidate_id: str, target_candidate_id: str
    ) -> list[str]:
        replaced = [target_candidate_id if value == source_candidate_id else value for value in (values or [])]
        return list(dict.fromkeys(replaced))
