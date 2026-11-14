"""The background worker's database role is least-privilege; the API role cannot write its tables."""

import uuid

import asyncpg
import pytest

from tests.test_rls import as_app
from tests.test_rls_documents import (  # noqa: F401
    C_OPEN,
    C_SECRET,
    D_OPEN,
    D_SECRET,
    LISTED,
    ORG_A,
    UNLISTED,
    world_db,
)


@pytest.fixture
async def worker(world_db: None, worker_db_url: str):  # type: ignore[no-untyped-def]
    conn = await asyncpg.connect(worker_db_url)
    try:
        yield conn
    finally:
        await conn.close()


async def test_worker_role_has_no_dangerous_attributes(worker: asyncpg.Connection) -> None:
    assert await worker.fetchval("SELECT current_user") == "worker_rw"
    row = await worker.fetchrow(
        "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = 'worker_rw'"
    )
    assert not any(row.values())
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await worker.execute("CREATE TABLE sneaky (id int)")
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await worker.execute("SET ROLE test")


@pytest.mark.parametrize(
    "table",
    [
        "users",
        "memberships",
        "invitations",
        "collections",
        "collection_members",
        "refresh_tokens",
        "password_resets",
    ],
)
async def test_worker_cannot_read_identity_or_access_tables(
    worker: asyncpg.Connection, table: str
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await worker.fetch(f"SELECT * FROM {table} LIMIT 1")


async def test_worker_sees_organization_ids_only(worker: asyncpg.Connection) -> None:
    assert await worker.fetchval("SELECT count(*) FROM (SELECT id FROM organizations) t") >= 1
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await worker.fetch("SELECT name FROM organizations")


async def test_worker_document_access_is_read_plus_a_fixed_set_of_columns(
    worker: asyncpg.Connection,
) -> None:
    assert (
        await worker.fetchval("SELECT count(*) FROM documents") == 3
    )  # across tenants: it acts for the system
    assert (
        await worker.execute("UPDATE documents SET status = 'parsing' WHERE id = $1", D_OPEN)
        == "UPDATE 1"
    )
    for forbidden in (
        "organization_id",
        "collection_id",
        "storage_key",
        "sha256",
        "title",
        "deleted_at",
        "uploaded_by",
    ):
        value = "'x'" if forbidden in ("storage_key", "sha256", "title") else "NULL"
        if forbidden in ("organization_id", "collection_id", "uploaded_by"):
            value = f"'{uuid.uuid4()}'"
        if forbidden == "deleted_at":
            value = "now()"
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await worker.execute(
                f"UPDATE documents SET {forbidden} = {value} WHERE id = $1", D_OPEN
            )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await worker.execute("DELETE FROM documents WHERE id = $1", D_OPEN)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await worker.execute(
            "INSERT INTO documents (id, organization_id, collection_id, title, original_filename, mime_type, "
            "size_bytes, sha256, storage_key) VALUES ($1,$2,$3,'t','f','application/pdf',1,'h','k/w')",
            uuid.uuid4(), ORG_A, C_OPEN,
        )  # fmt: skip


async def test_worker_owns_pages_chunks_and_jobs(worker: asyncpg.Connection) -> None:
    await worker.execute(
        "INSERT INTO document_pages (id, organization_id, document_id, collection_id, page_number, extraction_state) "
        "VALUES ($1,$2,$3,$4,1,'text')",
        uuid.uuid4(), ORG_A, D_SECRET, C_SECRET,
    )  # fmt: skip
    await worker.execute(
        "INSERT INTO chunks (id, organization_id, document_id, collection_id, page_start, page_end, chunk_index, "
        "content, content_search, token_count, lang) VALUES ($1,$2,$3,$4,1,1,0,'c','c',1,'en')",
        uuid.uuid4(), ORG_A, D_SECRET, C_SECRET,
    )  # fmt: skip
    assert await worker.fetchval("SELECT count(*) FROM chunks") == 1
    await worker.execute("DELETE FROM chunks")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO chunks (id, organization_id, document_id, collection_id, page_start, page_end, chunk_index, "
        f"content, content_search, token_count, lang) VALUES (gen_random_uuid(), '{ORG_A}', '{D_OPEN}', '{C_OPEN}', 1, 1, 0, 'c', 'c', 1, 'en')",
        "UPDATE chunks SET content = 'tampered'",
        "DELETE FROM chunks",
        "SELECT count(*) FROM ingestion_jobs",
        "DELETE FROM document_pages",
        "UPDATE document_pages SET char_count = 1",
    ],
)
async def test_api_role_cannot_write_the_worker_tables_or_read_the_job_log(
    world_db: None, app_db_url: str, sql: str
) -> None:
    async with as_app(app_db_url, user=LISTED, org=ORG_A) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(sql)


async def test_document_pages_follow_collection_access_for_the_api_role(
    world_db: None, app_db_url: str, worker_db_url: str
) -> None:
    w = await asyncpg.connect(worker_db_url)
    try:
        for doc, col in ((D_OPEN, C_OPEN), (D_SECRET, C_SECRET)):
            await w.execute(
                "INSERT INTO document_pages (id, organization_id, document_id, collection_id, page_number, "
                "extraction_state, text) VALUES ($1,$2,$3,$4,1,'text','secret page text')",
                uuid.uuid4(), ORG_A, doc, col,
            )  # fmt: skip
    finally:
        await w.close()
    async with as_app(app_db_url, user=UNLISTED, org=ORG_A) as conn:
        assert {
            r["document_id"] for r in await conn.fetch("SELECT document_id FROM document_pages")
        } == {D_OPEN}
    async with as_app(app_db_url, user=LISTED, org=ORG_A) as conn:
        assert {
            r["document_id"] for r in await conn.fetch("SELECT document_id FROM document_pages")
        } == {D_OPEN, D_SECRET}
