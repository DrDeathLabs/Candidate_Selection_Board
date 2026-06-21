from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.enums import ExpertAgentType, RoleName
from app.models.auth import User
from app.models.evaluation import ExpertAgent
from app.models.system import PromptTemplate, SystemSetting


@dataclass(frozen=True, slots=True)
class ExpertAgentSeed:
    agent_type: ExpertAgentType
    display_name: str
    description: str
    config: dict[str, Any]


def agent_config(**overrides: Any) -> dict[str, Any]:
    return {
        "provider": "ollama",
        "model": "gpt-oss:120b-cloud",
        "temperature": 0.2,
        "max_tokens": 4000,
        **overrides,
    }


DEFAULT_EXPERT_AGENTS: tuple[ExpertAgentSeed, ...] = (
    ExpertAgentSeed(
        agent_type=ExpertAgentType.PD_ANALYST,
        display_name="PD Analyst",
        description="Extracts job requirements, role type, critical factors, and rubric recommendations from the position description.",
        config=agent_config(phase="position-analysis", requires_candidate_context=False),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.RESUME_EVIDENCE_ANALYST,
        display_name="Resume Evidence Analyst",
        description="Extracts only evidence-supported candidate facts and flags weak or unsupported claims.",
        config=agent_config(phase="candidate-facts", requires_candidate_context=True),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.SUPERVISORY_EXPERT,
        display_name="Supervisory Expert",
        description="Evaluates leadership, supervision, contractor oversight, span of control, and grade-level scope.",
        config=agent_config(phase="expert-council", focus="leadership"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.TECHNICAL_DOMAIN_EXPERT,
        display_name="Technical Domain Expert",
        description="Assesses technical relevance and depth against the position-specific requirements.",
        config=agent_config(phase="expert-council", focus="technical-alignment"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.MISSION_ALIGNMENT_EXPERT,
        display_name="Mission Alignment Expert",
        description="Measures mission-domain alignment against the position context and operational environment.",
        config=agent_config(phase="expert-council", focus="mission-fit"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.BUDGET_AND_ACQUISITION_EXPERT,
        display_name="Budget and Acquisition Expert",
        description="Evaluates budget authority, procurement, vendor management, and contract oversight experience.",
        config=agent_config(phase="expert-council", focus="budget-acquisition"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.CYBERSECURITY_EXPERT,
        display_name="Cybersecurity Expert",
        description="Evaluates cybersecurity responsibilities and integration when relevant to the position.",
        config=agent_config(phase="expert-council", conditional="pd-relevant"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.OPERATIONS_EXPERT,
        display_name="Operations Expert",
        description="Assesses production ownership, sustainment, incident responsibility, and service reliability experience.",
        config=agent_config(phase="expert-council", focus="operations"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.MODERNIZATION_EXPERT,
        display_name="Modernization Expert",
        description="Evaluates transformation, Agile, DevSecOps, cloud, automation, AI, and delivery outcomes.",
        config=agent_config(phase="expert-council", focus="modernization"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.SKEPTIC_REVIEWER,
        display_name="Skeptic Reviewer",
        description="Challenges vague claims, weak evidence, inflated scope, and potential overrating.",
        config=agent_config(phase="challenge", focus="evidence-skepticism"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.COMPLIANCE_REVIEWER,
        display_name="Compliance Reviewer",
        description="Checks that findings stay job-related, evidence-based, and suitable for defensible selection decisions.",
        config=agent_config(phase="challenge", focus="compliance"),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.COMPARATIVE_REVIEWER,
        display_name="Comparative Reviewer",
        description="Performs comparative review only after individual candidate evaluations are complete.",
        config=agent_config(phase="comparison", requires_candidate_context=True),
    ),
    ExpertAgentSeed(
        agent_type=ExpertAgentType.SELECTION_REVIEWER,
        display_name="Selection Reviewer",
        description="Synthesizes the full record into a recommended selectee, ranked alternates, and rationale.",
        config=agent_config(phase="selection", requires_candidate_context=True),
    ),
)

DEFAULT_PROMPT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "name": "pd-analysis",
        "version": "v1",
        "purpose": "position_analysis",
        "template_body": "Analyze the position description and return structured duties, critical factors, role type, and rubric recommendations with evidence anchors.",
        "expected_schema": {
            "duties": [],
            "critical_factors": [],
            "role_type": "",
            "recommended_dimensions": [],
        },
    },
    {
        "name": "resume-evidence-extraction",
        "version": "v1",
        "purpose": "candidate_fact_extraction",
        "template_body": "Extract only facts supported by the candidate record. Include page references, confidence, and unsupported claims.",
        "expected_schema": {
            "facts": [],
            "unsupported_claims": [],
            "confidence_notes": [],
        },
    },
    {
        "name": "selection-recommendation",
        "version": "v1",
        "purpose": "selection_recommendation",
        "template_body": "Recommend a selectee and ranked alternates using evidence, rubric fit, consensus, pairwise outcomes, and adjudication history.",
        "expected_schema": {
            "selectee_candidate_id": "",
            "alternate_candidate_ids": [],
            "rationale": "",
            "confidence": 0,
        },
    },
)

DEFAULT_SYSTEM_SETTINGS: tuple[dict[str, Any], ...] = (
    {
        "setting_key": "ai.provider_configuration",
        "setting_value": {
            "default_provider": "ollama",
            "providers": {
                "ollama": {
                    "enabled": True,
                    "label": "Ollama",
                    "base_url": "http://host.docker.internal:11434",
                    "default_model": "gpt-oss:120b-cloud",
                    "api_key_env_var": "",
                    "notes": "Local Ollama runtime on this workstation.",
                },
                "openai": {
                    "enabled": True,
                    "label": "OpenAI",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-4.1",
                    "api_key_env_var": "OPENAI_API_KEY",
                    "notes": "",
                },
                "claude": {
                    "enabled": True,
                    "label": "Claude",
                    "base_url": "https://api.anthropic.com/v1",
                    "default_model": "claude-sonnet",
                    "api_key_env_var": "ANTHROPIC_API_KEY",
                    "notes": "",
                },
                "gemini": {
                    "enabled": True,
                    "label": "Gemini",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta",
                    "default_model": "gemini-2.5-pro",
                    "api_key_env_var": "GEMINI_API_KEY",
                    "notes": "",
                },
            },
        },
        "classification": "ai",
        "description": "Provider configuration used by the AI gateway and expert agents.",
    },
    {
        "setting_key": "security.default_data_sensitivity",
        "setting_value": {"value": "moderate"},
        "classification": "security",
        "description": "Default case sensitivity classification for new review cases.",
    },
    {
        "setting_key": "evaluation.minimum_evidence_confidence",
        "setting_value": {"value": 0.7},
        "classification": "evaluation",
        "description": "Minimum confidence threshold before candidate claims are considered sufficiently supported.",
    },
)


def seed_expert_agents() -> tuple[int, int]:
    created = 0
    updated = 0
    with SessionLocal() as db:
        for seed in DEFAULT_EXPERT_AGENTS:
            statement = select(ExpertAgent).where(ExpertAgent.agent_type == seed.agent_type.value)
            agent = db.execute(statement).scalar_one_or_none()
            if agent is None:
                db.add(
                    ExpertAgent(
                        agent_type=seed.agent_type.value,
                        display_name=seed.display_name,
                        description=seed.description,
                        enabled=True,
                        config=seed.config,
                    )
                )
                created += 1
                continue

            changed = False
            if agent.display_name != seed.display_name:
                agent.display_name = seed.display_name
                changed = True
            if agent.description != seed.description:
                agent.description = seed.description
                changed = True
            if agent.config != seed.config:
                agent.config = seed.config
                changed = True
            if not agent.enabled:
                agent.enabled = True
                changed = True
            if changed:
                updated += 1
        db.commit()
    return created, updated


def seed_prompt_templates() -> tuple[int, int]:
    created = 0
    updated = 0
    with SessionLocal() as db:
        for seed in DEFAULT_PROMPT_TEMPLATES:
            statement = select(PromptTemplate).where(
                PromptTemplate.name == seed["name"],
                PromptTemplate.version == seed["version"],
            )
            template = db.execute(statement).scalar_one_or_none()
            if template is None:
                db.add(PromptTemplate(**seed, is_active=True))
                created += 1
                continue

            changed = False
            for field in ("purpose", "template_body", "expected_schema"):
                if getattr(template, field) != seed[field]:
                    setattr(template, field, seed[field])
                    changed = True
            if not template.is_active:
                template.is_active = True
                changed = True
            if changed:
                updated += 1
        db.commit()
    return created, updated


def seed_system_settings() -> tuple[int, int]:
    created = 0
    updated = 0
    with SessionLocal() as db:
        for seed in DEFAULT_SYSTEM_SETTINGS:
            statement = select(SystemSetting).where(SystemSetting.setting_key == seed["setting_key"])
            setting = db.execute(statement).scalar_one_or_none()
            if setting is None:
                db.add(SystemSetting(**seed))
                created += 1
                continue

            changed = False
            for field in ("setting_value", "classification", "description"):
                if getattr(setting, field) != seed[field]:
                    setattr(setting, field, seed[field])
                    changed = True
            if changed:
                updated += 1
        db.commit()
    return created, updated


def seed_admin_user() -> tuple[int, int]:
    """Create the initial SYSTEM_ADMINISTRATOR account if none exists.

    Password is taken from ADMIN_INITIAL_PASSWORD env var. If not set, a
    random password is generated and printed once to stdout. After first login
    the admin should use /auth/password/change to rotate it.
    """
    from app.services.auth_service import hash_password

    created = 0
    skipped = 0
    with SessionLocal() as db:
        existing = db.query(User).filter(User.roles.contains(["system_administrator"])).first()
        if existing:
            skipped += 1
            return created, skipped

        password = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
        if not password:
            import secrets as _sec

            # Generate a FISMA-compliant 20-char password
            password = (
                _sec.token_hex(2).upper()[:2] + _sec.token_hex(2).lower()[:2] + "!7" + _sec.token_urlsafe(12)[:12]
            )
            print(f"[bootstrap] Generated admin password: {password}")
            print("[bootstrap] Store this securely — it will not be shown again.")

        admin = User(
            username="admin",
            email="admin@selection-board.local",
            display_name="System Administrator",
            password_hash=hash_password(password),
            roles=[RoleName.SYSTEM_ADMINISTRATOR.value, RoleName.CASE_OWNER.value],
            is_mfa_required=False,
            is_active=True,
            created_by="bootstrap",
        )
        db.add(admin)
        db.commit()
        created += 1
        print(f"[bootstrap] Created admin user 'admin' (id={admin.id})")
    return created, skipped


def seed_all() -> dict[str, tuple[int, int]]:
    return {
        "admin_user": seed_admin_user(),
        "expert_agents": seed_expert_agents(),
        "prompt_templates": seed_prompt_templates(),
        "system_settings": seed_system_settings(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap seed data for the selection board platform.")
    parser.add_argument(
        "command",
        choices=("seed-all", "seed-expert-agents", "seed-prompts", "seed-settings", "seed-admin"),
        help="Bootstrap operation to run.",
    )
    args = parser.parse_args()

    if args.command == "seed-all":
        results = seed_all()
        for key, (created, updated) in results.items():
            print(f"{key}: created={created} updated/skipped={updated}")
        return

    if args.command == "seed-admin":
        created, skipped = seed_admin_user()
        print(f"admin_user: created={created} skipped={skipped}")
        return

    if args.command == "seed-expert-agents":
        created, updated = seed_expert_agents()
        print(f"expert_agents: created={created} updated={updated}")
        return

    if args.command == "seed-prompts":
        created, updated = seed_prompt_templates()
        print(f"prompt_templates: created={created} updated={updated}")
        return

    created, updated = seed_system_settings()
    print(f"system_settings: created={created} updated={updated}")


if __name__ == "__main__":
    main()
