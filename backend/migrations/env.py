import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.base import Base, to_async_url
from app.modules.identity import models  # noqa: F401  (register tables)
from app.modules.tenancy import models as tenancy_models  # noqa: F401
from app.modules.documents import models as documents_models  # noqa: F401
from app.modules.processing import models as processing_models  # noqa: F401
from app.modules.chat import models as chat_models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return to_async_url(os.environ.get("DATABASE_URL") or get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
