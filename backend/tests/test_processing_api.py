import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

import pytest
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, broker_url
from app.db.base import make_engine, make_sessionmaker
from app.modules.documents import events
from app.modules.documents.models import Document
from app.modules.processing.events import channel
from tests import files
from tests.conftest import Enqueued
from tests.pdfgen import PageSpec, make_pdf
from tests.tenancy_helpers import Person, World

TEXT = "Employees receive twenty five working days of paid annual leave per calendar year."
TEXT2 = "Unused days may be carried over for a maximum of five days until the end of March."


async def setup(world: World) -> tuple[Person, str, str]:
    owner = await world.person("Owner")
    oid = (await world.org(owner, "Acme"))["id"]
    return owner, oid, await world.general(owner, oid)


async def up(owner: Person, oid: str, cid: str, name: str, data: bytes) -> str:
    return str((await owner.upload(oid, cid, (name, data))).json()[0]["document"]["id"])


# =============================================================== enqueue on upload


async def test_only_newly_created_documents_are_queued_for_processing(
    world: World, enqueued: Enqueued
) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([TEXT, TEXT2])])
    first = await owner.upload(oid, cid, ("a.pdf", pdf), ("bad.pdf", b"MZ nope"))
    again = await owner.upload(oid, cid, ("a-again.pdf", pdf))  # duplicate
    assert [r["outcome"] for r in first.json()] == ["created", "rejected"]
    assert again.json()[0]["outcome"] == "duplicate"
    created_id = first.json()[0]["document"]["id"]
    assert enqueued.calls == [(created_id, oid)]


async def test_a_broken_queue_never_fails_the_upload(world: World) -> None:
    async def explode(*_: object) -> None:
        raise ConnectionError("broker down")

    world.enqueued = explode
    owner, oid, cid = await setup(world)
    r = await owner.upload(oid, cid, ("a.pdf", make_pdf([PageSpec([TEXT])])))
    assert r.status_code == 200 and r.json()[0]["outcome"] == "created"
    doc = (await owner.get(f"/orgs/{oid}/documents/{r.json()[0]['document']['id']}")).json()
    assert doc["status"] == "uploaded"  # stays queued-for-later; the sweeper picks it up


# =============================================================== document fields, pages, summary


