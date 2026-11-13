"""Database-level document permissions, exercised as the real application role with raw SQL.

Even if every application filter were wrong, PostgreSQL itself must keep restricted collections
(and their documents) away from members who are not on the list, and keep tenants apart.
"""

import uuid

import asyncpg
import pytest

from tests.test_rls import as_app, count

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()
ADMIN, LISTED, UNLISTED, OUTSIDER = (uuid.uuid4() for _ in range(4))
C_OPEN, C_SECRET, C_OTHER_ORG = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
D_OPEN, D_SECRET, D_OTHER_ORG = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


@pytest.fixture
async def world_db(pg_url: str) -> None:
    conn = await asyncpg.connect(pg_url)
    try:
        await conn.execute(
            "TRUNCATE users, refresh_tokens, password_resets, organizations, memberships, invitations, "
            "collections, collection_members, documents CASCADE"
        )
        for uid in (ADMIN, LISTED, UNLISTED, OUTSIDER):
            await conn.execute(
                "INSERT INTO users (id, email, password_hash, display_name) VALUES ($1,$2,'x',$3)",
                uid, f"{uid}@example.com", str(uid),
            )  # fmt: skip
        for oid in (ORG_A, ORG_B):
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES ($1,$2,$2)", oid, f"o-{oid}"
            )
        for oid, uid, role in (
            (ORG_A, ADMIN, "admin"), (ORG_A, LISTED, "member"), (ORG_A, UNLISTED, "member"), (ORG_B, OUTSIDER, "owner"),
        ):  # fmt: skip
            await conn.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,$4)",
                uuid.uuid4(), oid, uid, role,
            )  # fmt: skip
        for cid, oid, vis in (
            (C_OPEN, ORG_A, "org"),
            (C_SECRET, ORG_A, "restricted"),
            (C_OTHER_ORG, ORG_B, "org"),
        ):
            await conn.execute(
                "INSERT INTO collections (id, organization_id, name, visibility) VALUES ($1,$2,$3,$4)",
                cid, oid, f"c-{cid}", vis,
            )  # fmt: skip
        await conn.execute(
            "INSERT INTO collection_members (collection_id, user_id, organization_id) VALUES ($1,$2,$3)",
            C_SECRET, LISTED, ORG_A,
        )  # fmt: skip
        for did, oid, cid in (
            (D_OPEN, ORG_A, C_OPEN),
            (D_SECRET, ORG_A, C_SECRET),
            (D_OTHER_ORG, ORG_B, C_OTHER_ORG),
        ):
            await conn.execute(
                "INSERT INTO documents (id, organization_id, collection_id, title, original_filename, mime_type, "
                "size_bytes, sha256, storage_key) VALUES ($1,$2,$3,'t','f.pdf','application/pdf',1,$4,$5)",
                did, oid, cid, uuid.uuid4().hex * 2, f"k/{did}",
            )  # fmt: skip
    finally:
        await conn.close()


async def visible(conn: asyncpg.Connection, table: str, col: str = "id") -> set[uuid.UUID]:
    return {r[col] for r in await conn.fetch(f"SELECT {col} FROM {table}")}  # noqa: S608


@pytest.mark.parametrize(
    ("user", "docs", "cols"),
    [
        (
            ADMIN,
            {D_OPEN, D_SECRET},
            {C_OPEN, C_SECRET},
        ),  # admins reach every collection of their org
        (LISTED, {D_OPEN, D_SECRET}, {C_OPEN, C_SECRET}),
        (UNLISTED, {D_OPEN}, {C_OPEN}),  # the restricted one does not even exist for them
    ],
)
async def test_reads_follow_collection_access(
    world_db: None, app_db_url: str, user: uuid.UUID, docs: set[uuid.UUID], cols: set[uuid.UUID]
) -> None:
    async with as_app(app_db_url, user=user, org=ORG_A) as conn:
        assert await visible(conn, "documents") == docs
        assert await visible(conn, "collections") == cols


