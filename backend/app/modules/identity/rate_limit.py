import functools
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import ParamSpec, TypeVar

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import AppError

_log = structlog.get_logger("rate_limit")
P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0


def digest(value: str) -> str:
    """Keys never contain raw emails (PII) or IPs."""
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def fail_closed(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    """If Redis cannot be reached we cannot enforce limits, so the request is refused (503).

    Brute-force protection must not silently disappear during an outage. Authentication of
    existing sessions does not use Redis at all (see `deps.current_user`).
    """

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await fn(*args, **kwargs)
        except (RedisError, OSError, TimeoutError):
            _log.error("rate_limiter_unavailable", exc_info=True)
            raise AppError(
                503,
                "SERVICE_UNAVAILABLE",
                "Service temporarily unavailable. Try again shortly.",
                headers={"Retry-After": "5"},
            ) from None

    return wrapper


class RateLimiter:
    """Fixed-window counters in Redis. Every operation fails closed (see `fail_closed`)."""

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @fail_closed
    async def blocked(self, key: str, limit: int) -> Decision:
        """Is the counter already at/over the limit? Does not increment."""
        raw = await self._r.get(key)
        if raw is not None and int(raw) >= limit:
            ttl = await self._r.ttl(key)
            return Decision(False, max(ttl, 1))
        return Decision(True)

    @fail_closed
    async def hit(self, key: str, window: int) -> int:
        """Increment and return the new count; the window starts at the first hit."""
        count = int(await self._r.incr(key))
        if count == 1:
            await self._r.expire(key, window)
        return count

    @fail_closed
    async def hit_and_check(self, key: str, limit: int, window: int) -> Decision:
        count = await self.hit(key, window)
        if count > limit:
            return Decision(False, max(int(await self._r.ttl(key)), 1))
        return Decision(True)

    @fail_closed
    async def reset(self, key: str) -> None:
        await self._r.delete(key)
