"""Tenant scope: the per-transaction context that Postgres row-level security policies read.

A session carries a `TenantScope` in `session.info`. On EVERY transaction begin we publish it
with `set_config(..., is_local => true)`, so values live only for that transaction and can never
leak to another request through the connection pool. A session without a scope publishes nothing,
the policies see NULLs, and every tenant table reads as empty (fail closed).
"""

import uuid
from dataclasses import dataclass, replace

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

_SET = text(
    "SELECT set_config('app.current_user', :user_id, true), "
    "set_config('app.current_org', :org_id, true), "
    "set_config('app.invite_hash', :invite_hash, true)"
)


@dataclass(frozen=True)
class TenantScope:
    user_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    invite_hash: str | None = None

    def params(self) -> dict[str, str]:
        return {
            "user_id": str(self.user_id) if self.user_id else "",
            "org_id": str(self.org_id) if self.org_id else "",
            "invite_hash": self.invite_hash or "",
        }


@event.listens_for(Session, "after_begin")
def _publish_scope(session: Session, _tx: SessionTransaction, connection: Connection) -> None:
    scope: TenantScope | None = session.info.get("tenant_scope")
    if scope is not None:
        connection.execute(_SET, scope.params())


def bind_scope(session: AsyncSession, scope: TenantScope) -> None:
    """Attach a scope before the first query; it is re-published on each new transaction.

    Refuses to run on a session that already has an open transaction: that transaction began
    without the scope, so the policies would silently see nothing.
    """
    if session.in_transaction():
        raise RuntimeError("bind_scope() must be called before the session starts a transaction")
    session.info["tenant_scope"] = scope


async def change_scope(session: AsyncSession, **changes: object) -> None:
    """Change the scope mid-transaction (e.g. after resolving an invitation to its org)."""
    current: TenantScope = session.info.get("tenant_scope") or TenantScope()
    updated = replace(current, **changes)  # type: ignore[arg-type]
    session.info["tenant_scope"] = updated
    await session.execute(_SET, updated.params())
