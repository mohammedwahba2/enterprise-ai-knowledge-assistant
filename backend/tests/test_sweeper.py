import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import Settings
from app.infrastructure.storage.s3 import S3ObjectStore, StorageUnavailableError
from app.modules.documents.models import Document
from app.modules.processing import sweeper
from app.modules.processing.models import IngestionJob
from tests.pdfgen import PageSpec, make_pdf
from tests.pipeline_helpers import worker_sessions
from tests.tenancy_helpers import Person, World

TEXT = "Employees receive twenty five working days of paid annual leave per calendar year."


async def setup(world: World) -> tuple[Person, str, str]:
    owner = await world.person("Owner")
    oid = (await world.org(owner, "Acme"))["id"]
    return owner, oid, await world.general(owner, oid)


async def upload(world: World, owner: Person, oid: str, cid: str, label: str) -> str:
    r = await owner.upload(oid, cid, (f"{label}.pdf", make_pdf([PageSpec([f"{TEXT} {label}"])])))
    return str(r.json()[0]["document"]["id"])


async def set_doc(world: World, owner: Person, oid: str, doc_id: str, **values: object) -> None:
    async with world.scoped_db(oid, owner.user_id) as s:
        await s.execute(update(Document).where(Document.id == uuid.UUID(doc_id)).values(**values))
        await s.commit()


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def __call__(self, document_id: uuid.UUID, org_id: uuid.UUID) -> None:
        self.calls.append((document_id, org_id))


async def test_stuck_documents_are_requeued_and_healthy_ones_left_alone(
    world: World, settings: Settings
) -> None:
    owner, oid, cid = await setup(world)
    old = datetime.now(UTC) - timedelta(hours=1)
    lost = await upload(world, owner, oid, cid, "lost")
    fresh = await upload(world, owner, oid, cid, "fresh")
    hung = await upload(world, owner, oid, cid, "hung")
    done = await upload(world, owner, oid, cid, "done")
    await set_doc(world, owner, oid, lost, updated_at=old)  # never started
    await set_doc(world, owner, oid, hung, status="parsing", updated_at=old)  # started, worker died
    await set_doc(world, owner, oid, done, status="ready", updated_at=old)  # finished long ago
    rec = Recorder()
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        result = await sweeper.requeue_stuck_documents(sessions, rec, settings)
        assert result == {"requeued": 2, "abandoned": 0}
        assert {c[0] for c in rec.calls} == {uuid.UUID(lost), uuid.UUID(hung)}
        assert all(c[1] == uuid.UUID(oid) for c in rec.calls)
        # an immediate second sweep does not re-queue them again (back-off)
        rec.calls.clear()
        assert await sweeper.requeue_stuck_documents(sessions, rec, settings) == {
            "requeued": 0,
            "abandoned": 0,
        }
        assert rec.calls == []
    finally:
        await engine.dispose()
    assert fresh  # (never touched: recent uploads are given time to start)


async def test_a_document_that_keeps_crashing_the_worker_is_abandoned(
    world: World, settings: Settings
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await upload(world, owner, oid, cid, "poison")
    old = datetime.now(UTC) - timedelta(hours=1)
    await set_doc(world, owner, oid, doc_id, status="parsing", updated_at=old)
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        async with sessions() as s:
            for attempt in range(1, settings.max_processing_attempts + 1):
                s.add(
                    IngestionJob(
                        organization_id=uuid.UUID(oid), document_id=uuid.UUID(doc_id),
                        collection_id=uuid.UUID(cid), stage="parsing", attempt=attempt, status="running",
                    )
                )  # fmt: skip
            await s.commit()
        rec = Recorder()
        assert await sweeper.requeue_stuck_documents(sessions, rec, settings) == {
            "requeued": 0,
            "abandoned": 1,
        }
        assert rec.calls == []  # no more retries
        async with sessions() as s:
            doc = (await s.scalars(select(Document).where(Document.id == uuid.UUID(doc_id)))).one()
            assert (doc.status, doc.error_code) == ("failed", "PROCESSING_CRASHED")
            jobs = (
                await s.scalars(select(IngestionJob).where(IngestionJob.document_id == doc.id))
            ).all()
            assert {j.status for j in jobs} == {"abandoned"}
    finally:
        await engine.dispose()


async def test_deleted_documents_objects_are_purged_and_failures_are_retried(
    world: World, settings: Settings
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await upload(world, owner, oid, cid, "gone")
    store = S3ObjectStore(settings)
    key = f"org/{oid}/doc/{doc_id}"
    await store.put(f"{key}.viewer.pdf", io.BytesIO(b"%PDF-"), "application/pdf")
    await set_doc(
        world, owner, oid, doc_id, deleted_at=datetime.now(UTC)
    )  # soft-deleted, purge never ran
    assert await store.exists(key)

    class Failing(S3ObjectStore):
        async def delete(self, key: str) -> None:
            raise StorageUnavailableError("down")

    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        assert (
            await sweeper.purge_deleted_objects(sessions, Failing(settings)) == 0
        )  # store down: try again later
        async with sessions() as s:
            assert (
                await s.scalars(select(Document.purged_at).where(Document.id == uuid.UUID(doc_id)))
            ).one() is None
        assert await sweeper.purge_deleted_objects(sessions, store) == 1
        assert not await store.exists(key) and not await store.exists(f"{key}.viewer.pdf")
        async with sessions() as s:
            assert (
                await s.scalars(select(Document.purged_at).where(Document.id == uuid.UUID(doc_id)))
            ).one() is not None
        assert await sweeper.purge_deleted_objects(sessions, store) == 0  # idempotent
    finally:
        await engine.dispose()


async def test_orphaned_workspace_prefixes_are_removed_but_live_and_recent_ones_are_not(
    world: World, settings: Settings
) -> None:
    owner, oid, cid = await setup(world)
    live_doc = await upload(world, owner, oid, cid, "live")
    store = S3ObjectStore(settings)
    ghost = str(uuid.uuid4())  # a workspace that no longer exists in the database
    for k in (f"org/{ghost}/doc/a", f"org/{ghost}/doc/b.viewer.pdf"):
        await store.put(k, io.BytesIO(b"x"), "application/octet-stream")
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        # recent orphans are left alone (a workspace may be mid-creation or mid-deletion)
        assert await sweeper.purge_orphan_prefixes(sessions, store) == 0
        assert len(await store.list_keys(f"org/{ghost}/")) == 2
        later = datetime.now(UTC) + timedelta(hours=2)
        removed = await sweeper.purge_orphan_prefixes(sessions, store, now=later)
        assert removed >= 2
        assert await store.list_keys(f"org/{ghost}/") == []
        assert await store.exists(f"org/{oid}/doc/{live_doc}")  # a real workspace is never touched
    finally:
        await engine.dispose()


async def test_the_sweeper_runs_as_the_restricted_worker_role(world: World) -> None:
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        async with sessions() as s:
            from sqlalchemy import text

            assert (await s.execute(text("SELECT current_user"))).scalar_one() == "worker_rw"
    finally:
        await engine.dispose()


@pytest.mark.parametrize("n", [1])
def test_settings_defaults_are_sane(n: int) -> None:
    s = Settings()
    assert s.stuck_uploaded_seconds < s.stuck_running_seconds and s.max_processing_attempts >= n
