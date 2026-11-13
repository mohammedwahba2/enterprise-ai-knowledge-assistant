import uuid
from collections.abc import AsyncIterator

import uuid_utils
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def new_id() -> uuid.UUID:
    """UUIDv7: time-ordered, so primary-key indexes stay append-mostly."""
    return uuid.UUID(str(uuid_utils.uuid7()))


def to_async_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(to_async_url(database_url), pool_pre_ping=True, pool_size=10)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session
