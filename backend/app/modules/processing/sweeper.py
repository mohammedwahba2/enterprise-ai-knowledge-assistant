"""Periodic housekeeping run by Celery beat. Every function is safe to run at any time."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.infrastructure.storage.s3 import ObjectStore, StorageUnavailableError
from app.modules.documents.models import Document
from app.modules.processing.models import IngestionJob
from app.modules.tenancy.models import Organization

_log = structlog.get_logger("sweeper")
Enqueue = Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]


async def requeue_stuck_documents(
    sessions: async_sessionmaker[AsyncSession],
    enqueue: Enqueue,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, int]:
    """Documents whose task was lost (uploaded but never started, or started and never finished).

    Retried up to `max_processing_attempts` times in total, then marked failed: a PDF that keeps
    killing the worker must not loop forever.
    """
    now = now or datetime.now(UTC)
    uploaded_cutoff = now - timedelta(seconds=settings.stuck_uploaded_seconds)
    running_cutoff = now - timedelta(seconds=settings.stuck_running_seconds)
    requeued = abandoned = 0
    async with sessions() as s:
        stuck = (
            await s.scalars(
                select(Document)
                .where(
                    Document.deleted_at.is_(None),
                    ((Document.status == "uploaded") & (Document.updated_at < uploaded_cutoff))
                    | (
                        Document.status.in_(("parsing", "chunking"))
                        & (Document.updated_at < running_cutoff)
                    ),
                )
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        ).all()
        for doc in stuck:
            attempts = (
                await s.scalar(
                    select(func.count())
                    .select_from(IngestionJob)
                    .where(IngestionJob.document_id == doc.id)
                )
                or 0
            )
            if attempts >= settings.max_processing_attempts:
                doc.status = "failed"
                doc.error_code = "PROCESSING_CRASHED"
                doc.error_detail = "Processing did not finish after several attempts."
                for job in (
                    await s.scalars(
                        select(IngestionJob).where(
                            IngestionJob.document_id == doc.id, IngestionJob.status == "running"
                        )
                    )
                ).all():
                    job.status = "abandoned"
                    job.finished_at = now
                abandoned += 1
            else:
                doc.updated_at = now  # back off: do not re-queue again until it is stuck again
                requeued += 1
                await enqueue(doc.id, doc.organization_id)
        await s.commit()
    if requeued or abandoned:
        _log.warning("stuck_documents", requeued=requeued, abandoned=abandoned)
    return {"requeued": requeued, "abandoned": abandoned}


async def purge_deleted_objects(
    sessions: async_sessionmaker[AsyncSession], store: ObjectStore
) -> int:
    """Remove the objects of soft-deleted documents whose purge failed or never ran."""
    purged = 0
    async with sessions() as s:
        docs = (
            await s.scalars(
                select(Document)
                .where(Document.deleted_at.is_not(None), Document.purged_at.is_(None))
                .limit(200)
            )
        ).all()
        for doc in docs:
            try:
                await store.delete(doc.storage_key)
                await store.delete(f"{doc.storage_key}.viewer.pdf")
            except StorageUnavailableError:
                _log.error("purge_failed", document_id=str(doc.id))
                continue
            doc.purged_at = datetime.now(UTC)
            purged += 1
        await s.commit()
    return purged


async def purge_orphan_prefixes(
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    min_age: timedelta = timedelta(hours=1),
    now: datetime | None = None,
) -> int:
    """Delete objects of workspaces that no longer exist (e.g. a failed cleanup after deleting one).

    Only prefixes whose newest object is older than `min_age` are touched, so a workspace that is
    being created right now is never raced. Scans the whole `org/` prefix: fine at this scale.
    """
    now = now or datetime.now(UTC)
    objects = await store.list_objects("org/")
    newest: dict[str, datetime] = {}
    for key, modified in objects:
        parts = key.split("/")
        if len(parts) >= 2:
            org = parts[1]
            newest[org] = max(newest.get(org, modified), modified)
    if not newest:
        return 0
    async with sessions() as s:
        known = {str(i) for i in (await s.scalars(select(Organization.id))).all()}
    removed = 0
    for org, modified in newest.items():
        if org not in known and now - modified > min_age:
            removed += await store.delete_prefix(f"org/{org}/")
            _log.warning("orphan_prefix_purged", org=org)
    return removed
