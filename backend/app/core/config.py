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
    # Failures caused by a dependency being down (storage, embedder) are retried automatically.
    transient_retry_seconds: int = 300
    max_transient_attempts: int = 6

    # --- embeddings (Ollama on the host; see docs/PLAN.md section 7) ---
    embedder_url: str = "http://localhost:11434"
    embedding_model: str = "bge-m3"
    embedding_dimensions: int = Field(default=1024, ge=8, le=4096)
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    embedder_timeout_seconds: float = Field(default=120.0, ge=1.0)
    # Chunks without a vector from the CURRENT model (documents that predate embeddings, or a
    # changed EMBEDDING_MODEL) are re-embedded in the background, this many documents per run.
    reindex_batch_documents: int = Field(default=25, ge=1, le=500)
    # Keep the model loaded between requests (Ollama unloads idle models after 5 minutes, and the
    # next query would pay the load time).
    embedder_keep_alive: str = "30m"

    # --- retrieval (stage 7) ---
    query_embedder_timeout_seconds: float = Field(default=8.0, ge=1.0)
    retrieval_candidates: int = Field(default=40, ge=5, le=200)  # per leg, before fusion
    # Fusion parameters chosen by the stage 7 grid (docs/eval/stage7-retrieval.md): the textbook
    # k=60 is nearly flat across ranks, so lexical consensus drowned out the vector ranking and
    # cross-language retrieval collapsed (Arabic->English recall@5 0.00); a small k with the vector
    # leg weighted 2x keeps same-language gains and cross-language retrieval.
    rrf_k: int = Field(default=3, ge=1)
    rrf_vector_weight: int = Field(default=2, ge=1, le=10)
    hnsw_ef_search: int = Field(default=100, ge=10, le=1000)
    hnsw_max_scan: int = Field(default=20000, ge=1000)
    search_rate_per_minute: int = Field(default=60, ge=1)

    # --- grounded generation (stage 8) ---
    llm_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    llm_num_ctx: int = Field(default=8192, ge=2048)
    llm_max_output_tokens: int = Field(default=600, ge=64, le=4096)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=120.0, ge=5.0)
    llm_keep_alive: str = "30m"
    # One generation at a time on the reference machine; others wait (bounded) and see "queued".
    llm_max_concurrency: int = Field(default=1, ge=1, le=8)
    llm_queue_limit: int = Field(default=4, ge=0, le=50)
    chat_rate_per_minute: int = Field(default=20, ge=1)
    answer_context_chunks: int = Field(default=6, ge=1, le=12)
    # Retrieval gate: refuse WITHOUT calling the model below these evidence levels. Calibrated on
    # the calibration split and verified on the test split (docs/eval/stage8-answers.md).
    gate_min_similarity: float = Field(default=0.45, ge=0.0, le=1.0)
    gate_min_fts_score: float = Field(default=1.0, ge=0.0)  # used only when vectors are unavailable
    # Citation verification: a cited sentence is supported when its numbers all occur in the cited
    # passage AND (it shares enough words with it OR is semantically close).
    verify_min_lexical: float = Field(default=0.4, ge=0.0, le=1.0)
    verify_min_similarity: float = Field(default=0.5, ge=0.0, le=1.0)

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
