"""Server-sent events for document progress, re-authorised on every event.

The worker publishes `{document_id, status}` to Redis for the whole workspace. Forwarding it as-is
would leak the existence and status of documents in restricted collections, so each event is
checked against the CALLER's current membership and collection access before it is sent, and the
stream ends as soon as the session or the membership is gone.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.tenant import TenantScope, bind_scope
from app.modules.access.policies import Role
from app.modules.documents.models import Document
from app.modules.documents.service import _accessible_ids
from app.modules.identity.deps import session_alive
from app.modules.identity.models import User
from app.modules.processing.events import channel
from app.modules.tenancy.deps import TenantCtx
from app.modules.tenancy.models import Membership

_log = structlog.get_logger("sse")


async def _context(
    sessions: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
) -> tuple[AsyncSession, TenantCtx] | None:
    db = sessions()
    bind_scope(db, TenantScope(user_id=user_id, org_id=org_id))
    membership = await db.scalar(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user_id
        )
    )
    user = await db.get(User, user_id)
    if (
        membership is None
        or user is None
        or not user.is_active
        or not await session_alive(db, user_id, session_id)
    ):
        await db.close()
        return None
    return db, TenantCtx(db=db, user=user, org_id=org_id, role=Role(membership.role))


async def still_allowed(
    sessions: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
) -> bool:
    ctx = await _context(sessions, user_id, org_id, session_id)
    if ctx is None:
        return False
    await ctx[0].close()
    return True


async def can_see_document(
    sessions: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
    document_id: uuid.UUID,
) -> bool:
    found = await _context(sessions, user_id, org_id, session_id)
    if found is None:
        return False
    db, ctx = found
    try:
        row = await db.scalar(
            select(Document.id).where(
                Document.id == document_id,
                Document.organization_id == org_id,
                Document.deleted_at.is_(None),
                Document.collection_id.in_(_accessible_ids(ctx)),
            )
        )
        return row is not None
    finally:
        await db.close()


async def stream_events(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    session_id: uuid.UUID,
    is_disconnected: Callable[[], Awaitable[bool]],
    heartbeat_seconds: float = 15.0,
    poll_seconds: float = 1.0,
) -> AsyncIterator[str]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(org_id))
    yield ": connected\n\n"
    last_check = time.monotonic()
    try:
        while not await is_disconnected():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_seconds)
            if time.monotonic() - last_check >= heartbeat_seconds:
                if not await still_allowed(sessions, user_id, org_id, session_id):
                    _log.info("sse_closed_access_revoked", org_id=str(org_id))
                    return
                last_check = time.monotonic()
                yield ": ping\n\n"
            if not message:
                continue
            try:
                data = json.loads(message["data"])
                document_id = uuid.UUID(data["document_id"])
            except (ValueError, KeyError, TypeError):
                continue
            if not await can_see_document(sessions, user_id, org_id, session_id, document_id):
                if not await still_allowed(sessions, user_id, org_id, session_id):
                    return
                continue  # not allowed to know this document exists: stay silent
            payload = json.dumps(
                {
                    "document_id": str(document_id),
                    "status": data.get("status"),
                    "error_code": data.get("error_code"),
                }
            )
            yield f"event: document\ndata: {payload}\n\n"
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()  # type: ignore[no-untyped-call]