async def test_unlisted_member_cannot_touch_restricted_rows(
    world_db: None, app_db_url: str, pg_url: str
) -> None:
    async with as_app(app_db_url, user=UNLISTED, org=ORG_A) as conn:
        assert (
            await conn.execute("UPDATE documents SET title = 'pwned' WHERE id = $1", D_SECRET)
            == "UPDATE 0"
        )
        assert await conn.execute("DELETE FROM documents WHERE id = $1", D_SECRET) == "DELETE 0"
        assert (
            await conn.execute("UPDATE collections SET name = 'pwned' WHERE id = $1", C_SECRET)
            == "UPDATE 0"
        )
        assert await conn.execute("DELETE FROM collections WHERE id = $1", C_SECRET) == "DELETE 0"
        assert (
            await conn.execute("DELETE FROM collection_members WHERE collection_id = $1", C_SECRET)
            == "DELETE 0"
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO documents (id, organization_id, collection_id, title, original_filename, mime_type, "
                "size_bytes, sha256, storage_key) VALUES ($1,$2,$3,'t','f','application/pdf',1,'h','k/new')",
                uuid.uuid4(), ORG_A, C_SECRET,
            )  # fmt: skip
    async with as_app(app_db_url, user=UNLISTED, org=ORG_A) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO collection_members (collection_id, user_id, organization_id) VALUES ($1,$2,$3)",
                C_SECRET, UNLISTED, ORG_A,
            )  # cannot add themselves to the list  # fmt: skip
    owner = await asyncpg.connect(pg_url)
    try:
        assert await owner.fetchval("SELECT title FROM documents WHERE id = $1", D_SECRET) == "t"
        assert (
            await owner.fetchval(
                "SELECT count(*) FROM collection_members WHERE collection_id = $1", C_SECRET
            )
            == 1
        )
    finally:
        await owner.close()


async def test_a_document_cannot_be_moved_into_a_collection_the_caller_cannot_access(
    world_db: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=UNLISTED, org=ORG_A) as conn:
        # moving an accessible document into the restricted collection: the new row fails the check
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "UPDATE documents SET collection_id = $1 WHERE id = $2", C_SECRET, D_OPEN
            )


async def test_naming_the_org_without_membership_exposes_no_documents_or_collections(
    world_db: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=OUTSIDER, org=ORG_A) as conn:  # forged scope
        for table in ("documents", "collections", "collection_members"):
            assert await count(conn, table) == 0, table
        assert (
            await conn.execute("DELETE FROM documents WHERE organization_id = $1", ORG_A)
            == "DELETE 0"
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO documents (id, organization_id, collection_id, title, original_filename, mime_type, "
                "size_bytes, sha256, storage_key) VALUES ($1,$2,$3,'t','f','application/pdf',1,'h','k/x')",
                uuid.uuid4(), ORG_A, C_OPEN,
            )  # fmt: skip


async def test_no_scope_and_cross_tenant_scopes_see_nothing(
    world_db: None, app_db_url: str
) -> None:
    async with as_app(app_db_url) as conn:
        for table in ("documents", "collections", "collection_members"):
            assert await count(conn, table) == 0
    async with as_app(app_db_url, user=OUTSIDER, org=ORG_B) as conn:
        assert await visible(conn, "documents") == {D_OTHER_ORG}  # only its own tenant's row
    async with as_app(app_db_url, user=LISTED, org=ORG_B) as conn:  # a member of A claiming org B
        assert await count(conn, "documents") == 0


async def test_cannot_file_a_document_under_another_orgs_collection(
    world_db: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=ADMIN, org=ORG_A) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO documents (id, organization_id, collection_id, title, original_filename, mime_type, "
                "size_bytes, sha256, storage_key) VALUES ($1,$2,$3,'t','f','application/pdf',1,'h','k/y')",
                uuid.uuid4(), ORG_A, C_OTHER_ORG,  # org A row pointing at org B's collection
            )  # fmt: skip


async def test_access_function_truth_table(world_db: None, app_db_url: str) -> None:
    async with as_app(app_db_url, user=ADMIN, org=ORG_A) as conn:

        async def can(col: uuid.UUID, usr: uuid.UUID) -> bool:
            return bool(await conn.fetchval("SELECT app_can_access_collection($1, $2)", col, usr))

        assert (
            await can(C_OPEN, UNLISTED) and await can(C_OPEN, LISTED) and await can(C_OPEN, ADMIN)
        )
        assert await can(C_SECRET, LISTED) and await can(C_SECRET, ADMIN)
        assert not await can(C_SECRET, UNLISTED)
        assert not await can(C_OPEN, OUTSIDER) and not await can(C_SECRET, OUTSIDER)  # other tenant
        assert not await can(C_OTHER_ORG, ADMIN) and not await can(uuid.uuid4(), ADMIN)


async def test_every_collection_scoped_table_is_covered_by_rls(pg_url: str) -> None:
    """Fails when a future table with a collection_id forgets the access-aware policy."""
    conn = await asyncpg.connect(pg_url)
    try:
        tables = {
            r["table_name"]
            for r in await conn.fetch(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='collection_id'"
            )
        }
        assert {"documents", "collection_members"} <= tables
        for table in tables:
            policies = " ".join(
                r["qual"] or r["with_check"] or ""
                for r in await conn.fetch(
                    "SELECT qual, with_check FROM pg_policies WHERE tablename = $1", table
                )
            )
            assert "app_can_access_collection" in policies, (
                f"{table}: policy does not check collection access"
            )
    finally:
        await conn.close()
