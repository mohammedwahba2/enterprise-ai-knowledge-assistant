import asyncio
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db import registry  # noqa: F401  (complete ORM metadata in the worker process)
from app.db.base import to_async_url
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.infrastructure.storage.s3 import ObjectStore, S3ObjectStore
from app.modules.processing import sweeper
from app.modules.processing.events import publish_document_event
from app.modules.processing.indexing import reindex_stale
from app.modules.processing.parsers import OfficeConverter
from app.modules.processing.pipeline import Deps, process_document
from app.worker.celery_app import celery_app

PROCESS_TASK = "knowledge.process_document"


def _embedder(settings: Settings) -> OllamaEmbedder:
    return OllamaEmbedder(
        settings.embedder_url,
        settings.embedding_model,
        settings.embedding_dimensions,
        settings.embedder_timeout_seconds,
    )


@asynccontextmanager
async def _runtime(
    settings: Settings,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], ObjectStore, Redis]]:
    # one short-lived engine per task: the pool must not be shared across forked workers
    engine = create_async_engine(to_async_url(settings.worker_database_url), poolclass=NullPool)
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=5)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False), S3ObjectStore(settings), redis
    finally:
        await engine.dispose()
        await redis.aclose()


async def _enqueue_via_celery(document_id: uuid.UUID, org_id: uuid.UUID) -> None:
    celery_app.send_task(PROCESS_TASK, args=[str(document_id), str(org_id)], queue="ingest")


@celery_app.task(name=PROCESS_TASK)
def process_document_task(document_id: str, org_id: str) -> str:
    settings = get_settings()
    # Celery replaces sys.stdout with a proxy into its own logger: writing there would swallow every
    # line (failures included), so log to the real stream.
    configure_logging(settings.log_level, settings.log_json, stream=sys.__stdout__)

    async def run() -> str:
        async with _runtime(settings) as (sessions, store, redis):

            async def publish(
                org: uuid.UUID, doc: uuid.UUID, status: str, code: str | None
            ) -> None:
                await publish_document_event(redis, org, doc, status, code)

            deps = Deps(
                sessions,
                store,
                OfficeConverter(settings.soffice_binary),
                publish,
                _embedder(settings),
                settings.embedding_batch_size,
            )
            return await process_document(deps, uuid.UUID(document_id), uuid.UUID(org_id))

    return asyncio.run(run())


def _sweep(fn: Callable[..., Awaitable[Any]]) -> Any:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, stream=sys.__stdout__)

    async def run() -> Any:
        async with _runtime(settings) as (sessions, store, _redis):
            return await fn(sessions, store, settings)

    return asyncio.run(run())


@celery_app.task(name="knowledge.requeue_stuck")
def requeue_stuck_task() -> dict[str, int]:
    async def go(sessions: Any, _store: Any, settings: Settings) -> dict[str, int]:
        return await sweeper.requeue_stuck_documents(sessions, _enqueue_via_celery, settings)

    return _sweep(go)  # type: ignore[no-any-return]


@celery_app.task(name="knowledge.requeue_transient")
def requeue_transient_task() -> int:
    async def go(sessions: Any, _store: Any, settings: Settings) -> int:
        return await sweeper.requeue_transient_failures(sessions, _enqueue_via_celery, settings)

    return _sweep(go)  # type: ignore[no-any-return]


@celery_app.task(name="knowledge.reindex_stale")
def reindex_stale_task(org_id: str | None = None, document_id: str | None = None) -> dict[str, Any]:
    """Re-embed chunks not embedded by the configured model (run after changing the model).

    `celery -A app.worker.celery_app call knowledge.reindex_stale` re-indexes everything;
    pass `--args='["<org id>"]'` to limit it to one workspace.
    """

    async def go(sessions: Any, _store: Any, settings: Settings) -> dict[str, Any]:
        result = await reindex_stale(
            sessions,
            _embedder(settings),
            settings.embedding_batch_size,
            org_id=uuid.UUID(org_id) if org_id else None,
            document_id=uuid.UUID(document_id) if document_id else None,
        )
        return {"documents": result.documents, "chunks": result.chunks, "stopped": result.stopped}

    return _sweep(go)  # type: ignore[no-any-return]


@celery_app.task(name="knowledge.purge_deleted")
def purge_deleted_task() -> int:
    async def go(sessions: Any, store: Any, _settings: Settings) -> int:
        return await sweeper.purge_deleted_objects(sessions, store)

    return _sweep(go)  # type: ignore[no-any-return]


@celery_app.task(name="knowledge.purge_orphans")
def purge_orphans_task() -> int:
    async def go(sessions: Any, store: Any, _settings: Settings) -> int:
        return await sweeper.purge_orphan_prefixes(sessions, store)

    return _sweep(go)  # type: ignore[no-any-return]


structlog.get_logger("worker").info("worker_module_loaded")
