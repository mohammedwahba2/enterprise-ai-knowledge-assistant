from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI
from redis.asyncio import Redis

from app.api import health
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.readiness import Check, build_checks
from app.db.base import make_engine, make_sessionmaker
from app.infrastructure.embeddings.base import Embedder
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.infrastructure.llm.base import ChatModel
from app.infrastructure.llm.ollama import OllamaChat
from app.infrastructure.storage.s3 import ObjectStore, S3ObjectStore
from app.modules.chat.queue import GenerationQueue
from app.modules.chat.router import router as chat_router
from app.modules.documents.router import router as documents_router
from app.modules.identity.email import EmailSender, SmtpEmailSender
from app.modules.identity.passwords import PasswordService
from app.modules.identity.rate_limit import RateLimiter
from app.modules.identity.router import router as auth_router
from app.modules.processing.queue import Enqueue, celery_enqueue
from app.modules.retrieval.router import router as retrieval_router
from app.modules.tenancy.router import invitations_router
from app.modules.tenancy.router import router as orgs_router


def create_app(
    settings: Settings | None = None,
    checks: list[Check] | None = None,
    *,
    email_sender: EmailSender | None = None,
    store: ObjectStore | None = None,
    enqueue: Enqueue | None = None,
    embedder: Embedder | None = None,
    chat: ChatModel | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    engine = make_engine(settings.database_url)
    # Short timeouts: a dead Redis must turn into a fast 503, not a hung request.
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)

    @asynccontextmanager
    async def lifespan(app_: FastAPI) -> AsyncIterator[None]:
        try:  # tolerate an unavailable store at boot: readiness reports it, uploads retry
            await app_.state.store.ensure_bucket()
        except Exception:
            structlog.get_logger("app").error("bucket_not_ready", exc_info=True)
        yield
        await engine.dispose()
        await redis.aclose()

    app = FastAPI(
        title="Enterprise AI Knowledge Assistant API",
        version="0.2.0",
        docs_url="/api/docs" if settings.app_env != "prod" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.app_env != "prod" else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.readiness_checks = checks if checks is not None else build_checks(settings)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.redis = redis
    app.state.limiter = RateLimiter(redis)
    app.state.passwords = PasswordService(
        memory_kib=settings.argon2_memory_kib,
        time_cost=settings.argon2_time_cost,
        parallelism=settings.argon2_parallelism,
    )
    app.state.email_sender = email_sender or SmtpEmailSender(settings)
    app.state.store = store or S3ObjectStore(settings)
    app.state.enqueue = enqueue or celery_enqueue
    # Query embedding is interactive: a short timeout (a slow model must not hang search; search
    # degrades to full text instead).
    app.state.embedder = embedder or OllamaEmbedder(
        settings.embedder_url,
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.query_embedder_timeout_seconds,
        keep_alive=settings.embedder_keep_alive,
    )
    app.state.chat = chat or OllamaChat(
        settings.llm_url,
        settings.llm_model,
        num_ctx=settings.llm_num_ctx,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        keep_alive=settings.llm_keep_alive,
    )
    app.state.generation_queue = GenerationQueue(
        settings.llm_max_concurrency, settings.llm_queue_limit
    )

    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth_router)
    v1.include_router(orgs_router)
    v1.include_router(documents_router)
    v1.include_router(retrieval_router)
    v1.include_router(chat_router)
    v1.include_router(invitations_router)
    app.include_router(v1)

    structlog.get_logger("app").info("startup", env=settings.app_env)
    return app


app = create_app()
