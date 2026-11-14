"""The generation queue: atomic admission, FIFO order, and places always given back."""

import asyncio
from contextlib import suppress

from app.modules.chat.queue import GenerationQueue


async def test_requests_run_immediately_up_to_the_concurrency_and_then_wait_in_line() -> None:
    q = GenerationQueue(concurrency=1, queue_limit=2)
    first, second, third = q.enter(), q.enter(), q.enter()
    assert first is not None and second is not None and third is not None
    assert (first.position, second.position, third.position) == (0, 1, 2)
    assert q.waiting == 2 and q.is_full()
    assert q.enter() is None  # over the limit: refused, not queued


async def test_the_next_in_line_runs_when_a_slot_is_released_in_fifo_order() -> None:
    q = GenerationQueue(1, 3)
    order: list[str] = []

    async def worker(name: str, hold: float) -> None:
        ticket = q.enter()
        assert ticket is not None
        try:
            await ticket.ready()
            order.append(name)
            await asyncio.sleep(hold)
        finally:
            ticket.release()

    await asyncio.gather(worker("a", 0.05), worker("b", 0.01), worker("c", 0.01))
    assert order == ["a", "b", "c"]
    assert q.waiting == 0 and not q.is_full() and q.enter() is not None


async def test_a_request_that_gives_up_while_waiting_frees_its_place() -> None:
    q = GenerationQueue(1, 1)
    running = q.enter()
    waiting = q.enter()
    assert running is not None and waiting is not None and q.is_full()
    task = asyncio.create_task(waiting.ready())
    await asyncio.sleep(0)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    waiting.release()
    assert q.waiting == 0 and not q.is_full()
    running.release()
    again = q.enter()
    assert again is not None and again.position == 0  # nothing leaked: the slot is free


async def test_cancellation_after_the_slot_was_handed_over_still_releases_it() -> None:
    q = GenerationQueue(1, 1)
    running = q.enter()
    waiting = q.enter()
    assert running is not None and waiting is not None
    task = asyncio.create_task(waiting.ready())
    await asyncio.sleep(0)
    running.release()  # hands the slot to `waiting`'s future...
    task.cancel()  # ...but its task is cancelled before it resumes
    with suppress(asyncio.CancelledError):
        await task
    waiting.release()
    fresh = q.enter()
    assert fresh is not None and fresh.position == 0 and q.waiting == 0


async def test_releasing_twice_is_harmless() -> None:
    q = GenerationQueue(1, 0)
    ticket = q.enter()
    assert ticket is not None and q.enter() is None
    ticket.release()
    ticket.release()
    again = q.enter()
    assert again is not None and again.position == 0
    assert q.enter() is None  # still exactly one slot, not two


async def test_a_zero_length_queue_admits_only_what_can_run() -> None:
    q = GenerationQueue(2, 0)
    a, b = q.enter(), q.enter()
    assert a is not None and b is not None and q.enter() is None
