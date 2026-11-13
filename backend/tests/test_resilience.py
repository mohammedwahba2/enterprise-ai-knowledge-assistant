"""Failure-mode tests: Redis outages, concurrent refreshes, and total session revocation."""

import asyncio
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import Settings
from app.modules.identity.models import PasswordReset, RefreshToken, User
from tests.conftest import Outbox, make_client
from tests.test_auth_flow import EMAIL, PASSWORD, V1, csrf, db, sign_up

DEAD_REDIS = "redis://127.0.0.1:1/0"  # nothing listens here


def _copy_cookies(src: AsyncClient, dst: AsyncClient) -> None:
    for cookie in src.cookies.jar:
        dst.cookies.jar.set_cookie(cookie)


# ---------------- Redis unavailable ----------------


async def test_sign_in_sign_up_and_reset_fail_closed_when_redis_is_down(
    settings: Settings, outbox: Outbox
) -> None:
    async with make_client(settings, email_sender=outbox) as live:
        await sign_up(live)
        await live.post(f"{V1}/password/forgot", json={"email": EMAIL})
        token = outbox.last_token()

    dead = settings.model_copy(update={"redis_url": DEAD_REDIS})
    async with make_client(dead, email_sender=outbox, ip="198.51.100.9") as c:
        bodies = {
            "sign-in": {"email": EMAIL, "password": PASSWORD},  # correct credentials
            "sign-up": {"email": "new@example.com", "password": PASSWORD, "display_name": "N"},
            "password/forgot": {"email": EMAIL},
            "password/reset": {"token": token, "password": "a-fine-new-passphrase-3"},
        }
        for path, body in bodies.items():
            r = await c.post(f"{V1}/{path}", json=body)
            assert r.status_code == 503, path
            assert r.json()["code"] == "SERVICE_UNAVAILABLE", path
            assert r.headers["retry-after"], path
            assert not r.headers.get_list("set-cookie"), f"{path} must not issue a session"
        # nothing was changed by the failed attempts
        async with db(settings) as s:
            assert (await s.scalars(select(User))).all().__len__() == 1
            assert (await s.scalars(select(PasswordReset.used_at))).first() is None


async def test_authentication_does_not_depend_on_redis(settings: Settings, outbox: Outbox) -> None:
    async with make_client(settings, email_sender=outbox) as live:
        await sign_up(live)
        dead = settings.model_copy(update={"redis_url": DEAD_REDIS})
        async with make_client(dead, email_sender=outbox) as c:
            _copy_cookies(live, c)
            assert (await c.get(f"{V1}/me")).status_code == 200
            assert (await c.post(f"{V1}/refresh", headers=csrf(c))).status_code == 200


async def test_sign_out_revokes_even_when_redis_is_down(settings: Settings, outbox: Outbox) -> None:
    async with make_client(settings, email_sender=outbox) as live:
        await sign_up(live)
        stolen = {c.name: c.value for c in live.cookies.jar}
        dead = settings.model_copy(update={"redis_url": DEAD_REDIS})
        async with make_client(dead, email_sender=outbox) as c:
            _copy_cookies(live, c)
            assert (await c.post(f"{V1}/sign-out")).status_code == 204
        # Redis is back: a copy of the old access token must still be rejected (DB is the truth).
        live.cookies.clear()
        live.cookies.set("ka_at", stolen["ka_at"] or "", domain="localhost.local", path="/api")
        assert (await live.get(f"{V1}/me")).status_code == 401


async def test_revocation_written_to_the_database_is_enforced_without_any_cache(
    client: AsyncClient, settings: Settings
) -> None:
    """Simulates a revocation whose cache write was lost: the access token must still die."""
    await sign_up(client)
    assert (await client.get(f"{V1}/me")).status_code == 200
    async with db(settings) as s:
        await s.execute(update(RefreshToken).values(revoked_at=datetime.now(UTC)))
        await s.commit()
    assert (await client.get(f"{V1}/me")).status_code == 401


