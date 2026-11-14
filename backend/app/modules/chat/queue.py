"""Bounded, visible queue for generation: one model run at a time on the reference machine."""

import asyncio


class GenerationQueue:
    def __init__(self, concurrency: int, queue_limit: int) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._limit = queue_limit
        self._waiting = 0

    @property
    def waiting(self) -> int:
        return self._waiting

    def would_wait(self) -> bool:
        return self._semaphore.locked()

    def is_full(self) -> bool:
        """True when a new request would exceed the bounded queue (reject instead of queueing)."""
        return self._semaphore.locked() and self._waiting >= self._limit

    async def acquire(self) -> int:
        """Wait for a slot; returns how many requests were waiting ahead (0 if none)."""
        if not self._semaphore.locked():
            await self._semaphore.acquire()
            return 0
        self._waiting += 1
        position = self._waiting
        try:
            await self._semaphore.acquire()
        finally:
            self._waiting -= 1
        return position

    def release(self) -> None:
        self._semaphore.release()
