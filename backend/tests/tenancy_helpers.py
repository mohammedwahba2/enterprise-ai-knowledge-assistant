"""Shared helpers for tenancy tests: build browser-like clients for distinct users."""

import itertools
import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import to_async_url
from app.db.tenant import TenantScope, bind_scope
from tests.conftest import Outbox, make_client
from tests.test_auth_flow import csrf

PASSWORD = "rivers-flow-quietly-9"
V1 = "/api/v1"
_ip = itertools.count(10)


@dataclass
class Person:
    email: str
    name: str
    client: AsyncClient
    user_id: str = ""

    def h(self) -> dict[str, str]:
        return csrf(self.client)

    async def post(self, path: str, json: object | None = None) -> Response:
        return await self.client.post(f"{V1}{path}", json=json, headers=self.h())

    async def patch(self, path: str, json: object) -> Response:
        return await self.client.patch(f"{V1}{path}", json=json, headers=self.h())

    async def delete(self, path: str) -> Response:
        return await self.client.delete(f"{V1}{path}", headers=self.h())

    async def get(self, path: str) -> Response:
        return await self.client.get(f"{V1}{path}")


@dataclass
class World:
    settings: Settings
    outbox: Outbox
    stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    async def person(self, name: str, email: str | None = None) -> Person:
        email = email or f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com"
        client = await self.stack.enter_async_context(
            make_client(self.settings, email_sender=self.outbox, ip=f"203.0.113.{next(_ip)}")
        )
        r = await client.post(
            f"{V1}/auth/sign-up", json={"email": email, "password": PASSWORD, "display_name": name}
        )
        assert r.status_code == 201, r.text
        return Person(email, name, client, r.json()["id"])

    async def org(self, owner: Person, name: str = "Acme") -> dict[str, str]:
        r = await owner.post("/orgs", {"name": name})
        assert r.status_code == 201, r.text
        return dict(r.json())

    async def join(self, owner: Person, org_id: str, person: Person, role: str) -> dict[str, str]:
        """Invite `person` into the org with `role` and have them accept. Returns the new org view."""
        r = await owner.post(f"/orgs/{org_id}/invitations", {"email": person.email, "role": role})
        assert r.status_code == 201, r.text
        token = self.outbox.last_token()
        a = await person.post("/invitations/accept", {"token": token})
        assert a.status_code == 200, a.text
        return dict(a.json())

    async def member_id(self, viewer: Person, org_id: str, user_id: str) -> str:
        r = await viewer.get(f"/orgs/{org_id}/members")
        return str(next(m["id"] for m in r.json() if m["user_id"] == user_id))

    @asynccontextmanager
    async def scoped_db(self, org_id: str, user_id: str) -> AsyncIterator[AsyncSession]:
        """Direct DB access as the app role, scoped as a member (to set up states the API can't)."""
        engine = create_async_engine(to_async_url(self.settings.database_url))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                bind_scope(
                    session, TenantScope(user_id=uuid.UUID(user_id), org_id=uuid.UUID(org_id))
                )
                yield session
        finally:
            await engine.dispose()

    async def aclose(self) -> None:
        await self.stack.aclose()
