import asyncio

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

TABLES = {
    "users", "refresh_tokens", "password_resets", "organizations", "memberships", "invitations",
    "collections", "collection_members", "documents", "document_pages", "chunks", "ingestion_jobs",
}  # fmt: skip


async def _tables(url: str) -> set[str]:
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return {r["tablename"] for r in rows}
    finally:
        await conn.close()


async def _recreate_db(admin_url: str, name: str) -> None:
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {name}")
        await conn.execute(f"CREATE DATABASE {name}")
    finally:
        await conn.close()


def test_migrations_apply_and_roll_back_cleanly(
    pg_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_recreate_db(pg_url, "migtest"))
    target = pg_url.rsplit("/", 1)[0] + "/migtest"
    monkeypatch.setenv("DATABASE_URL", target)
    cfg = Config("alembic.ini")

    command.upgrade(cfg, "head")
    assert asyncio.run(_tables(target)) >= TABLES

    command.downgrade(cfg, "base")
    assert not (TABLES & asyncio.run(_tables(target)))

    command.upgrade(cfg, "head")  # and forward again
    assert asyncio.run(_tables(target)) >= TABLES
