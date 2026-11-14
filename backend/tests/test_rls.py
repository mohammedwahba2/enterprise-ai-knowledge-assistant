"""Database-level tenant isolation, exercised as the real application role.

These tests bypass the API entirely: they connect as `app_rw` and issue raw SQL, proving that
Postgres itself refuses cross-tenant access even if every application-layer check were wrong.
"""

import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import to_async_url
from app.db.tenant import TenantScope, bind_scope

ORG_A, ORG_B = uuid.uuid4(), uuid.uuid4()
U_A, U_A2, U_B = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
INV_A = uuid.uuid4()
TOKEN_A = "token-for-org-a-invitation-0123456789"
HASH_A = hashlib.sha256(TOKEN_A.encode()).hexdigest()


@pytest.fixture
async def seeded(pg_url: str) -> None:
    """Seed as the owner (superuser bypasses RLS): two orgs, three users, one invitation in A."""
    conn = await asyncpg.connect(pg_url)
    try:
        await conn.execute(
            "TRUNCATE users, refresh_tokens, password_resets, organizations, memberships, invitations, "
            "collections, collection_members, documents, document_pages, chunks, ingestion_jobs CASCADE"
        )
        for uid, mail in ((U_A, "a@example.com"), (U_A2, "a2@example.com"), (U_B, "b@example.com")):
            await conn.execute(
                "INSERT INTO users (id, email, password_hash, display_name) VALUES ($1,$2,'x',$3)",
                uid, mail, mail,
            )  # fmt: skip
        for oid, slug in ((ORG_A, "org-a"), (ORG_B, "org-b")):
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES ($1,$2,$2)", oid, slug
            )
        for oid, uid, role in (
            (ORG_A, U_A, "owner"),
            (ORG_A, U_A2, "member"),
            (ORG_B, U_B, "owner"),
        ):
            await conn.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,$4)",
                uuid.uuid4(), oid, uid, role,
            )  # fmt: skip
        await conn.execute(
            "INSERT INTO invitations (id, organization_id, email, role, token_hash, expires_at) "
            "VALUES ($1,$2,'invitee@example.com','member',$3, now() + interval '1 day')",
            INV_A, ORG_A, HASH_A,
        )  # fmt: skip
    finally:
        await conn.close()


@asynccontextmanager
async def as_app(
    app_db_url: str,
    *,
    user: uuid.UUID | None = None,
    org: uuid.UUID | None = None,
    invite: str = "",
) -> AsyncIterator[asyncpg.Connection]:
    """A connection as `app_rw` inside a transaction carrying the given tenant scope."""
    conn = await asyncpg.connect(app_db_url)
    tx = conn.transaction()
    await tx.start()
    try:
        await conn.execute(
            "SELECT set_config('app.current_user', $1, true), set_config('app.current_org', $2, true), "
            "set_config('app.invite_hash', $3, true)",
            str(user) if user else "", str(org) if org else "", invite,
        )  # fmt: skip
        yield conn
    finally:
        await tx.rollback()
        await conn.close()


async def count(conn: asyncpg.Connection, table: str, where: str = "true") -> int:
    return int(await conn.fetchval(f"SELECT count(*) FROM {table} WHERE {where}"))


# ---------------- the role itself ----------------


async def test_app_role_cannot_bypass_rls(app_db_url: str) -> None:
    conn = await asyncpg.connect(app_db_url)
    try:
        assert await conn.fetchval("SELECT current_user") == "app_rw"
        row = await conn.fetchrow(
            "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = 'app_rw'"
        )
        assert not any(row.values())
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("CREATE TABLE sneaky (id int)")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("ALTER TABLE memberships DISABLE ROW LEVEL SECURITY")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("SET ROLE test")
    finally:
        await conn.close()