async def test_processed_documents_expose_language_page_summary_and_pages(world: World) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([TEXT, TEXT2]), PageSpec([], image_ratio=0.9), PageSpec([TEXT2])])
    doc_id = await up(owner, oid, cid, "report.pdf", pdf)
    assert (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages")).json() == []  # nothing yet
    await world.process(oid, doc_id)
    doc = (await owner.get(f"/orgs/{oid}/documents/{doc_id}")).json()
    assert (doc["status"], doc["error_code"], doc["language"], doc["page_count"]) == (
        "ready_partial",
        "PARTIAL_TEXT",
        "en",
        3,
    )
    assert doc["page_summary"] == {"total": 3, "text": 2, "image_only": 1, "garbled": 0}
    pages = (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages")).json()
    assert [(p["page_number"], p["extraction_state"]) for p in pages] == [
        (1, "text"),
        (2, "image_only"),
        (3, "text"),
    ]
    one = (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages/1")).json()
    assert one["extraction_state"] == "text" and "twenty five working days" in one["text"]
    two = (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages/2")).json()
    assert (
        two["extraction_state"] == "image_only" and two["text"] == ""
    )  # unusable pages expose no text
    assert (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages/99")).status_code == 404
    assert (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages/0")).status_code == 422
    assert (await owner.get(f"/orgs/{oid}/documents/{doc_id}/pages/abc")).status_code == 422


async def test_page_access_follows_collection_access(world: World) -> None:
    owner, oid, _ = await setup(world)
    listed, unlisted = await world.person("Listed"), await world.person("Unlisted")
    await world.join(owner, oid, listed, "member")
    await world.join(owner, oid, unlisted, "member")
    secret = await world.collection(owner, oid, "Board", "restricted", members=[listed.user_id])
    doc_id = await up(owner, oid, secret, "minutes.pdf", make_pdf([PageSpec([TEXT, TEXT2])]))
    await world.process(oid, doc_id)
    assert (await listed.get(f"/orgs/{oid}/documents/{doc_id}/pages/1")).status_code == 200
    for path in ("/pages", "/pages/1", ""):
        assert (await unlisted.get(f"/orgs/{oid}/documents/{doc_id}{path}")).status_code == 404, (
            path
        )


async def test_status_summary_counts_only_what_the_caller_may_see(world: World) -> None:
    owner, oid, cid = await setup(world)
    unlisted = await world.person("Unlisted")
    await world.join(owner, oid, unlisted, "member")
    secret = await world.collection(owner, oid, "Board", "restricted", members=[])
    good = await up(owner, oid, cid, "good.pdf", make_pdf([PageSpec([TEXT, TEXT2])]))
    scan = await up(owner, oid, cid, "scan.pdf", make_pdf([PageSpec([], image_ratio=0.9)]))
    hidden = await up(owner, oid, secret, "hidden.pdf", make_pdf([PageSpec([TEXT2, TEXT])]))
    for d in (good, scan, hidden):
        await world.process(oid, d)
    s = (await owner.get(f"/orgs/{oid}/documents/summary")).json()
    assert s == {
        "total": 3,
        "by_status": {"ready": 2, "unsupported_scanned": 1},
        "needs_attention": 1,
    }
    seen = (await unlisted.get(f"/orgs/{oid}/documents/summary")).json()
    assert seen == {
        "total": 2,
        "by_status": {"ready": 1, "unsupported_scanned": 1},
        "needs_attention": 1,
    }


# =============================================================== reprocess


async def test_reprocess_rules(world: World, enqueued: Enqueued) -> None:
    owner, oid, cid = await setup(world)
    viewer = await world.person("Viewer")
    await world.join(owner, oid, viewer, "viewer")
    doc_id = await up(owner, oid, cid, "locked.pdf", b"%PDF-1.4\n" + b"\x00\xff" * 3000)
    busy = await owner.post(f"/orgs/{oid}/documents/{doc_id}/reprocess")
    assert busy.status_code == 409 and busy.json()["code"] == "ALREADY_PROCESSING"  # still queued
    assert await world.process(oid, doc_id) == "failed"
    enqueued.calls.clear()
    assert (await viewer.post(f"/orgs/{oid}/documents/{doc_id}/reprocess")).status_code == 403
    assert (await owner.post(f"/orgs/{oid}/documents/{uuid.uuid4()}/reprocess")).status_code == 404
    ok = await owner.post(f"/orgs/{oid}/documents/{doc_id}/reprocess")
    assert ok.status_code == 202 and ok.json() == {"status": "queued"}
    assert enqueued.calls == [(doc_id, oid)]
    doc = (await owner.get(f"/orgs/{oid}/documents/{doc_id}")).json()
    assert (doc["status"], doc["error_code"]) == ("uploaded", None)


# =============================================================== server-sent events


@pytest.fixture
async def stream_deps(
    settings: Settings,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], Redis]]:
    engine = make_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    try:
        yield make_sessionmaker(engine), redis
    finally:
        await engine.dispose()
        await redis.aclose()


async def session_of(person: Person) -> uuid.UUID:
    """The caller's session id: the refresh family behind its access token."""
    from app.modules.identity.tokens import decode_access_token

    token = next(c.value for c in person.client.cookies.jar if c.name == "ka_at")
    return decode_access_token(Settings(app_env="test"), token or "").session_id


def open_stream(
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    person: Person,
    org_id: str,
    session_id: uuid.UUID,
    **kw: Any,
) -> AsyncIterator[str]:
    async def never() -> bool:
        return False

    return events.stream_events(
        sessions, redis, user_id=uuid.UUID(person.user_id), org_id=uuid.UUID(org_id),
        session_id=session_id, is_disconnected=kw.pop("is_disconnected", never), **kw,
    )  # fmt: skip


async def publish(redis: Redis, org_id: str, doc_id: str, status: str) -> None:
    await redis.publish(
        channel(org_id), json.dumps({"document_id": doc_id, "status": status, "error_code": None})
    )


async def next_item(stream: AsyncIterator[str], timeout: float = 5.0) -> str:
    return await asyncio.wait_for(anext(stream), timeout)


async def test_events_reach_people_who_can_see_the_document(
    world: World, stream_deps: tuple[async_sessionmaker[AsyncSession], Redis]
) -> None:
    sessions, redis = stream_deps
    owner, oid, cid = await setup(world)
    doc_id = await up(owner, oid, cid, "a.pdf", make_pdf([PageSpec([TEXT])]))
    stream = open_stream(sessions, redis, owner, oid, await session_of(owner))
    assert await next_item(stream) == ": connected\n\n"
    await asyncio.sleep(0.2)
    await publish(redis, oid, doc_id, "parsing")
    item = await next_item(stream)
    assert item.startswith("event: document\ndata: ")
    assert json.loads(item.split("data: ", 1)[1]) == {
        "document_id": doc_id,
        "status": "parsing",
        "error_code": None,
    }
    await stream.aclose()  # type: ignore[attr-defined]


async def test_events_for_restricted_documents_never_reach_unlisted_members(
    world: World, stream_deps: tuple[async_sessionmaker[AsyncSession], Redis]
) -> None:
    sessions, redis = stream_deps
    owner, oid, cid = await setup(world)
    listed, unlisted = await world.person("Listed"), await world.person("Unlisted")
    await world.join(owner, oid, listed, "member")
    await world.join(owner, oid, unlisted, "member")
    secret = await world.collection(owner, oid, "Board", "restricted", members=[listed.user_id])
    hidden = await up(owner, oid, secret, "minutes.pdf", make_pdf([PageSpec([TEXT])]))
    shown = await up(owner, oid, cid, "public.pdf", make_pdf([PageSpec([TEXT2])]))
    s_unlisted = open_stream(sessions, redis, unlisted, oid, await session_of(unlisted))
    s_listed = open_stream(sessions, redis, listed, oid, await session_of(listed))
    await next_item(s_unlisted), await next_item(s_listed)  # connected
    await asyncio.sleep(0.2)
    await publish(redis, oid, hidden, "ready")
    await publish(redis, oid, shown, "ready")
    got_listed = [
        json.loads((await next_item(s_listed)).split("data: ", 1)[1])["document_id"]
        for _ in range(2)
    ]
    assert set(got_listed) == {hidden, shown}
    first_for_unlisted = json.loads((await next_item(s_unlisted)).split("data: ", 1)[1])
    assert (
        first_for_unlisted["document_id"] == shown
    )  # the restricted document's event was silently dropped
    with pytest.raises(TimeoutError):
        await next_item(s_unlisted, timeout=1.0)
    await s_unlisted.aclose(), await s_listed.aclose()  # type: ignore[attr-defined]


async def test_the_stream_ends_when_access_is_revoked(
    world: World, stream_deps: tuple[async_sessionmaker[AsyncSession], Redis]
) -> None:
    sessions, redis = stream_deps
    owner, oid, _ = await setup(world)
    member = await world.person("Member")
    await world.join(owner, oid, member, "member")
    stream = open_stream(
        sessions,
        redis,
        member,
        oid,
        await session_of(member),
        heartbeat_seconds=0.3,
        poll_seconds=0.1,
    )
    await next_item(stream)
    ping = await next_item(stream)
    assert ping == ": ping\n\n"  # still allowed
    mid = await world.member_id(owner, oid, member.user_id)
    await owner.delete(f"/orgs/{oid}/members/{mid}")
    with pytest.raises(StopAsyncIteration):  # the next heartbeat notices and closes the stream
        for _ in range(20):
            await next_item(stream, timeout=3.0)


async def test_the_stream_ends_when_the_session_is_signed_out(
    world: World, stream_deps: tuple[async_sessionmaker[AsyncSession], Redis]
) -> None:
    sessions, redis = stream_deps
    owner, oid, _ = await setup(world)
    stream = open_stream(
        sessions,
        redis,
        owner,
        oid,
        await session_of(owner),
        heartbeat_seconds=0.3,
        poll_seconds=0.1,
    )
    await next_item(stream)
    assert (await owner.post("/auth/sign-out")).status_code == 204
    with pytest.raises(StopAsyncIteration):
        for _ in range(20):
            await next_item(stream, timeout=3.0)


async def test_the_stream_stops_when_the_client_disconnects(
    world: World, stream_deps: tuple[async_sessionmaker[AsyncSession], Redis]
) -> None:
    sessions, redis = stream_deps
    owner, oid, _ = await setup(world)
    state = {"gone": False}

    async def disconnected() -> bool:
        return state["gone"]

    stream = open_stream(
        sessions,
        redis,
        owner,
        oid,
        await session_of(owner),
        is_disconnected=disconnected,
        poll_seconds=0.1,
    )
    await next_item(stream)
    state["gone"] = True
    with pytest.raises(StopAsyncIteration):
        await next_item(stream, timeout=3.0)


async def test_garbage_events_are_ignored(
    world: World, stream_deps: tuple[async_sessionmaker[AsyncSession], Redis]
) -> None:
    sessions, redis = stream_deps
    owner, oid, cid = await setup(world)
    doc_id = await up(owner, oid, cid, "a.pdf", make_pdf([PageSpec([TEXT])]))
    stream = open_stream(sessions, redis, owner, oid, await session_of(owner))
    await next_item(stream)
    await asyncio.sleep(0.2)
    for junk in (
        "not json",
        json.dumps({"document_id": "nope"}),
        json.dumps({"status": "x"}),
        json.dumps([1, 2]),
    ):
        await redis.publish(channel(oid), junk)
    await publish(redis, oid, doc_id, "ready")
    assert json.loads((await next_item(stream)).split("data: ", 1)[1])["status"] == "ready"
    await stream.aclose()  # type: ignore[attr-defined]


# =============================================================== worker wiring


def test_celery_is_wired_for_the_ingest_queue() -> None:
    from app.worker.celery_app import celery_app
    from app.worker.tasks import PROCESS_TASK

    assert celery_app.conf.task_default_queue == "ingest"
    assert PROCESS_TASK in celery_app.tasks
    assert {
        "knowledge.requeue_stuck",
        "knowledge.requeue_transient",
        "knowledge.reindex_stale",
        "knowledge.purge_deleted",
        "knowledge.purge_orphans",
    } <= set(celery_app.tasks)
    assert set(celery_app.conf.beat_schedule) == {
        "requeue-stuck-documents",
        "requeue-transient-failures",
        "purge-deleted-objects",
        "purge-orphan-prefixes",
    }
    assert (
        celery_app.conf.task_acks_late is False
        and celery_app.conf.worker_max_tasks_per_child <= 100
    )


def test_broker_url_uses_a_separate_redis_database() -> None:
    s = Settings(app_env="test", redis_url="redis://:pw@redis:6379/0")
    assert broker_url(s) == "redis://:pw@redis:6379/1"
    assert (
        broker_url(s.model_copy(update={"celery_broker_url": "redis://other/5"}))
        == "redis://other/5"
    )


async def test_the_real_enqueue_function_swallows_broker_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.processing import queue
    from app.worker.celery_app import celery_app

    def broken(*_a: object, **_k: object) -> None:
        raise ConnectionError("no broker")

    monkeypatch.setattr(celery_app, "send_task", broken)
    await queue.celery_enqueue(uuid.uuid4(), uuid.uuid4())  # must not raise


async def test_the_real_enqueue_function_sends_the_expected_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.processing import queue
    from app.worker.celery_app import celery_app
    from app.worker.tasks import PROCESS_TASK

    sent: list[tuple[str, list[str], str]] = []

    def capture(name: str, args: list[str], queue: str) -> None:
        sent.append((name, args, queue))

    monkeypatch.setattr(celery_app, "send_task", capture)
    d, o = uuid.uuid4(), uuid.uuid4()
    await queue.celery_enqueue(d, o)
    assert sent == [(PROCESS_TASK, [str(d), str(o)], "ingest")]
    with suppress(Exception):
        _ = files, select, update, Document
