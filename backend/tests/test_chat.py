"""Grounded answering end to end: real Postgres (RLS), real pipeline and retrieval, scripted model."""

import asyncio
import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.modules.access.policies import Role
from app.modules.chat import service
from app.modules.chat.queue import GenerationQueue
from tests.fake_chat import FakeChat
from tests.fake_embedder import FakeEmbedder
from tests.tenancy_helpers import Person, World
from tests.test_retrieval import CANARY, Team, team

GROUNDED = "Employees receive twenty five working days of paid annual leave per calendar year [1]."
QUESTION = "how many working days of paid annual leave do employees receive per year"


def lenient(world: World, **changes: Any) -> None:
    """The fake hash embedder gives lower cosines than a real model: use a low gate in tests."""
    world.settings = world.settings.model_copy(update={"gate_min_similarity": 0.2, **changes})


def parse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def names(events: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [e for e, _ in events]


async def conversation(person: Person, oid: str) -> str:
    r = await person.post(f"/orgs/{oid}/conversations", {})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def ask(
    person: Person, oid: str, cid: str, question: str = QUESTION, **extra: Any
) -> tuple[int, list[tuple[str, dict[str, Any]]]]:
    r = await person.post(
        f"/orgs/{oid}/conversations/{cid}/messages", {"content": question, **extra}
    )
    return r.status_code, parse(r.text) if r.status_code == 200 else [("http", r.json())]


async def setup(world: World, reply: Any = GROUNDED, **fake: Any) -> tuple[Team, FakeChat, str]:
    chat = FakeChat(reply, **fake)
    world.chat = chat
    lenient(world)
    t = await team(world)
    return t, chat, await conversation(t.people["viewer"], t.oid)


# ------------------------------------------------------------------ the happy path


async def test_a_grounded_answer_streams_verifies_and_persists(world: World) -> None:
    t, chat, cid = await setup(world)
    viewer = t.people["viewer"]
    status, events = await ask(viewer, t.oid, cid)
    assert status == 200
    kinds = names(events)
    assert kinds[0] == "meta" and kinds[1] == "retrieval" and kinds[-2:] == ["final", "done"]
    assert "delta" in kinds and all(e["provisional"] for k, e in events if k == "delta")
    final = dict(events)["final"]
    assert final["text"] == GROUNDED and final["partially_supported"] is False
    (citation,) = final["citations"]
    assert citation["marker"] == 1 and citation["document_title"] == "leave policy"
    assert citation["page_start"] == 1 and "twenty five working days" in citation["quote"]
    assert citation["support_score"] > 0.4
    # the model was shown a numbered, delimited source and the question
    shown = chat.calls[0][1].content
    assert "[1] (leave policy, p. 1)" in shown and "<<<" in shown and shown.endswith(QUESTION)

    detail = (await viewer.get(f"/orgs/{t.oid}/conversations/{cid}")).json()
    user_msg, answer = detail["messages"]
    assert (user_msg["role"], answer["role"]) == ("user", "assistant")
    assert answer["status"] == "complete" and answer["content"] == GROUNDED
    assert answer["citations"][0]["available"] is True and answer["citations"][0]["quote"]
    assert detail["title"] == QUESTION[:60]


async def test_metrics_and_retrieval_logs_are_recorded(world: World) -> None:
    t, _, cid = await setup(world)
    viewer = t.people["viewer"]
    await ask(viewer, t.oid, cid)
    async with world.scoped_db(t.oid, viewer.user_id) as s:
        row = (
            await s.execute(
                text(
                    "select status, model, latency_ms, first_token_ms, prompt_tokens, completion_tokens, "
                    "retrieval_params from messages where role = 'assistant'"
                )
            )
        ).one()
        logs = (await s.execute(text("select rank, used from retrieval_logs order by rank"))).all()
    assert row.status == "complete" and row.model == "fake-chat"
    assert row.latency_ms >= 0 and row.first_token_ms >= 0 and row.prompt_tokens == 500
    assert row.retrieval_params["gate"]["passed"] is True
    assert logs and logs[0].rank == 1 and any(used for _, used in logs)


# ------------------------------------------------------------------ the gate and NO_ANSWER


async def test_weak_evidence_is_refused_without_calling_the_model(world: World) -> None:
    t, chat, cid = await setup(world)
    status, events = await ask(t.people["viewer"], t.oid, cid, "zzzz qqqq xxxx wwww")
    assert status == 200 and names(events)[-2:] == ["refused", "done"]
    refused = dict(events)["refused"]
    assert (
        refused["reason"] == "NOT_FOUND"
        and refused["text"] == "I couldn't find this in your documents."
    )
    assert chat.calls == []  # the model was never called
    assert "delta" not in names(events) and "retrieval" not in names(events)


@pytest.mark.parametrize(
    "reply", ["NO_ANSWER", "  NO_ANSWER", "NO_ANSWER.", "NO_ANSWER\nThe sources don't say."]
)
async def test_the_no_answer_protocol_is_never_shown_as_an_answer(world: World, reply: str) -> None:
    t, chat, cid = await setup(world, reply)
    _, events = await ask(t.people["viewer"], t.oid, cid)
    assert (
        names(events)[-2:] == ["refused", "done"]
        and dict(events)["refused"]["reason"] == "NO_ANSWER"
    )
    assert "delta" not in names(events), "NO_ANSWER must never leak into the stream"
    assert "NO_ANSWER" not in json.dumps(events)
    assert chat.calls


async def test_an_answer_that_merely_starts_with_no_is_not_mistaken_for_a_refusal(
    world: World,
) -> None:
    reply = "Nothing in the policy limits it: employees receive twenty five working days of paid annual leave [1]."
    t, _, cid = await setup(world, reply)
    _, events = await ask(t.people["viewer"], t.oid, cid)
    assert names(events)[-2:] == ["final", "done"]


async def test_an_answer_without_a_verifiable_citation_is_not_shown_as_one(world: World) -> None:
    t, _, cid = await setup(world, "Employees receive twenty five working days of annual leave.")
    _, events = await ask(t.people["viewer"], t.oid, cid)
    assert dict(events)["refused"]["reason"] == "UNSUPPORTED" and "final" not in names(events)
    detail = (await t.people["viewer"].get(f"/orgs/{t.oid}/conversations/{cid}")).json()
    assert detail["messages"][1]["status"] == "refused" and detail["messages"][1]["citations"] == []


async def test_a_wrong_figure_with_a_citation_is_refused(world: World) -> None:
    t, _, cid = await setup(world, "Employees receive 300 working days of paid annual leave [1].")
    _, events = await ask(t.people["viewer"], t.oid, cid)
    assert dict(events)["refused"]["reason"] == "UNSUPPORTED"


async def test_invented_markers_are_stripped_and_the_answer_is_flagged(world: World) -> None:
    reply = GROUNDED[:-1] + "[9]. Employees also receive twenty five days of leave [1]."
    t, _, cid = await setup(world, reply)
    _, events = await ask(t.people["viewer"], t.oid, cid)
    final = dict(events)["final"]
    assert "[9]" not in final["text"] and final["partially_supported"] is True
    assert [c["marker"] for c in final["citations"]] == [1]


async def test_the_answer_language_follows_the_question(world: World) -> None:
    t, chat, cid = await setup(world, "NO_ANSWER")
    _, events = await ask(t.people["viewer"], t.oid, cid, "كم يوماً تبلغ الإجازة السنوية للموظف؟")
    assert "Write the answer in Arabic" in chat.calls[0][0].content
    refused = dict(events)["refused"]
    assert refused["text"] == "لم أجد هذا في مستنداتك."
    _, events = await ask(t.people["viewer"], t.oid, cid, QUESTION, language="ar")
    assert "Write the answer in Arabic" in chat.calls[1][0].content  # explicit override wins


# ------------------------------------------------------------------ permissions and privacy


async def test_restricted_text_never_reaches_the_model_for_an_unauthorized_user(
    world: World,
) -> None:
    t, chat, _ = await setup(world, "NO_ANSWER")
    secret_question = f"{CANARY} acquisition budget Project Cedar twelve million"
    for who in ("member", "viewer", "editor"):
        person = t.people[who]
        cid = await conversation(person, t.oid)
        _, events = await ask(person, t.oid, cid, secret_question)
        assert CANARY not in json.dumps(events) and "Cedar" not in json.dumps(events)
    # the prompts the model received contain neither the canary nor the restricted text
    prompts = chat.prompts
    assert "acquisition budget for Project Cedar is twelve million" not in prompts
    assert "Board only" not in prompts
    assert prompts.count(CANARY) == 3  # only the three questions themselves carry the string

    chat.calls.clear()
    chat.reply = "The acquisition budget is twelve million [1]."
    listed = t.people["listed"]
    cid = await conversation(listed, t.oid)
    _, events = await ask(listed, t.oid, cid, secret_question)
    assert "Board only" in chat.prompts  # an authorized user's model run does see it
    assert dict(events)["final"]["citations"][0]["document_title"] == "board minutes"


async def test_conversations_are_private_even_from_administrators(world: World) -> None:
    t, _, cid = await setup(world)
    viewer, admin, owner = t.people["viewer"], t.people["admin"], t.people["owner"]
    await ask(viewer, t.oid, cid)
    for other in (admin, owner, t.people["member"]):
        assert (await other.get(f"/orgs/{t.oid}/conversations/{cid}")).status_code == 404
        assert (await other.delete(f"/orgs/{t.oid}/conversations/{cid}")).status_code == 404
        assert (
            await other.post(f"/orgs/{t.oid}/conversations/{cid}/messages", {"content": "hi"})
        ).status_code == 404
        assert cid not in [
            c["id"] for c in (await other.get(f"/orgs/{t.oid}/conversations")).json()
        ]
    # and the database agrees: row-level security hides the rows from anyone else
    async with world.scoped_db(t.oid, admin.user_id) as s:
        assert await s.scalar(text("select count(*) from messages")) == 0
        assert await s.scalar(text("select count(*) from conversations")) == 0
    async with world.scoped_db(t.oid, viewer.user_id) as s:
        assert await s.scalar(text("select count(*) from messages")) == 2
        with pytest.raises(Exception, match="permission denied"):
            await s.execute(text("update message_citations set quote = 'x'"))


async def test_citations_are_redacted_as_soon_as_access_is_lost(world: World) -> None:
    t, _, _ = await setup(world, "The acquisition budget is twelve million [1].")
    owner, listed = t.people["owner"], t.people["listed"]
    cid = await conversation(listed, t.oid)
    await ask(listed, t.oid, cid, f"{CANARY} acquisition budget twelve million")
    before = (await listed.get(f"/orgs/{t.oid}/conversations/{cid}")).json()["messages"][1]
    assert (
        before["citations"][0]["available"] and "twelve million" in before["citations"][0]["quote"]
    )

    await owner.put(f"/orgs/{t.oid}/collections/{t.restricted}/members", {"user_ids": []})
    after = (await listed.get(f"/orgs/{t.oid}/conversations/{cid}")).json()["messages"][1][
        "citations"
    ][0]
    assert after["available"] is False
    assert (
        after["quote"] is None and after["document_title"] is None and after["document_id"] is None
    )
    assert CANARY not in json.dumps(after) and "twelve million" not in json.dumps(after)

    await owner.put(
        f"/orgs/{t.oid}/collections/{t.restricted}/members", {"user_ids": [listed.user_id]}
    )
    assert (await listed.get(f"/orgs/{t.oid}/conversations/{cid}")).json()["messages"][1][
        "citations"
    ][0]["available"]
    docs = (await owner.get(f"/orgs/{t.oid}/documents?collection_id={t.restricted}")).json()[
        "items"
    ]
    await owner.delete(
        f"/orgs/{t.oid}/documents/{docs[0]['id']}"
    )  # deleted documents are redacted too
    gone = (await listed.get(f"/orgs/{t.oid}/conversations/{cid}")).json()["messages"][1][
        "citations"
    ][0]
    assert gone["available"] is False and gone["quote"] is None


async def test_conversations_can_be_listed_and_deleted_by_their_owner(world: World) -> None:
    t, _, cid = await setup(world)
    viewer = t.people["viewer"]
    await ask(viewer, t.oid, cid)
    assert [c["id"] for c in (await viewer.get(f"/orgs/{t.oid}/conversations")).json()] == [cid]
    assert (await viewer.delete(f"/orgs/{t.oid}/conversations/{cid}")).status_code == 204
    assert (await viewer.get(f"/orgs/{t.oid}/conversations/{cid}")).status_code == 404
    async with world.scoped_db(t.oid, viewer.user_id) as s:
        assert await s.scalar(text("select count(*) from messages")) == 0  # cascaded


# ------------------------------------------------------------------ failures and limits


async def test_a_model_outage_ends_in_a_recorded_error_not_a_stuck_message(world: World) -> None:
    t, _, cid = await setup(world, unavailable=True)
    _, events = await ask(t.people["viewer"], t.oid, cid)
    assert (
        names(events)[-2:] == ["error", "done"]
        and dict(events)["error"]["code"] == "LLM_UNAVAILABLE"
    )
    answer = (await t.people["viewer"].get(f"/orgs/{t.oid}/conversations/{cid}")).json()[
        "messages"
    ][1]
    assert answer["status"] == "error" and answer["error_code"] == "LLM_UNAVAILABLE"


async def test_a_full_context_window_is_an_error_never_a_silently_truncated_answer(
    world: World,
) -> None:
    t, _, cid = await setup(
        world, prompt_tokens=8190
    )  # the server reports a prompt that filled num_ctx
    _, events = await ask(t.people["viewer"], t.oid, cid)
    assert dict(events)["error"]["code"] == "PROMPT_TRUNCATED" and "final" not in names(events)


async def test_questions_are_rate_limited_per_user(world: World) -> None:
    lenient(world, chat_rate_per_minute=2)
    t, _, cid = await setup(world)
    viewer = t.people["viewer"]
    codes = [(await ask(viewer, t.oid, cid))[0] for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_invalid_requests_are_rejected_before_any_streaming(world: World) -> None:
    t, _, cid = await setup(world)
    viewer = t.people["viewer"]
    for payload in (
        {"content": ""},
        {"content": "   "},
        {"content": "x" * 2001},
        {"content": "hi", "language": "fr"},
    ):
        r = await viewer.post(f"/orgs/{t.oid}/conversations/{cid}/messages", payload)
        assert r.status_code == 422
    r = await viewer.post(f"/orgs/{t.oid}/conversations/{uuid.uuid4()}/messages", {"content": "hi"})
    assert r.status_code == 404


async def test_the_bounded_queue_makes_requests_wait_visibly_and_rejects_overflow(
    world: World,
) -> None:
    lenient(world, llm_queue_limit=1)
    t, _, _ = await setup(world, delay=0.15, chunk_chars=30)
    people = [t.people["viewer"], t.people["member"], t.people["editor"]]
    cids = [await conversation(p, t.oid) for p in people]
    results = await asyncio.gather(*(ask(p, t.oid, c) for p, c in zip(people, cids, strict=True)))
    codes = sorted(status for status, _ in results)
    assert codes.count(200) >= 2
    streams = [events for status, events in results if status == 200]
    assert any("queued" in names(events) for events in streams)  # someone waited, visibly
    assert all(names(e)[-1] == "done" for e in streams)
    if codes[-1] == 503:  # the third request found the queue full
        busy = next(events for status, events in results if status == 503)
        assert busy[0][1]["code"] == "BUSY"


# ------------------------------------------------------------------ disconnects


async def _manual_run(
    world: World, chat: FakeChat
) -> tuple[service.ChatDeps, service.Started, Team]:
    lenient(world)
    world.chat = chat
    t = await team(world)
    viewer = t.people["viewer"]
    cid = await conversation(viewer, t.oid)
    # create the two messages through the API with an instant fake, then drive `generate` by hand
    async with world.scoped_db(t.oid, viewer.user_id) as s:
        ids = [uuid.uuid4(), uuid.uuid4()]
        for mid, role, status in ((ids[0], "user", "complete"), (ids[1], "assistant", "streaming")):
            await s.execute(
                text(
                    "insert into messages (id, conversation_id, organization_id, user_id, role, status, content) "
                    "values (:i, :c, :o, :u, :r, :s, :t)"
                ),
                {
                    "i": mid,
                    "c": uuid.UUID(cid),
                    "o": uuid.UUID(t.oid),
                    "u": uuid.UUID(viewer.user_id),
                    "r": role,
                    "s": status,
                    "t": QUESTION,
                },
            )
        await s.commit()
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.base import to_async_url

    engine = create_async_engine(to_async_url(world.settings.database_url))
    world.stack.push_async_callback(engine.dispose)
    deps = service.ChatDeps(
        chat=chat, embedder=FakeEmbedder(), limiter=None,  # type: ignore[arg-type]
        settings=world.settings, queue=GenerationQueue(1, 1),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
    )  # fmt: skip
    started = service.Started(
        conversation_id=uuid.UUID(cid), user_message_id=ids[0], assistant_message_id=ids[1],
        user_id=uuid.UUID(viewer.user_id), org_id=uuid.UUID(t.oid), role=Role.VIEWER,
        question=QUESTION, language="en", collection_ids=None,
    )  # fmt: skip
    return deps, started, t


async def _status(world: World, t: Team, message_id: uuid.UUID) -> tuple[str, str | None]:
    async with world.scoped_db(t.oid, t.people["viewer"].user_id) as s:
        row = (
            await s.execute(
                text("select status, error_code from messages where id = :i"), {"i": message_id}
            )
        ).one()
    return row.status, row.error_code


async def test_a_cancelled_stream_marks_the_message_failed_instead_of_streaming_forever(
    world: World,
) -> None:
    deps, started, t = await _manual_run(world, FakeChat(GROUNDED * 4, delay=0.2, chunk_chars=5))
    seen = asyncio.Event()

    async def consume() -> None:
        async for event in service.generate(deps, started):
            if event["event"] == "delta":
                seen.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(seen.wait(), 30)
    task.cancel()  # what the server does when the client disconnects
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await _status(world, t, started.assistant_message_id) == ("error", "CLIENT_DISCONNECTED")


async def test_an_abandoned_generator_is_also_finalized(world: World) -> None:
    deps, started, t = await _manual_run(world, FakeChat(GROUNDED * 4, chunk_chars=5))
    generator = service.generate(deps, started)
    async for event in generator:
        if event["event"] == "delta":
            break
    await generator.aclose()
    assert await _status(world, t, started.assistant_message_id) == ("error", "INTERRUPTED")
    assert deps.queue.waiting == 0 and not deps.queue.would_wait()  # the model slot was released


async def test_the_settings_defaults_are_the_documented_ones() -> None:
    s = Settings()
    assert (s.llm_num_ctx, s.llm_max_concurrency, s.answer_context_chunks) == (8192, 1, 6)
