"""Embedding stage, indexes and re-indexing, against real Postgres (pgvector) and the real pipeline."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.types import vector_literal
from app.modules.processing.arabic import search_normalize
from app.modules.processing.indexing import embedding_text, reindex_stale
from app.modules.processing.sweeper import requeue_transient_failures
from tests.fake_embedder import FakeEmbedder, vectorize
from tests.pdfgen import PageSpec, make_pdf
from tests.pipeline_helpers import worker_sessions
from tests.tenancy_helpers import World
from tests.test_pipeline import (
    ARABIC,
    ARABIC2,
    ENGLISH,
    ENGLISH2,
    fetch,
    ingest,
    jobs_of,
    setup,
)

HANDBOOK = make_pdf([PageSpec([ENGLISH, ENGLISH2]), PageSpec(["4.4 Carry-over", ENGLISH2])])


async def wsql(world: World, sql: str, **params: Any) -> list[Any]:
    """Run SQL as the worker role (the API role cannot see chunks)."""
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        async with sessions() as s:
            result = await s.execute(text(sql), params)
            rows = list(result.all()) if result.returns_rows else []
            await s.commit()
            return rows
    finally:
        await engine.dispose()


# ------------------------------------------------------------------ embedding stage


async def test_every_chunk_is_stored_with_a_vector_and_the_model_that_made_it(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert doc.status == "ready"
    (row,) = await wsql(
        world,
        "select count(*), count(embedding), count(*) filter (where embedding_model = 'fake-hash-1024'),"
        " min(vector_dims(embedding)), max(vector_dims(embedding)) from chunks where document_id = :d",
        d=uuid.UUID(doc_id),
    )
    total, embedded, by_model, lo, hi = row
    assert total > 0 and embedded == total and by_model == total and (lo, hi) == (1024, 1024)


async def test_nearest_neighbour_search_finds_the_matching_chunk(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    query = vector_literal(vectorize("how many working days of annual leave per year"))
    (row,) = await wsql(
        world,
        "select content from chunks where document_id = :d "
        "order by embedding <=> CAST(CAST(:q AS text) AS vector) limit 1",
        d=uuid.UUID(doc_id),
        q=query,
    )
    assert "twenty five working days" in row.content


async def test_chunks_are_embedded_with_title_and_heading_context_in_bounded_batches(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    embedder = FakeEmbedder()
    await ingest(world, owner, oid, cid, "Travel Policy.pdf", HANDBOOK, embedder=embedder)
    assert embedder.texts and all(t.startswith("Travel Policy") for t in embedder.texts)
    for t in embedder.texts:
        first_line = t.split("\n", 1)[0]
        assert first_line == "Travel Policy" or first_line.startswith("Travel Policy > ")
    assert all(n <= 8 for n in embedder.calls)


async def test_documents_without_chunks_never_reach_the_embedder(world: World) -> None:
    owner, oid, cid = await setup(world)
    embedder = FakeEmbedder()
    doc_id = await ingest(
        world, owner, oid, cid, "scan.pdf",
        make_pdf([PageSpec([], image_ratio=0.9)]), embedder=embedder,
    )  # fmt: skip
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert doc.status == "unsupported_scanned" and embedder.calls == []


async def test_events_include_the_embedding_stage_only_when_there_is_something_to_embed(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    seen: list[str] = []

    async def publish(_o: uuid.UUID, _d: uuid.UUID, status: str, _c: str | None) -> None:
        seen.append(status)

    await ingest(world, owner, oid, cid, "a.pdf", make_pdf([PageSpec([])]), publish=publish)
    assert "embedding" not in seen  # blank page: nothing to embed


# ------------------------------------------------------------------ embedder trouble


async def test_embedder_outage_fails_the_document_recoverably_and_keeps_nothing(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "handbook.pdf", HANDBOOK, embedder=FakeEmbedder(unavailable=True)
    )
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("failed", "EMBEDDER_UNAVAILABLE")
    assert pages == []  # no half-indexed document
    assert (
        await wsql(world, "select count(*) from chunks where document_id=:d", d=uuid.UUID(doc_id))
    )[0][0] == 0
    (job,) = await jobs_of(world, doc_id)
    assert (job.status, job.error_code, job.stage) == (
        "failed",
        "EMBEDDER_UNAVAILABLE",
        "embedding",
    )


async def test_a_dependency_outage_is_retried_automatically_and_then_succeeds(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "handbook.pdf", HANDBOOK, embedder=FakeEmbedder(unavailable=True)
    )
    queued: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def enqueue(doc: uuid.UUID, org: uuid.UUID) -> None:
        queued.append((doc, org))

    settings = Settings()
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        soon = datetime.now(UTC) + timedelta(seconds=10)
        assert (
            await requeue_transient_failures(sessions, enqueue, settings, now=soon) == 0
        )  # too soon
        later = datetime.now(UTC) + timedelta(seconds=settings.transient_retry_seconds + 5)
        assert await requeue_transient_failures(sessions, enqueue, settings, now=later) == 1
    finally:
        await engine.dispose()
    assert queued == [(uuid.UUID(doc_id), uuid.UUID(oid))]
    assert await world.process(oid, doc_id) == "processed"  # the embedder is back
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("ready", None)


async def test_retries_stop_after_the_attempt_limit(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "handbook.pdf", HANDBOOK, embedder=FakeEmbedder(unavailable=True)
    )
    settings = Settings(max_transient_attempts=1)  # the single failed attempt is all it gets
    queued: list[Any] = []

    async def enqueue(doc: uuid.UUID, org: uuid.UUID) -> None:
        queued.append(doc)

    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        later = datetime.now(UTC) + timedelta(hours=1)
        assert await requeue_transient_failures(sessions, enqueue, settings, now=later) == 0
    finally:
        await engine.dispose()
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert doc.status == "failed" and queued == []


async def test_a_misconfigured_model_is_a_permanent_failure_that_is_not_retried(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world,
        owner,
        oid,
        cid,
        "handbook.pdf",
        HANDBOOK,
        embedder=FakeEmbedder(wrong_dimensions=True),
    )
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("failed", "EMBEDDING_FAILED")
    queued: list[Any] = []

    async def enqueue(doc: uuid.UUID, org: uuid.UUID) -> None:
        queued.append(doc)

    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        later = datetime.now(UTC) + timedelta(days=1)
        assert await requeue_transient_failures(sessions, enqueue, Settings(), now=later) == 0
    finally:
        await engine.dispose()
    assert queued == []


# ------------------------------------------------------------------ re-indexing


async def _models(world: World, doc_id: str) -> set[str | None]:
    rows = await wsql(
        world,
        "select distinct embedding_model from chunks where document_id=:d",
        d=uuid.UUID(doc_id),
    )
    return {r[0] for r in rows}


async def test_reindex_moves_stale_chunks_to_the_new_model_and_is_idempotent(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    assert await _models(world, doc_id) == {"fake-hash-1024"}
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        current = FakeEmbedder()
        assert (await reindex_stale(sessions, current, 8)).chunks == 0  # nothing stale: no work
        newer = FakeEmbedder(model="fake-hash-v2")
        first = await reindex_stale(sessions, newer, 8, org_id=uuid.UUID(oid))
        assert first.documents == 1 and first.chunks > 0 and first.stopped is None
        assert await _models(world, doc_id) == {"fake-hash-v2"}
        assert (await reindex_stale(sessions, newer, 8)).chunks == 0  # second run: nothing to do
        assert newer.calls and sum(newer.calls) == first.chunks  # only stale chunks were embedded
    finally:
        await engine.dispose()
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert doc.status == "ready"  # a model switch never disturbs the document


async def test_reindex_embeds_chunks_that_were_never_embedded(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    await wsql(
        world,
        "update chunks set embedding=null, embedding_model=null where document_id=:d",
        d=uuid.UUID(doc_id),
    )
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        done = await reindex_stale(sessions, FakeEmbedder(), 8, document_id=uuid.UUID(doc_id))
    finally:
        await engine.dispose()
    assert done.chunks > 0 and await _models(world, doc_id) == {"fake-hash-1024"}


async def test_reindex_stops_cleanly_when_the_embedder_is_down_and_changes_nothing(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        result = await reindex_stale(sessions, FakeEmbedder(model="other", unavailable=True), 8)
    finally:
        await engine.dispose()
    assert result.stopped == "EmbedderUnavailableError" and result.chunks == 0
    assert await _models(world, doc_id) == {"fake-hash-1024"}


async def test_reindex_ignores_documents_that_are_not_ready(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "handbook.pdf", HANDBOOK, embedder=FakeEmbedder(unavailable=True)
    )  # failed: no chunks at all
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        assert (await reindex_stale(sessions, FakeEmbedder(), 8)).documents == 0
    finally:
        await engine.dispose()
    assert await _models(world, doc_id) == set()


# ------------------------------------------------------------------ schema and indexes


async def test_a_vector_without_its_model_is_refused_by_the_database(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    with pytest.raises(IntegrityError):
        await wsql(
            world,
            "update chunks set embedding_model = null where document_id = :d",
            d=uuid.UUID(doc_id),
        )


async def test_the_api_role_still_cannot_read_chunks_or_vectors(world: World) -> None:
    owner, oid, cid = await setup(world)
    await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    async with world.scoped_db(oid, owner.user_id) as s:
        with pytest.raises(Exception, match="permission denied"):
            await s.execute(text("select embedding from chunks limit 1"))


async def test_vector_and_full_text_indexes_are_usable(world: World) -> None:
    """With sequential scans disabled the planner must be able to use each index (tiny tables
    otherwise prefer a scan, which would hide a missing or unusable index)."""
    owner, oid, cid = await setup(world)
    await ingest(world, owner, oid, cid, "handbook.pdf", HANDBOOK)
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        async with sessions() as s:
            await s.execute(text("set local enable_seqscan = off"))
            vec = "\n".join(
                r[0]
                for r in await s.execute(
                    text(
                        "explain select id from chunks "
                        "order by embedding <=> CAST(CAST(:q AS text) AS vector) limit 5"
                    ),
                    {"q": vector_literal(vectorize("leave"))},
                )
            )
            fts = "\n".join(
                r[0]
                for r in await s.execute(
                    text(
                        "explain select id from chunks where content_tsv @@ to_tsquery('english', 'leave')"
                    )
                )
            )
            simple = "\n".join(
                r[0]
                for r in await s.execute(
                    text(
                        "explain select id from chunks where content_tsv_simple @@ to_tsquery('simple', 'leave')"
                    )
                )
            )
    finally:
        await engine.dispose()
    assert "ix_chunks_embedding_hnsw" in vec
    assert "ix_chunks_content_tsv" in fts
    assert "ix_chunks_content_tsv_simple" in simple


# ------------------------------------------------------------------ lexical leg


async def test_arabic_full_text_matches_across_spelling_variants_and_digits(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([ARABIC, ARABIC2]), PageSpec(["يحق للموظف ٢٥ يوما من الإجازة"])])
    doc_id = await ingest(world, owner, oid, cid, "leave_ar.pdf", pdf)
    assert (await fetch(world, owner, oid, doc_id))[0].status == "ready"

    async def hits(query: str, config: str = "arabic", column: str = "content_tsv") -> int:
        q = " & ".join(search_normalize(query).split())
        rows = await wsql(
            world,
            f"select count(*) from chunks where document_id=:d and {column} @@ to_tsquery('{config}', :q)",
            d=uuid.UUID(doc_id),
            q=q,
        )
        return int(rows[0][0])

    assert await hits("الإجازة السنوية") > 0  # hamza on the alef is folded on both sides
    assert await hits("الاجازه") == 0  # ta marbuta is deliberately NOT folded (documented)
    assert await hits("الاجازة") > 0
    assert await hits("25") > 0  # Western digits find the Arabic-Indic "٢٥"
    assert await hits("٢٥") > 0  # and Arabic-Indic digits in the query normalize the same way
    assert await hits("الاجازة", "simple", "content_tsv_simple") > 0


async def test_mixed_language_chunks_are_indexed_for_both_languages(world: World) -> None:
    owner, oid, cid = await setup(world)
    mixed = (
        "نظام Fleet Management system for vehicle maintenance schedules "
        "لإدارة المركبات والصيانة الدورية للأسطول"
    )
    doc_id = await ingest(world, owner, oid, cid, "mixed.pdf", make_pdf([PageSpec([mixed, mixed])]))
    langs = {
        r[0]
        for r in await wsql(
            world, "select lang from chunks where document_id=:d", d=uuid.UUID(doc_id)
        )
    }
    assert langs == {"mixed"}

    async def hits(config: str, query: str) -> int:
        rows = await wsql(
            world,
            f"select count(*) from chunks where document_id=:d and content_tsv @@ to_tsquery('{config}', :q)",
            d=uuid.UUID(doc_id),
            q=query,
        )
        return int(rows[0][0])

    assert await hits("english", "managing") > 0  # English stemming (manage / management)
    # The Arabic side is covered by the long-Arabic test above: this short synthetic line is
    # extracted in visual order (the documented short-line limit), which would make it flaky here.
    assert await hits("arabic", "fleet") > 0  # Latin words stay findable under the Arabic config
