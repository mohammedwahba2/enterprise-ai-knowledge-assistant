import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.base import to_async_url
from app.modules.identity.models import PasswordReset, RefreshToken, User
from tests.conftest import Outbox, make_client

EMAIL = "layla@example.com"
PASSWORD = "rivers-flow-quietly-9"
V1 = "/api/v1/auth"
COOKIE_DOMAIN = "localhost.local"  # what the stdlib cookie jar assigns to dotless hosts


async def sign_up(
    c: AsyncClient, email: str = EMAIL, password: str = PASSWORD, **kw: str
) -> object:
    return await c.post(
        f"{V1}/sign-up", json={"email": email, "password": password, "display_name": "Layla", **kw}
    )


def csrf(c: AsyncClient) -> dict[str, str]:
    return {"x-csrf-token": c.cookies.get("ka_csrf") or ""}


@asynccontextmanager
async def db(settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(to_async_url(settings.database_url))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


# ---------------- sign-up ----------------


async def test_sign_up_creates_user_and_session(client: AsyncClient) -> None:
    r = await sign_up(client, locale="ar")
    assert r.status_code == 201  # type: ignore[attr-defined]
    body = r.json()  # type: ignore[attr-defined]
    assert body["email"] == EMAIL and body["locale"] == "ar" and body["digit_style"] == "western"
    assert "password" not in json.dumps(body) and "hash" not in json.dumps(body)
    me = await client.get(f"{V1}/me")
    assert me.status_code == 200 and me.json()["id"] == body["id"]


async def test_sign_up_response_headers_are_not_cacheable(client: AsyncClient) -> None:
    r = await sign_up(client)
    assert r.headers["cache-control"] == "no-store"  # type: ignore[attr-defined]


async def test_email_is_normalised_and_unique_case_insensitively(client: AsyncClient) -> None:
    assert (await sign_up(client, "Layla@Example.COM")).status_code == 201  # type: ignore[attr-defined]
    dup = await sign_up(client, "layla@example.com")
    assert dup.status_code == 409 and dup.json()["code"] == "EMAIL_TAKEN"  # type: ignore[attr-defined]
    r = await client.post(
        f"{V1}/sign-in", json={"email": "  LAYLA@example.com ", "password": PASSWORD}
    )
    assert r.status_code == 200


@pytest.mark.parametrize(
    ("password", "reason"),
    [("short", "TOO_SHORT"), ("password123", "TOO_COMMON"), ("layla-secret-1", "CONTAINS_EMAIL")],
)
async def test_weak_password_rejected_with_reasons(
    client: AsyncClient, password: str, reason: str
) -> None:
    r = await sign_up(client, password=password)
    assert r.status_code == 422  # type: ignore[attr-defined]
    body = r.json()  # type: ignore[attr-defined]
    assert body["code"] == "WEAK_PASSWORD" and reason in body["reasons"]
    assert password not in json.dumps(body)


async def test_sign_up_validates_input(client: AsyncClient) -> None:
    bad = [
        {"email": "not-an-email", "password": PASSWORD, "display_name": "x"},
        {"email": EMAIL, "password": PASSWORD, "display_name": "   "},
        {"email": EMAIL, "password": PASSWORD, "display_name": "x" * 81},
        {"email": EMAIL, "password": PASSWORD, "display_name": "x", "locale": "fr"},
        {
            "email": EMAIL,
            "password": PASSWORD,
            "display_name": "x",
            "is_active": False,
        },  # extra field
    ]
    for payload in bad:
        r = await client.post(f"{V1}/sign-up", json=payload)
        assert r.status_code == 422, payload


async def test_password_is_stored_as_argon2id_only(client: AsyncClient, settings: Settings) -> None:
    await sign_up(client)
    async with db(settings) as s:
        user = (await s.scalars(select(User))).one()
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash


async def test_sign_up_is_rate_limited_per_ip(client: AsyncClient, settings: Settings) -> None:
    for i in range(settings.signup_ip_limit):
        r = await sign_up(client, f"user{i}@example.com")
        assert r.status_code == 201  # type: ignore[attr-defined]
    blocked = await sign_up(client, "one-more@example.com")
    assert blocked.status_code == 429  # type: ignore[attr-defined]
    assert int(blocked.headers["retry-after"]) > 0  # type: ignore[attr-defined]


# ---------------- cookies ----------------


async def test_cookie_attributes(client: AsyncClient) -> None:
    r = await sign_up(client)
    raw = r.headers.get_list("set-cookie")  # type: ignore[attr-defined]
    by_name = {c.split("=", 1)[0]: c.lower() for c in raw}
    assert {"ka_at", "ka_rt", "ka_csrf", "ka_session"} <= set(by_name)
    for name in ("ka_at", "ka_rt"):
        assert "httponly" in by_name[name] and "samesite=lax" in by_name[name]
    assert "path=/api;" in by_name["ka_at"] + ";"
    assert "path=/api/v1/auth" in by_name["ka_rt"]
    assert "httponly" not in by_name["ka_csrf"]  # must be readable for double-submit
    assert "httponly" not in by_name["ka_session"]


async def test_secure_flag_follows_configuration(settings: Settings, outbox: Outbox) -> None:
    s = settings.model_copy(update={"cookie_secure": True})
    async with make_client(
        s, email_sender=outbox, ip="198.51.100.1", base_url="https://localhost:8080"
    ) as c:
        r = await sign_up(c)
    assert all("secure" in v.lower() for v in r.headers.get_list("set-cookie"))  # type: ignore[attr-defined]


async def test_refresh_token_not_sent_outside_auth_path(client: AsyncClient) -> None:
    await sign_up(client)
    # the cookie jar honours Path: the refresh cookie is invisible to other API routes
    cookies_for_me = client.cookies.jar
    refresh = next(c for c in cookies_for_me if c.name == "ka_rt")
    assert refresh.path == "/api/v1/auth"


# ---------------- sign-in ----------------


async def test_sign_in_failures_are_indistinguishable(client: AsyncClient) -> None:
    await sign_up(client)
    client.cookies.clear()
    wrong = await client.post(
        f"{V1}/sign-in", json={"email": EMAIL, "password": "wrong-password-1"}
    )
    unknown = await client.post(
        f"{V1}/sign-in", json={"email": "nobody@example.com", "password": "wrong-password-1"}
    )
    assert wrong.status_code == unknown.status_code == 401
    a, b = wrong.json(), unknown.json()
    for body in (a, b):
        body.pop("request_id")
    assert a == b and a["code"] == "INVALID_CREDENTIALS"


async def test_unknown_email_still_runs_a_password_verification(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.identity.passwords import PasswordService

    calls = {"dummy": 0}
    original = PasswordService.verify_dummy

    async def spy(self: PasswordService, pw: str) -> None:
        calls["dummy"] += 1
        await original(self, pw)

    monkeypatch.setattr(PasswordService, "verify_dummy", spy)
    await client.post(
        f"{V1}/sign-in", json={"email": "ghost@example.com", "password": "whatever-123"}
    )
    assert calls["dummy"] == 1


async def test_sign_in_lockout_then_recovery_window(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    client.cookies.clear()
    for _ in range(settings.signin_account_limit):
        r = await client.post(
            f"{V1}/sign-in", json={"email": EMAIL, "password": "wrong-password-1"}
        )
        assert r.status_code == 401
    locked = await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
    assert locked.status_code == 429 and locked.json()["code"] == "RATE_LIMITED"
    assert int(locked.headers["retry-after"]) > 0
    # clearing the counter (what expiry does) restores access
    redis = Redis.from_url(settings.redis_url)
    await redis.flushdb()
    await redis.aclose()
    ok = await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
    assert ok.status_code == 200


async def test_lockout_is_per_ip_so_a_stranger_cannot_lock_the_owner_out(
    client: AsyncClient, settings: Settings, outbox: Outbox
) -> None:
    await sign_up(client)
    client.cookies.clear()
    for _ in range(settings.signin_account_limit):
        await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": "wrong-password-1"})
    # a different client IP can still sign in
    async with make_client(
        settings, email_sender=outbox, ip="192.0.2.99", base_url="http://localhost:8080"
    ) as other:
        assert (
            await other.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
        ).status_code == 200


async def test_successful_sign_in_clears_failure_counter(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    client.cookies.clear()
    for _ in range(settings.signin_account_limit - 1):
        await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": "wrong-password-1"})
    assert (
        await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
    ).status_code == 200
    for _ in range(settings.signin_account_limit - 1):
        r = await client.post(
            f"{V1}/sign-in", json={"email": EMAIL, "password": "wrong-password-1"}
        )
        assert r.status_code == 401  # not 429: counter was reset


async def test_inactive_user_cannot_sign_in_or_use_existing_session(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    async with db(settings) as s:
        await s.execute(update(User).values(is_active=False))
        await s.commit()
    assert (await client.get(f"{V1}/me")).status_code == 401
    client.cookies.clear()
    r = await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"


async def test_weak_old_hash_is_upgraded_on_sign_in(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    stronger = settings.model_copy(update={"argon2_memory_kib": 2048, "argon2_time_cost": 2})
    async with make_client(
        stronger, email_sender=Outbox(), ip="192.0.2.5", base_url="http://localhost:8080"
    ) as c2:
        assert (
            await c2.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
        ).status_code == 200
    async with db(settings) as s:
        h = (await s.scalars(select(User.password_hash))).one()
        assert "m=2048,t=2" in h


# ---------------- authentication / me ----------------


async def test_me_requires_authentication(client: AsyncClient) -> None:
    r = await client.get(f"{V1}/me")
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"


async def test_forged_or_garbage_access_cookie_rejected(client: AsyncClient) -> None:
    for value in ("garbage", "a.b.c", ""):
        client.cookies.set("ka_at", value, domain=COOKIE_DOMAIN, path="/api")
        assert (await client.get(f"{V1}/me")).status_code == 401


async def test_update_locale_and_digit_style(client: AsyncClient) -> None:
    await sign_up(client)
    r = await client.patch(
        f"{V1}/me", json={"locale": "ar", "digit_style": "arabic-indic"}, headers=csrf(client)
    )
    assert r.status_code == 200 and r.json()["locale"] == "ar"
    assert (await client.get(f"{V1}/me")).json()["digit_style"] == "arabic-indic"
    for bad in (
        {"locale": "fr"},
        {"digit_style": "roman"},
        {"email": "x@y.z"},
        {"is_active": False},
    ):
        assert (await client.patch(f"{V1}/me", json=bad, headers=csrf(client))).status_code == 422


# ---------------- CSRF / origin ----------------


async def test_csrf_required_for_authenticated_state_changes(client: AsyncClient) -> None:
    await sign_up(client)
    no_header = await client.patch(f"{V1}/me", json={"locale": "ar"})
    assert no_header.status_code == 403 and no_header.json()["code"] == "CSRF_FAILED"
    wrong = await client.patch(f"{V1}/me", json={"locale": "ar"}, headers={"x-csrf-token": "nope"})
    assert wrong.status_code == 403
    refresh = await client.post(f"{V1}/refresh")
    assert refresh.status_code == 403 and refresh.json()["code"] == "CSRF_FAILED"


async def test_cross_origin_requests_rejected_even_before_login(client: AsyncClient) -> None:
    for headers in ({"origin": "https://evil.example"}, {"sec-fetch-site": "cross-site"}):
        r = await client.post(
            f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD}, headers=headers
        )
        assert r.status_code == 403 and r.json()["code"] == "CSRF_FAILED"
    r = await client.post(
        f"{V1}/sign-out", headers={"origin": "http://localhost:8080.evil.example"}
    )
    assert r.status_code == 403


async def test_non_browser_client_without_origin_is_allowed(client: AsyncClient) -> None:
    del client.headers["origin"]
    assert (await sign_up(client)).status_code == 201  # type: ignore[attr-defined]


# ---------------- refresh rotation ----------------


async def _refresh(c: AsyncClient) -> object:
    return await c.post(f"{V1}/refresh", headers=csrf(c))


def _cookie(c: AsyncClient, name: str) -> str:
    return next(x.value for x in c.cookies.jar if x.name == name and x.value)


async def test_refresh_rotates_token_and_issues_new_access(client: AsyncClient) -> None:
    await sign_up(client)
    old_rt, old_at = _cookie(client, "ka_rt"), _cookie(client, "ka_at")
    r = await _refresh(client)
    assert r.status_code == 200  # type: ignore[attr-defined]
    assert _cookie(client, "ka_rt") != old_rt
    assert _cookie(client, "ka_at") != old_at
    assert (await client.get(f"{V1}/me")).status_code == 200


async def test_reused_refresh_token_revokes_whole_family(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    stolen = _cookie(client, "ka_rt")
    assert (await _refresh(client)).status_code == 200  # type: ignore[attr-defined]
    # age the rotation beyond the benign-race grace window
    async with db(settings) as s:
        await s.execute(
            update(RefreshToken)
            .where(RefreshToken.replaced_by.is_not(None))
            .values(revoked_at=datetime.now(UTC) - timedelta(minutes=5))
        )
        await s.commit()
    attacker = client
    attacker.cookies.set("ka_rt", stolen, domain=COOKIE_DOMAIN, path="/api/v1/auth")
    r = await _refresh(attacker)
    assert r.status_code == 401 and r.json()["code"] == "SESSION_INVALID"  # type: ignore[attr-defined]
    async with db(settings) as s:
        rows = (await s.scalars(select(RefreshToken))).all()
        assert rows and all(row.revoked_at is not None for row in rows)
    # the legitimate user's newest token and access token are dead too
    assert (await client.get(f"{V1}/me")).status_code == 401


async def test_concurrent_rotation_inside_grace_does_not_kill_the_family(
    client: AsyncClient,
) -> None:
    await sign_up(client)
    first = _cookie(client, "ka_rt")
    assert (await _refresh(client)).status_code == 200  # type: ignore[attr-defined]
    newest = _cookie(client, "ka_rt")
    client.cookies.set("ka_rt", first, domain=COOKIE_DOMAIN, path="/api/v1/auth")
    r = await _refresh(client)
    assert r.status_code == 401 and r.json()["code"] == "REFRESH_RACE"  # type: ignore[attr-defined]
    # the family survives: the newest token still works
    client.cookies.set("ka_rt", newest, domain=COOKIE_DOMAIN, path="/api/v1/auth")
    assert (await _refresh(client)).status_code == 200  # type: ignore[attr-defined]


async def test_refresh_token_stored_only_as_hash(client: AsyncClient, settings: Settings) -> None:
    await sign_up(client)
    raw = _cookie(client, "ka_rt")
    async with db(settings) as s:
        dump = (await s.execute(text("SELECT token_hash FROM refresh_tokens"))).scalars().all()
        assert dump and raw not in dump and all(len(h) == 64 for h in dump)


async def test_expired_and_over_age_families_cannot_refresh(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    async with db(settings) as s:
        await s.execute(
            update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    r = await _refresh(client)
    assert r.status_code == 401 and r.json()["code"] == "SESSION_EXPIRED"  # type: ignore[attr-defined]

    async with db(settings) as s:
        await s.execute(
            update(RefreshToken).values(
                expires_at=datetime.now(UTC) + timedelta(days=5),
                family_started_at=datetime.now(UTC)
                - timedelta(days=settings.refresh_family_max_days + 1),
            )
        )
        await s.commit()
    r = await _refresh(client)
    assert r.status_code == 401 and r.json()["code"] == "SESSION_EXPIRED"  # type: ignore[attr-defined]


async def test_refresh_without_cookie_is_unauthorised(client: AsyncClient) -> None:
    await sign_up(client)
    client.cookies.delete("ka_rt", domain=COOKIE_DOMAIN, path="/api/v1/auth")
    r = await _refresh(client)
    assert r.status_code == 401  # type: ignore[attr-defined]


async def test_family_lifetime_is_capped_when_issuing(
    client: AsyncClient, settings: Settings
) -> None:
    await sign_up(client)
    async with db(settings) as s:
        near_cap = datetime.now(UTC) - timedelta(days=settings.refresh_family_max_days - 1)
        await s.execute(update(RefreshToken).values(family_started_at=near_cap))
        await s.commit()
    assert (await _refresh(client)).status_code == 200  # type: ignore[attr-defined]
    async with db(settings) as s:
        newest = (
            await s.scalars(select(RefreshToken).order_by(RefreshToken.created_at.desc()))
        ).first()
        assert newest is not None
        cap = newest.family_started_at + timedelta(days=settings.refresh_family_max_days)
        assert newest.expires_at <= cap + timedelta(seconds=1)


# ---------------- sign-out ----------------


async def test_sign_out_revokes_access_token_immediately(client: AsyncClient) -> None:
    await sign_up(client)
    stolen_access = _cookie(client, "ka_at")
    stolen_refresh = _cookie(client, "ka_rt")
    assert (await client.post(f"{V1}/sign-out")).status_code == 204
    assert client.cookies.get("ka_at") is None
    # replaying the old access token (valid for 15 min by signature) must now fail
    client.cookies.set("ka_at", stolen_access, domain=COOKIE_DOMAIN, path="/api")
    assert (await client.get(f"{V1}/me")).status_code == 401
    # and the refresh token is revoked
    client.cookies.set("ka_rt", stolen_refresh, domain=COOKIE_DOMAIN, path="/api/v1/auth")
    client.cookies.set("ka_csrf", "t", domain=COOKIE_DOMAIN, path="/")
    r = await client.post(f"{V1}/refresh", headers={"x-csrf-token": "t"})
    assert r.status_code == 401


async def test_sign_out_without_session_still_succeeds(client: AsyncClient) -> None:
    assert (await client.post(f"{V1}/sign-out")).status_code == 204


# ---------------- password reset ----------------


async def test_forgot_password_gives_identical_response_for_known_and_unknown(
    client: AsyncClient, outbox: Outbox
) -> None:
    await sign_up(client)
    known = await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
    unknown = await client.post(f"{V1}/password/forgot", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"status": "accepted"}
    assert [m["to"] for m in outbox.messages] == [EMAIL]  # only the real account got mail


async def test_reset_email_contents_and_locale(client: AsyncClient, outbox: Outbox) -> None:
    await sign_up(client, locale="ar")
    await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
    msg = outbox.messages[-1]
    assert "/ar/reset-password#token=" in msg["body"]  # token in fragment, never in the query
    assert "?token=" not in msg["body"]
    assert "كلمة المرور" in msg["subject"]


async def test_full_reset_flow_revokes_all_sessions_and_token_is_single_use(
    client: AsyncClient, outbox: Outbox, settings: Settings
) -> None:
    await sign_up(client)
    session_cookies = {c.name: c.value for c in client.cookies.jar}
    await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
    token = outbox.last_token()
    new_pw = "another-long-quiet-pass-7"
    r = await client.post(f"{V1}/password/reset", json={"token": token, "password": new_pw})
    assert r.status_code == 204
    # the pre-reset session is dead
    client.cookies.clear()
    client.cookies.set("ka_at", session_cookies["ka_at"] or "", domain=COOKIE_DOMAIN, path="/api")
    assert (await client.get(f"{V1}/me")).status_code == 401
    # old password no longer works; new one does
    assert (
        await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": PASSWORD})
    ).status_code == 401
    assert (
        await client.post(f"{V1}/sign-in", json={"email": EMAIL, "password": new_pw})
    ).status_code == 200
    # single use
    again = await client.post(
        f"{V1}/password/reset", json={"token": token, "password": "yet-another-pass-88"}
    )
    assert again.status_code == 400 and again.json()["code"] == "INVALID_TOKEN"


async def test_reset_tokens_are_hashed_expire_and_newer_supersedes_older(
    client: AsyncClient, outbox: Outbox, settings: Settings
) -> None:
    await sign_up(client)
    await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
    first = outbox.last_token()
    await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
    second = outbox.last_token()
    assert first != second
    async with db(settings) as s:
        hashes = (await s.scalars(select(PasswordReset.token_hash))).all()
        assert first not in hashes and second not in hashes
    old = await client.post(
        f"{V1}/password/reset", json={"token": first, "password": "brand-new-passphrase-1"}
    )
    assert old.status_code == 400  # superseded
    async with db(settings) as s:
        await s.execute(
            update(PasswordReset).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    expired = await client.post(
        f"{V1}/password/reset", json={"token": second, "password": "brand-new-passphrase-1"}
    )
    assert expired.status_code == 400 and expired.json()["code"] == "INVALID_TOKEN"


async def test_reset_rejects_weak_password_without_consuming_token(
    client: AsyncClient, outbox: Outbox
) -> None:
    await sign_up(client)
    await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
    token = outbox.last_token()
    weak = await client.post(f"{V1}/password/reset", json={"token": token, "password": "short"})
    assert weak.status_code == 422 and weak.json()["code"] == "WEAK_PASSWORD"
    ok = await client.post(
        f"{V1}/password/reset", json={"token": token, "password": "a-fine-new-passphrase-3"}
    )
    assert ok.status_code == 204


async def test_garbage_reset_tokens_rejected(client: AsyncClient) -> None:
    r = await client.post(
        f"{V1}/password/reset", json={"token": "x" * 43, "password": "a-fine-new-passphrase-3"}
    )
    assert r.status_code == 400 and r.json()["code"] == "INVALID_TOKEN"
    short = await client.post(
        f"{V1}/password/reset", json={"token": "abc", "password": "a-fine-new-passphrase-3"}
    )
    assert short.status_code == 422


async def test_forgot_password_is_rate_limited_per_ip_and_per_email(
    client: AsyncClient, outbox: Outbox, settings: Settings
) -> None:
    await sign_up(client)
    for _ in range(settings.reset_email_limit + 2):
        r = await client.post(f"{V1}/password/forgot", json={"email": EMAIL})
        assert r.status_code == 202  # per-email limit is silent: no oracle
    assert len(outbox.messages) == settings.reset_email_limit  # but mail volume is capped
    for i in range(settings.reset_ip_limit):
        await client.post(f"{V1}/password/forgot", json={"email": f"x{i}@example.com"})
    r = await client.post(f"{V1}/password/forgot", json={"email": "y@example.com"})
    assert r.status_code == 429


async def test_email_failure_does_not_change_response(settings: Settings) -> None:
    class Broken:
        async def send(self, **_: str) -> None:
            raise ConnectionError("smtp down")

    async with make_client(
        settings, email_sender=Broken(), ip="192.0.2.77", base_url="http://localhost:8080"
    ) as c:
        await sign_up(c)
        r = await c.post(f"{V1}/password/forgot", json={"email": EMAIL})
        assert r.status_code == 202


# ---------------- logging hygiene ----------------


async def test_secrets_never_reach_logs(settings: Settings, outbox: Outbox) -> None:
    async with make_client(
        settings, email_sender=outbox, ip="192.0.2.88", base_url="http://localhost:8080"
    ) as c:
        stream = io.StringIO()
        configure_logging("DEBUG", json_logs=True, stream=stream)
        await sign_up(c)
        raw_refresh, raw_access = _cookie(c, "ka_rt"), _cookie(c, "ka_at")
        await c.post(f"{V1}/sign-in", json={"email": EMAIL, "password": "wrong-password-xyz"})
        await c.post(f"{V1}/password/forgot", json={"email": EMAIL})
        token = outbox.last_token()
        await c.post(
            f"{V1}/password/reset", json={"token": token, "password": "a-fine-new-passphrase-3"}
        )
    logs = stream.getvalue()
    for secret in (
        PASSWORD,
        "wrong-password-xyz",
        "a-fine-new-passphrase-3",
        raw_refresh,
        raw_access,
        token,
        EMAIL,
    ):
        assert secret not in logs, f"secret leaked to logs: {secret[:6]}…"
    events = {json.loads(line)["event"] for line in logs.splitlines() if line.strip()}
    assert {"auth.sign_up", "auth.sign_in.failure", "auth.password_reset.completed"} <= events