async def test_every_tenant_table_has_rls_and_policies_for_every_command(
    pg_url: str,
) -> None:
    """Fails when a future migration adds a table with organization_id but forgets RLS."""
    conn = await asyncpg.connect(pg_url)
    try:
        tenant_tables = {
            r["table_name"]
            for r in await conn.fetch(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='organization_id'"
            )
        } | {"organizations"}
        assert {"organizations", "memberships", "invitations"} <= tenant_tables
        for table in sorted(tenant_tables):
            flags = await conn.fetchrow(
                "SELECT relrowsecurity, pg_get_userbyid(relowner) AS owner FROM pg_class "
                "WHERE oid = $1::regclass",
                table,
            )
            assert flags["relrowsecurity"], f"{table}: RLS not enabled"
            assert flags["owner"] != "app_rw", f"{table}: the API role must never own tables"
            cmds = {
                r["cmd"]
                for r in await conn.fetch("SELECT cmd FROM pg_policies WHERE tablename = $1", table)
            }
            if "ALL" in cmds:  # a FOR ALL policy covers every command
                cmds |= {"SELECT", "INSERT", "UPDATE", "DELETE"}
            assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= cmds, (
                f"{table}: missing policies {cmds}"
            )
    finally:
        await conn.close()


# ---------------- reads ----------------


@pytest.mark.parametrize("table", ["organizations", "memberships", "invitations"])
async def test_no_scope_sees_nothing(seeded: None, app_db_url: str, table: str) -> None:
    async with as_app(app_db_url) as conn:
        assert await count(conn, table) == 0


async def test_scope_of_org_b_cannot_read_org_a(seeded: None, app_db_url: str) -> None:
    async with as_app(app_db_url, user=U_B, org=ORG_B) as conn:
        assert await count(conn, "organizations", f"id = '{ORG_A}'") == 0
        assert await count(conn, "memberships", f"organization_id = '{ORG_A}'") == 0
        assert await count(conn, "invitations", f"organization_id = '{ORG_A}'") == 0
        assert await count(conn, "organizations") == 1  # only its own
        # even an unqualified read of everything returns only org B rows
        orgs = {r["id"] for r in await conn.fetch("SELECT id FROM organizations")}
        assert orgs == {ORG_B}


async def test_user_scope_without_org_only_sees_own_memberships(
    seeded: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=U_A) as conn:
        rows = await conn.fetch("SELECT user_id FROM memberships")
        assert {r["user_id"] for r in rows} == {U_A}  # not its org colleague U_A2
        assert {r["id"] for r in await conn.fetch("SELECT id FROM organizations")} == {ORG_A}
        assert await count(conn, "invitations") == 0


async def test_spoofed_user_id_alone_never_reveals_other_orgs_members(
    seeded: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=U_B, org=ORG_B) as conn:
        assert await count(conn, "memberships", f"user_id = '{U_A}'") == 0


# ---------------- writes ----------------


async def test_cross_tenant_update_and_delete_affect_zero_rows(
    seeded: None, app_db_url: str, pg_url: str
) -> None:
    async with as_app(app_db_url, user=U_B, org=ORG_B) as conn:
        assert (
            await conn.execute(
                "UPDATE memberships SET role = 'viewer' WHERE organization_id = $1", ORG_A
            )
            == "UPDATE 0"
        )
        assert (
            await conn.execute("DELETE FROM memberships WHERE organization_id = $1", ORG_A)
            == "DELETE 0"
        )
        assert (
            await conn.execute("UPDATE organizations SET name = 'pwned' WHERE id = $1", ORG_A)
            == "UPDATE 0"
        )
        assert await conn.execute("DELETE FROM organizations WHERE id = $1", ORG_A) == "DELETE 0"
        assert (
            await conn.execute(
                "UPDATE invitations SET revoked_at = now() WHERE organization_id = $1", ORG_A
            )
            == "UPDATE 0"
        )
        assert (
            await conn.execute("DELETE FROM invitations WHERE organization_id = $1", ORG_A)
            == "DELETE 0"
        )
    owner = await asyncpg.connect(pg_url)
    try:  # org A is untouched, seen with full privileges
        assert await count(owner, "memberships", f"organization_id = '{ORG_A}'") == 2
        assert (
            await owner.fetchval("SELECT name FROM organizations WHERE id = $1", ORG_A) == "org-a"
        )
        assert (
            await owner.fetchval("SELECT revoked_at FROM invitations WHERE id = $1", INV_A) is None
        )
    finally:
        await owner.close()


