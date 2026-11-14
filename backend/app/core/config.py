from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0123456789abcdef"  # noqa: S105


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables only."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql://knowledge:change-me@localhost:5432/knowledge"
    redis_url: str = "redis://localhost:6379/0"
    # S3-compatible object store (SeaweedFS). The store is never exposed to browsers.
    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: SecretStr = SecretStr("change-me-key")
    s3_secret_key: SecretStr = SecretStr("change-me-secret")
    s3_bucket: str = "knowledge-documents"
    s3_region: str = "us-east-1"
    readiness_timeout_seconds: float = 2.0

    # --- identity ---
    app_origin: str = "http://localhost:8080"
    cookie_secure: bool = False  # must be true in prod (enforced below)
    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_issuer: str = "knowledge-assistant"
    jwt_audience: str = "knowledge-assistant-api"
    access_ttl_seconds: int = Field(default=900, ge=60)
    refresh_ttl_days: int = Field(default=14, ge=1)
    refresh_family_max_days: int = Field(default=30, ge=1)
    refresh_grace_seconds: int = Field(default=10, ge=0)
    reset_ttl_minutes: int = Field(default=30, ge=5)

    # --- background processing ---
    worker_database_url: str = "postgresql://worker_rw:change-me@localhost:5432/knowledge"
    celery_broker_url: str | None = None  # defaults to the Redis server, database 1
    soffice_binary: str = "soffice"
    stuck_uploaded_seconds: int = 120
    stuck_running_seconds: int = 900
    max_processing_attempts: int = 3

    # --- documents ---
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    max_files_per_upload: int = Field(default=10, ge=1, le=50)

    # --- tenancy ---
    max_owned_orgs_per_user: int = Field(default=10, ge=1)
    invitation_ttl_days: int = Field(default=7, ge=1)
    invitation_org_hourly_limit: int = 50
    invitation_accept_ip_limit: int = 30

    # argon2id (OWASP-aligned defaults: 64 MiB, 3 iterations, 1 lane)
    argon2_memory_kib: int = Field(default=65536, ge=8)
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_parallelism: int = Field(default=1, ge=1)

    # rate limits (fixed windows, Redis)
    signin_account_limit: int = 5  # failures per (ip, email) per window
    signin_ip_limit: int = 30  # failures per ip per window
    signin_window_seconds: int = 900
    signup_ip_limit: int = 10
    signup_window_seconds: int = 3600
    reset_ip_limit: int = 10
    reset_email_limit: int = 3
    reset_window_seconds: int = 3600

    # email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    email_from: str = "Knowledge Assistant <no-reply@example.test>"

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        if self.app_env == "prod":
            problems = []
            if self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
                problems.append("JWT_SECRET must be set")
            if len(self.jwt_secret.get_secret_value()) < 32:
                problems.append("JWT_SECRET must be at least 32 characters")
            if self.s3_secret_key.get_secret_value() == "change-me-secret":
                problems.append("S3_SECRET_KEY must be set")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true")
            if not self.app_origin.startswith("https://"):
                problems.append("APP_ORIGIN must be https")
            if problems:
                raise ValueError("; ".join(problems))
        elif len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return self


def broker_url(settings: Settings) -> str:
    """Celery's broker: the app's Redis server, but a separate logical database (1)."""
    if settings.celery_broker_url:
        return settings.celery_broker_url
    base, _, _ = settings.redis_url.rpartition("/")
    return f"{base}/1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