async def test_session_dies_with_its_refresh_family_expiry(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    async with db(settings) as s:
        await s.execute(
            update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    assert (await client.get(f"{V1}/me")).status_code == 401


# ---------------- concurrent refresh ----------------


async def test_simultaneous_refreshes_produce_exactly_one_descendant(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    results = await asyncio.gather(
        *(client.post(f"{V1}/refresh", headers=csrf(client)) for _ in range(8))
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200] + [401] * 7
    assert {r.json()["code"] for r in results if r.status_code == 401} == {"REFRESH_RACE"}
    winners = [r for r in results if r.status_code == 200]
    assert len(winners) == 1 and winners[0].headers.get_list("set-cookie")
    assert not any(r.headers.get_list("set-cookie") for r in results if r.status_code == 401)
    async with db(settings) as s:
        rows = (await s.scalars(select(RefreshToken))).all()
        assert len(rows) == 2  # the original and exactly one child
        live = [r for r in rows if r.revoked_at is None]
        assert len(live) == 1 and len({r.family_id for r in rows}) == 1


async def test_after_the_race_the_family_continues_from_the_single_child(
    client: AsyncClient,
) -> None:
    await sign_up(client)
    first = next(c.value for c in client.cookies.jar if c.name == "ka_rt")
    await asyncio.gather(*(client.post(f"{V1}/refresh", headers=csrf(client)) for _ in range(3)))
    assert (await client.get(f"{V1}/me")).status_code == 200  # jar holds the winner's cookies
    child = next(c.value for c in client.cookies.jar if c.name == "ka_rt")
    assert child != first
    assert (await client.post(f"{V1}/refresh", headers=csrf(client))).status_code == 200


# ---------------- password reset revokes everything ----------------


async def test_reset_revokes_every_session_and_family_of_the_user_only(
    settings: Settings, outbox: Outbox
) -> None:
    async with make_client(settings, email_sender=outbox, ip="203.0.113.1") as a:
        await sign_up(a)
        other = await a.post(
            f"{V1}/sign-up",
            json={"email": "other@example.com", "password": PASSWORD, "display_name": "O"},
        )
        assert other.status_code == 201
        other_cookies = {c.name: c.value for c in a.cookies.jar}  # the bystander's session

    stack = AsyncExitStack()
    sessions: list[AsyncClient] = []
    for i in range(3):  # three devices for Layla, one of them rotated several times
        client = await stack.enter_async_context(
            make_client(settings, email_sender=outbox, ip=f"203.0.113.{10 + i}")
        )
        sessions.append(client)
        await sessions[-1].post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
        if i == 0:
            for _ in range(3):
                assert (
                    await sessions[0].post(f"{V1}/refresh", headers=csrf(sessions[0]))
                ).status_code == 200
    try:
        for s in sessions:
            assert (await s.get(f"{V1}/me")).status_code == 200
        stale_refresh = [
            next(c.value for c in s.cookies.jar if c.name == "ka_rt") for s in sessions
        ]

        async with make_client(settings, email_sender=outbox, ip="198.51.100.77") as anon:
            await anon.post(f"{V1}/password/forgot", json={"email": EMAIL})
            await anon.post(
                f"{V1}/password/forgot", json={"email": EMAIL}
            )  # two outstanding tokens
            r = await anon.post(
                f"{V1}/password/reset",
                json={"token": outbox.last_token(), "password": "a-fine-new-passphrase-3"},
            )
            assert r.status_code == 204

        # every device is out: access tokens rejected, refresh tokens rejected
        for s, rt in zip(sessions, stale_refresh, strict=True):
            assert (await s.get(f"{V1}/me")).status_code == 401
            s.cookies.set("ka_rt", rt or "", domain="localhost.local", path="/api/v1/auth")
            assert (await s.post(f"{V1}/refresh", headers=csrf(s))).status_code == 401

        async with db(settings) as dbs:
            layla = (await dbs.scalars(select(User).where(User.email == EMAIL))).one()
            tokens = (
                await dbs.scalars(select(RefreshToken).where(RefreshToken.user_id == layla.id))
            ).all()
            assert tokens and all(t.revoked_at is not None for t in tokens)
            assert (
                len({t.family_id for t in tokens}) == 4
            )  # sign-up + 3 sign-ins: all families, not just one
            resets = (await dbs.scalars(select(PasswordReset.used_at))).all()
            assert resets and all(
                u is not None for u in resets
            )  # every outstanding reset token spent

        # the bystander is untouched
        async with make_client(settings, email_sender=outbox, ip="203.0.113.50") as o:
            for name, value in other_cookies.items():
                o.cookies.set(
                    name,
                    value or "",
                    domain="localhost.local",
                    path="/api" if name == "ka_at" else "/",
                )
            assert (await o.get(f"{V1}/me")).status_code == 200
    finally:
        await stack.aclose()