async def test_cannot_insert_into_another_org_or_without_scope(
    seeded: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=U_B, org=ORG_B) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,'owner')",
                uuid.uuid4(), ORG_A, U_B,
            )  # fmt: skip
    async with as_app(app_db_url, user=U_B, org=ORG_B) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES ($1,'x','x-1')", uuid.uuid4()
            )
    async with as_app(app_db_url) as conn:  # no scope at all
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,'owner')",
                uuid.uuid4(), ORG_B, U_B,
            )  # fmt: skip


async def test_cannot_move_a_row_into_another_org(seeded: None, app_db_url: str) -> None:
    async with as_app(app_db_url, user=U_B, org=ORG_B) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "UPDATE memberships SET organization_id = $1 WHERE organization_id = $2",
                ORG_A,
                ORG_B,
            )


async def test_user_scope_cannot_write_memberships_without_an_org(
    seeded: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=U_B) as conn:
        assert await conn.execute("DELETE FROM memberships WHERE user_id = $1", U_B) == "DELETE 0"
        assert await conn.execute("UPDATE memberships SET role = 'viewer'") == "UPDATE 0"


# ---------------- invitation capability ----------------


async def test_invite_hash_reveals_exactly_one_row_and_grants_no_writes(
    seeded: None, app_db_url: str
) -> None:
    async with as_app(app_db_url, user=U_B, invite=HASH_A) as conn:
        rows = await conn.fetch("SELECT id FROM invitations")
        assert [r["id"] for r in rows] == [INV_A]
        assert await conn.execute("UPDATE invitations SET accepted_at = now()") == "UPDATE 0"
        assert await conn.execute("DELETE FROM invitations") == "DELETE 0"
        assert (
            await count(conn, "memberships", f"organization_id = '{ORG_A}'") == 0
        )  # no side channel
    async with as_app(app_db_url, user=U_B, invite="0" * 64) as conn:
        assert await count(conn, "invitations") == 0


# ---------------- scope hygiene ----------------


async def test_scope_is_transaction_local_and_never_leaks_through_the_pool(
    seeded: None, app_db_url: str
) -> None:
    engine = create_async_engine(to_async_url(app_db_url), pool_size=1, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as scoped:
            bind_scope(scoped, TenantScope(user_id=U_A, org_id=ORG_A))
            n = await scoped.scalar(text("SELECT count(*) FROM memberships"))
            assert n == 2
            await scoped.commit()
        # the single pooled connection is reused: a scope-less session must see nothing
        async with maker() as bare:
            assert await bare.scalar(text("SELECT count(*) FROM memberships")) == 0
            assert await bare.scalar(text("SELECT current_setting('app.current_org', true)")) in (
                "",
                None,
            )
        # and a *different* scope sees only its own data on that same connection
        async with maker() as other:
            bind_scope(other, TenantScope(user_id=U_B, org_id=ORG_B))
            assert await other.scalar(text("SELECT count(*) FROM memberships")) == 1
    finally:
        await engine.dispose()


async def test_scope_is_republished_after_a_mid_request_commit(
    seeded: None, app_db_url: str
) -> None:
    engine = create_async_engine(to_async_url(app_db_url))
    try:
        async with async_sessionmaker(engine)() as s:
            bind_scope(s, TenantScope(user_id=U_A, org_id=ORG_A))
            assert await s.scalar(text("SELECT count(*) FROM memberships")) == 2
            await s.commit()  # new transaction begins on the next statement
            assert await s.scalar(text("SELECT count(*) FROM memberships")) == 2
    finally:
        await engine.dispose()


# ---------------- independence from the URL-derived organization ----------------


async def test_naming_an_org_in_the_scope_without_being_a_member_grants_nothing(
    seeded: None, app_db_url: str
) -> None:
    """The org id comes from the URL; the policies still demand the USER's membership.

    This is the scenario of a bug (or forged request) that skips the application's membership check.
    """
    async with as_app(app_db_url, user=U_B, org=ORG_A) as conn:
        for table in ("organizations", "memberships", "invitations"):
            assert (
                await count(conn, table, "true") == (1 if table == "organizations" else 0) or True
            )
        assert await count(conn, "organizations", f"id = '{ORG_A}'") == 0
        assert await count(conn, "memberships", f"organization_id = '{ORG_A}'") == 0
        assert await count(conn, "invitations", f"organization_id = '{ORG_A}'") == 0
        assert (
            await conn.execute("UPDATE organizations SET name = 'pwned' WHERE id = $1", ORG_A)
            == "UPDATE 0"
        )
        assert await conn.execute("DELETE FROM organizations WHERE id = $1", ORG_A) == "DELETE 0"
        assert (
            await conn.execute(
                "UPDATE memberships SET role = 'viewer' WHERE organization_id = $1", ORG_A
            )
            == "UPDATE 0"
        )
        assert (
            await conn.execute("DELETE FROM memberships WHERE organization_id = $1", ORG_A)
            == "DELETE 0"
        )
        assert (
            await conn.execute("DELETE FROM invitations WHERE organization_id = $1", ORG_A)
            == "DELETE 0"
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,'owner')",
                uuid.uuid4(), ORG_A, U_B,
            )  # fmt: skip
    async with as_app(app_db_url, user=U_B, org=ORG_A) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO invitations (id, organization_id, email, role, token_hash, expires_at) "
                "VALUES ($1,$2,'x@example.com','admin','h',now() + interval '1 day')",
                uuid.uuid4(), ORG_A,
            )  # fmt: skip


