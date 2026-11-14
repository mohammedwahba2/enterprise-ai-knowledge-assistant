"""Document progress events over Redis pub/sub (worker publishes, the API's SSE endpoint relays)."""

import json
import uuid

from redis.asyncio import Redis


def channel(org_id: uuid.UUID | str) -> str:
    return f"docevents:{org_id}"


async def publish_document_event(
    redis: Redis,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    status: str,
    error_code: str | None = None,
) -> None:
    """Best effort: progress is also available by polling, so a Redis hiccup must not fail a job."""
    payload = json.dumps(
        {"document_id": str(document_id), "status": status, "error_code": error_code}
    )
    try:
        await redis.publish(channel(org_id), payload)
    except Exception:
        return
