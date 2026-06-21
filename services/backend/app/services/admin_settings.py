from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.case import Document, ReviewCase
from app.models.evaluation import ExpertAgent
from app.models.operations import AuditEvent, ExportPackage
from app.models.system import ModelRun, SystemSetting
from app.schemas.admin import (
    AIProviderConfig,
    AISettingsRead,
    AISettingsUpdate,
    OperationsOverviewRead,
    SecurityOverviewRead,
)

AI_PROVIDER_SETTING_KEY = "ai.provider_configuration"


def default_ai_settings() -> AISettingsRead:
    settings = get_settings()
    return AISettingsRead(
        default_provider=settings.ai_default_provider,
        providers={
            "ollama": AIProviderConfig(
                enabled=True,
                label="Ollama",
                base_url="http://host.docker.internal:11434",
                default_model="gpt-oss:120b-cloud",
                api_key_env_var="",
                notes="Local Ollama runtime on this workstation.",
            ),
            "openai": AIProviderConfig(
                enabled=True,
                label="OpenAI",
                base_url="https://api.openai.com/v1",
                default_model="gpt-4.1",
                api_key_env_var="OPENAI_API_KEY",
                notes="",
            ),
            "claude": AIProviderConfig(
                enabled=True,
                label="Claude",
                base_url="https://api.anthropic.com/v1",
                default_model="claude-sonnet",
                api_key_env_var="ANTHROPIC_API_KEY",
                notes="",
            ),
            "gemini": AIProviderConfig(
                enabled=True,
                label="Gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                default_model="gemini-2.5-pro",
                api_key_env_var="GEMINI_API_KEY",
                notes="",
            ),
        },
    )


class AdminSettingsService:
    def get_ai_settings(self, db: Session) -> AISettingsRead:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == AI_PROVIDER_SETTING_KEY))
        if setting is None:
            payload = default_ai_settings()
            setting = SystemSetting(
                setting_key=AI_PROVIDER_SETTING_KEY,
                setting_value=payload.model_dump(mode="json"),
                classification="ai",
                description="Provider configuration used by the AI gateway and expert agents.",
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
            return payload
        return AISettingsRead.model_validate(setting.setting_value)

    def update_ai_settings(self, db: Session, payload: AISettingsUpdate) -> AISettingsRead:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == AI_PROVIDER_SETTING_KEY))
        if setting is None:
            setting = SystemSetting(
                setting_key=AI_PROVIDER_SETTING_KEY,
                setting_value={},
                classification="ai",
                description="Provider configuration used by the AI gateway and expert agents.",
            )
            db.add(setting)

        setting.setting_value = payload.model_dump(mode="json")
        setting.classification = "ai"
        setting.description = "Provider configuration used by the AI gateway and expert agents."
        db.commit()
        db.refresh(setting)
        return AISettingsRead.model_validate(setting.setting_value)

    def get_operations_overview(self, db: Session) -> OperationsOverviewRead:
        ai_settings = self.get_ai_settings(db)

        case_status_counts = count_values(db.scalars(select(ReviewCase.status)).all())
        document_status_counts = count_values(db.scalars(select(Document.status)).all())
        model_run_status_counts = count_values(db.scalars(select(ModelRun.status)).all())

        return OperationsOverviewRead(
            active_case_count=sum(count for status, count in case_status_counts.items() if status != "closed"),
            case_status_counts=case_status_counts,
            document_status_counts=document_status_counts,
            model_run_status_counts=model_run_status_counts,
            enabled_agent_count=len(db.scalars(select(ExpertAgent.id).where(ExpertAgent.enabled.is_(True))).all()),
            export_queue_count=len(
                db.scalars(select(ExportPackage.id).where(ExportPackage.status.in_(("pending", "running")))).all()
            ),
            default_provider=ai_settings.default_provider,
        )

    def get_security_overview(self, db: Session) -> SecurityOverviewRead:
        ai_settings = self.get_ai_settings(db)
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        sensitivity_counts = count_values(db.scalars(select(ReviewCase.data_sensitivity)).all())
        audit_event_count_last_24h = len(db.scalars(select(AuditEvent.id).where(AuditEvent.occurred_at >= since)).all())
        admin_change_count_last_24h = len(
            db.scalars(
                select(AuditEvent.id).where(
                    AuditEvent.event_type == "admin_setting_change",
                    AuditEvent.occurred_at >= since,
                )
            ).all()
        )
        provider_secret_dependencies = [
            {
                "provider": provider_key,
                "enabled": provider.enabled,
                "api_key_env_var": provider.api_key_env_var,
                "base_url": provider.base_url,
            }
            for provider_key, provider in ai_settings.providers.items()
        ]

        return SecurityOverviewRead(
            sensitivity_counts=sensitivity_counts,
            outside_enrichment_case_count=len(
                db.scalars(select(ReviewCase.id).where(ReviewCase.outside_enrichment_allowed.is_(True))).all()
            ),
            audit_event_count_last_24h=audit_event_count_last_24h,
            admin_change_count_last_24h=admin_change_count_last_24h,
            provider_secret_dependencies=provider_secret_dependencies,
            checklist=[],
        )


def count_values(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts
