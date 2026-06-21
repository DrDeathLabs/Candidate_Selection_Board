from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = Field(default="api", alias="SERVICE_NAME")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(default="database", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="selection_board", alias="POSTGRES_DB")
    postgres_user: str = Field(default="selection_board", alias="POSTGRES_USER")
    postgres_password: str = Field(default="change-me", alias="POSTGRES_PASSWORD")

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")

    s3_endpoint_url: str = Field(default="http://object-storage:9000", alias="S3_ENDPOINT_URL")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    minio_bucket: str = Field(default="selection-board", alias="MINIO_BUCKET")
    minio_root_user: str = Field(default="minioadmin", alias="MINIO_ROOT_USER")
    minio_root_password: str = Field(default="change-me", alias="MINIO_ROOT_PASSWORD")

    opensearch_url: str = Field(default="http://search:9200", alias="OPENSEARCH_URL")
    parser_service_url: str = Field(default="http://parser:8010", alias="PARSER_SERVICE_URL")
    ai_gateway_url: str = Field(default="http://ai-gateway:8020", alias="AI_GATEWAY_URL")
    virus_scanner_host: str = Field(default="virus-scanner", alias="VIRUS_SCANNER_HOST")
    virus_scanner_port: int = Field(default=3310, alias="VIRUS_SCANNER_PORT")

    oidc_issuer_url: str = Field(default="https://login.example.gov", alias="OIDC_ISSUER_URL")
    oidc_audience: str = Field(default="selection-board", alias="OIDC_AUDIENCE")
    oidc_jwks_url: str = Field(default="https://login.example.gov/.well-known/jwks.json", alias="OIDC_JWKS_URL")

    ai_default_provider: str = Field(default="ollama", alias="AI_DEFAULT_PROVIDER")
    ai_allowed_models: str = Field(
        default="gpt-oss:120b-cloud,gpt-4.1,claude-sonnet,gemini-2.5-pro",
        alias="AI_ALLOWED_MODELS",
    )

    cors_origins_raw: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    celery_broker_url: str = Field(default="redis://redis:6379/0", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://redis:6379/1", alias="CELERY_RESULT_BACKEND")

    dev_auth_bypass: bool = Field(default=False, alias="DEV_AUTH_BYPASS")
    redis_password: str | None = Field(default=None, alias="REDIS_PASSWORD")
    postgres_ssl_mode: str = Field(default="prefer", alias="POSTGRES_SSL_MODE")

    # Session management (FISMA Moderate AC-10, AC-11, AC-12)
    session_cookie_name: str = Field(default="sb_session", alias="SESSION_COOKIE_NAME")
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")
    session_idle_timeout_minutes: int = Field(default=15, alias="SESSION_IDLE_TIMEOUT_MINUTES")
    session_absolute_timeout_hours: int = Field(default=8, alias="SESSION_ABSOLUTE_TIMEOUT_HOURS")
    max_concurrent_sessions: int = Field(default=3, alias="MAX_CONCURRENT_SESSIONS")

    # Account lockout (FISMA Moderate AC-7)
    max_failed_login_attempts: int = Field(default=5, alias="MAX_FAILED_LOGIN_ATTEMPTS")
    account_lockout_minutes: int = Field(default=30, alias="ACCOUNT_LOCKOUT_MINUTES")

    # Password policy (FISMA Moderate IA-5)
    password_min_length: int = Field(default=14, alias="PASSWORD_MIN_LENGTH")
    password_history_count: int = Field(default=5, alias="PASSWORD_HISTORY_COUNT")
    password_max_age_days: int = Field(default=90, alias="PASSWORD_MAX_AGE_DAYS")

    # TOTP / MFA (FISMA Moderate IA-2)
    totp_issuer_name: str = Field(default="Candidate Selection Board", alias="TOTP_ISSUER_NAME")
    totp_encryption_key: str = Field(default="dev-only-totp-key-000000000000000", alias="TOTP_ENCRYPTION_KEY")

    # OIDC group prefix for role mapping
    oidc_group_prefix: str = Field(default="selection-board-", alias="OIDC_GROUP_PREFIX")

    # OIDC redirect base URL (used in callback to build redirect_uri)
    oidc_redirect_base_url: str = Field(default="http://127.0.0.1:8610", alias="OIDC_REDIRECT_BASE_URL")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def allowed_models(self) -> list[str]:
        return [model.strip() for model in self.ai_allowed_models.split(",") if model.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
