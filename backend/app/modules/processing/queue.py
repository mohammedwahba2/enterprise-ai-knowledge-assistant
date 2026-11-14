"""Enqueue a document for processing (API side). Failures never fail the HTTP request."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable

import structlog

_log = structlog.get_logger("queue")
Enqueue = Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]


async def celery_enqueue(document_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Hand the document to the worker. If the broker is down the document stays `uploaded` and
    the sweeper re-queues it, so an outage delays processing instead of losing the upload."""
    from app.worker.celery_app import celery_app
    from app.worker.tasks import PROCESS_TASK

    try:
        await asyncio.to_thread(
            celery_app.send_task, PROCESS_TASK, args=[str(document_id), str(org_id)], queue="ingest"
        )
    except Exception:
        _log.error("enqueue_failed", document_id=str(document_id), exc_info=True)
