import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncpg
from redis.asyncio import Redis

from app.core.config import Settings


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    latency_ms: float
    detail: str | None = None


Check = Callable[[], Awaitable[CheckResult]]


async def _timed(
    name: str, probe: Callable[[], Awaitable[str | None]], seconds: float
) -> CheckResult:
    """Run a probe; failures report only the exception class, never connection strings."""
    started = time.perf_counter()
    try:
        detail = await asyncio.wait_for(probe(), seconds)
        return CheckResult(name, True, _ms(started), detail)
    except Exception as exc:
        return CheckResult(name, False, _ms(started), type(exc).__name__ + _hint(exc))


def _hint(exc: Exception) -> str:
    return f": {exc}" if isinstance(exc, _SafeError) else ""


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


class _SafeError(Exception):
    """Exception whose message is safe to expose in readiness output."""


def build_checks(settings: Settings) -> list[Check]:
    timeout = settings.readiness_timeout_seconds

    async def postgres() -> str | None:
        conn = await asyncpg.connect(settings.database_url, timeout=timeout)
        try:
            version = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
        finally:
            await conn.close()
        if version is None:
            raise _SafeError("pgvector extension is not installed")
        return f"pgvector {version}"

    async def redis() -> str | None:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=timeout)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return None

    async def object_store() -> str | None:
        # Authenticated HEAD on the bucket: proves reachability, credentials and that it exists.
        from app.infrastructure.storage.s3 import S3ObjectStore

        await S3ObjectStore(settings).check()
        return f"bucket {settings.s3_bucket}"

    return [
        lambda: _timed("postgres", postgres, timeout),
        lambda: _timed("redis", redis, timeout),
        lambda: _timed("object_store", object_store, timeout),
    ]
