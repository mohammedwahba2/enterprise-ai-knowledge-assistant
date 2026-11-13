import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.tenant import TenantScope, bind_scope
from app.modules.access.policies import Role
from app.modules.identity.deps import CurrentUser
from app.modules.identity.models import User
from app.modules.tenancy.models import Membership


@dataclass
class TenantCtx:
    """An authenticated user acting inside ONE organization they belong to."""

    db: AsyncSession
    user: User
    org_id: uuid.UUID
    role: Role


async def own_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A session of this handler's own.

    Deliberately a different dependency from `get_session` (which `current_user` uses): FastAPI
    caches dependencies per request, so sharing it would hand the handler a session whose
    transaction began before its tenant scope was bound.
    """
    async with request.app.state.sessionmaker() as session:
        yield session


OwnSession = Annotated[AsyncSession, Depends(own_session)]


async def tenant_ctx(
    org_id: uuid.UUID, user: CurrentUser, request: Request
) -> AsyncIterator[TenantCtx]:
    """Resolve `{org_id}` from the URL against the caller's memberships.

    The session is scoped to (user, org) so Postgres RLS enforces the boundary as well. A caller
    who is not a member gets the SAME 404 as for an organization that does not exist: neither
    existence nor membership is revealed.
    """
    async with request.app.state.sessionmaker() as session:
        bind_scope(session, TenantScope(user_id=user.id, org_id=org_id))
        membership = await session.scalar(
            select(Membership).where(
                Membership.organization_id == org_id, Membership.user_id == user.id
            )
        )
        if membership is None:
            raise AppError(404, "NOT_FOUND", "Not Found")
        yield TenantCtx(db=session, user=user, org_id=org_id, role=Role(membership.role))


Tenant = Annotated[TenantCtx, Depends(tenant_ctx)]
