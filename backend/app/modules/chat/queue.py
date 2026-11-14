"""Bounded, visible, FIFO queue for generation: a few model runs at a time (one on the reference
machine); the rest wait in line, up to a limit.

`enter()` decides atomically (no await between the capacity check and taking a place), so
simultaneous requests cannot all be admitted. A `Ticket` gives its place back however the request
ends: finished, cancelled while waiting, or cancelled after the slot was already handed over.
"""

import asyncio
from collections import deque
from contextlib import suppress


class Ticket:
    def __init__(
        self, queue: "GenerationQueue", position: int, future: "asyncio.Future[None] | None"
    ) -> None:
        self._queue = queue
        self.position = position  # 0: runs immediately; n: n-th in line
        self._future = future
        self._state = "holding" if future is None else "waiting"

    async def ready(self) -> None:
        """Wait until it is this request's turn."""
        if self._future is not None and self._state == "waiting":
            await self._future
            self._state = "holding"

    def release(self) -> None:
        """Give the place back (safe to call more than once, and from any state)."""
        if self._state == "waiting":
            future = self._future
            if future is not None and future.done() and not future.cancelled():
                self._queue._release_slot()  # the slot was handed over just as we gave up
            elif future is not None:
                self._queue._forget(future)
            self._state = "done"
        elif self._state == "holding":
            self._queue._release_slot()
            self._state = "done"


class GenerationQueue:
    def __init__(self, concurrency: int, queue_limit: int) -> None:
        self._concurrency = concurrency
        self._limit = queue_limit
        self._running = 0
        self._waiters: deque[asyncio.Future[None]] = deque()

    @property
    def waiting(self) -> int:
        return len(self._waiters)

    def is_full(self) -> bool:
        return self._running >= self._concurrency and len(self._waiters) >= self._limit

    def enter(self) -> Ticket | None:
        """Take a place, or None if the queue is full. Synchronous on purpose."""
        if self._running < self._concurrency and not self._waiters:
            self._running += 1
            return Ticket(self, 0, None)
        if len(self._waiters) >= self._limit:
            return None
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        return Ticket(self, len(self._waiters), future)

    def _release_slot(self) -> None:
        while self._waiters:
            future = self._waiters.popleft()
            if not future.cancelled():
                future.set_result(None)  # hand the slot to the next in line (running unchanged)
                return
        self._running -= 1

    def _forget(self, future: "asyncio.Future[None]") -> None:
        with suppress(ValueError):
            self._waiters.remove(future)