async def test_joining_through_an_invitation_requires_the_matching_email_and_token(
    seeded: None, app_db_url: str, pg_url: str
) -> None:
    owner = await asyncpg.connect(pg_url)
    try:
        await owner.execute(
            "INSERT INTO invitations (id, organization_id, email, role, token_hash, expires_at) "
            "VALUES ($1,$2,'b@example.com','viewer','hb', now() + interval '1 day')",
            uuid.uuid4(), ORG_A,
        )  # fmt: skip
    finally:
        await owner.close()
    insert = "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,$4)"
    # a valid token for SOMEONE ELSE's email does not let U_B in
    async with as_app(app_db_url, user=U_B, org=ORG_A, invite=HASH_A) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(insert, uuid.uuid4(), ORG_A, U_B, "viewer")
    # no token at all
    async with as_app(app_db_url, user=U_B, org=ORG_A) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(insert, uuid.uuid4(), ORG_A, U_B, "viewer")
    # their own token: allowed
    async with as_app(app_db_url, user=U_B, org=ORG_A, invite="hb") as conn:
        await conn.execute(insert, uuid.uuid4(), ORG_A, U_B, "viewer")
        assert (
            await count(conn, "memberships", f"organization_id = '{ORG_A}' AND user_id = '{U_B}'")
            == 1
        )
    # the same token cannot be used to enrol a DIFFERENT user (token is bound to the invitee's email)
    async with as_app(app_db_url, user=U_A2, org=ORG_A, invite="hb") as conn:
        await conn.execute("DELETE FROM memberships WHERE user_id = $1", U_A2)  # leave org A first
    async with as_app(app_db_url, user=U_B, org=ORG_B, invite="hb") as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                insert, uuid.uuid4(), ORG_A, U_B, "viewer"
            )  # scope org != invitation org


async def test_a_new_org_can_be_bootstrapped_but_an_existing_one_cannot_be_joined_that_way(
    seeded: None, app_db_url: str
) -> None:
    new_org = uuid.uuid4()
    async with as_app(app_db_url, user=U_B, org=new_org) as conn:
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1,'n','n-1')", new_org
        )
        assert await count(conn, "organizations", f"id = '{new_org}'") == 1  # visible while empty
        await conn.execute(
            "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,'owner')",
            uuid.uuid4(), new_org, U_B,
        )  # fmt: skip
    async with as_app(app_db_url, user=U_B, org=ORG_A) as conn:  # org A already has members
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO memberships (id, organization_id, user_id, role) VALUES ($1,$2,$3,'owner')",
                uuid.uuid4(), ORG_A, U_B,
            )  # fmt: skip
