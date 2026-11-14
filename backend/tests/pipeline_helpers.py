"""Run the real ingestion pipeline in tests (real Postgres as `worker_rw`, real SeaweedFS)."""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.base import to_async_url
from app.infrastructure.embeddings.base import Embedder
from app.infrastructure.storage.s3 import S3ObjectStore
from app.modules.processing.parsers import OfficeConverter
from app.modules.processing.pipeline import Deps, process_document
from tests.fake_embedder import FakeEmbedder

Publish = Callable[[uuid.UUID, uuid.UUID, str, str | None], Awaitable[None]]


async def _noop(_o: uuid.UUID, _d: uuid.UUID, _s: str, _c: str | None) -> None:
    return None


async def run_pipeline(
    settings: Settings,
    worker_db_url: str,
    org_id: str,
    document_id: str,
    *,
    converter: OfficeConverter | None = None,
    publish: Publish | None = None,
    embedder: Embedder | None = None,
) -> str:
    engine = create_async_engine(to_async_url(worker_db_url), poolclass=NullPool)
    deps = Deps(
        async_sessionmaker(engine, expire_on_commit=False),
        S3ObjectStore(settings),
        converter or OfficeConverter("/nonexistent/soffice"),
        publish or _noop,
        embedder or FakeEmbedder(),
        embedding_batch_size=8,
    )
    try:
        return await process_document(deps, uuid.UUID(document_id), uuid.UUID(org_id))
    finally:
        await engine.dispose()


def worker_sessions(worker_db_url: str):  # type: ignore[no-untyped-def]
    """A sessionmaker connected as the worker role (what the sweeper and pipeline really use)."""
    engine = create_async_engine(to_async_url(worker_db_url), poolclass=NullPool)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
