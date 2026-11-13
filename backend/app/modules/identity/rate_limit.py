import hashlib
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0


def digest(value: str) -> str:
    """Keys never contain raw emails (PII) or IPs."""
    return hashlib.sha256(value.encode()).hexdigest()[:20]


class RateLimiter:
    """Fixed-window counters in Redis."""

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def blocked(self, key: str, limit: int) -> Decision:
        """Is the counter already at/over the limit? Does not increment."""
        raw = await self._r.get(key)
        if raw is not None and int(raw) >= limit:
            ttl = await self._r.ttl(key)
            return Decision(False, max(ttl, 1))
        return Decision(True)

    async def hit(self, key: str, window: int) -> int:
        """Increment and return the new count; the window starts at the first hit."""
        count = int(await self._r.incr(key))
        if count == 1:
            await self._r.expire(key, window)
        return count

    async def hit_and_check(self, key: str, limit: int, window: int) -> Decision:
        count = await self.hit(key, window)
        if count > limit:
            return Decision(False, max(int(await self._r.ttl(key)), 1))
        return Decision(True)

    async def reset(self, key: str) -> None:
        await self._r.delete(key)


class SessionRevocations:
    """Revoked session ids, kept only as long as an access token could still be valid."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._r = redis
        self._ttl = ttl_seconds

    async def revoke(self, session_id: str) -> None:
        await self._r.set(f"revoked:sid:{session_id}", "1", ex=self._ttl)

    async def is_revoked(self, session_id: str) -> bool:
        return bool(await self._r.exists(f"revoked:sid:{session_id}"))
