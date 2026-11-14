import hmac
import uuid
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request, Response
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import get_session
from app.modules.identity.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER
from app.modules.identity.models import RefreshToken, User
from app.modules.identity.rate_limit import RateLimiter
from app.modules.identity.tokens import TokenError, decode_access_token

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

Session = Annotated[AsyncSession, Depends(get_session)]


def settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(settings_dep)]


def limiter_dep(request: Request) -> RateLimiter:
    return request.app.state.limiter  # type: ignore[no-any-return]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def origin_guard(request: Request, settings: SettingsDep) -> None:
    """Reject cross-site state-changing requests (login CSRF included).

    Browsers always send Origin on cross-origin POSTs; non-browser clients do not carry cookies
    automatically, so a missing Origin with no cross-site Fetch metadata is allowed.
    """
    if request.method in SAFE_METHODS:
        return
    allowed = urlsplit(settings.app_origin)
    origin = request.headers.get("origin")
    if origin is not None:
        got = urlsplit(origin)
        if (got.scheme, got.netloc) != (allowed.scheme, allowed.netloc):
            raise AppError(403, "CSRF_FAILED", "Cross-origin request rejected")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise AppError(403, "CSRF_FAILED", "Cross-site request rejected")


def csrf_guard(request: Request) -> None:
    """Double-submit token for cookie-authenticated, state-changing requests."""
    if request.method in SAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise AppError(403, "CSRF_FAILED", "CSRF token missing or invalid")


async def session_alive(session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """The session's refresh family still has a live token (database = source of truth)."""
    return bool(
        await session.scalar(
            select(
                exists().where(
                    RefreshToken.family_id == session_id,
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > func.now(),
                )
            )
        )
    )


async def current_user(
    request: Request,
    session: Session,
    settings: SettingsDep,
) -> User:
    """Authenticate from the access cookie.

    Granting access requires the database to confirm the session is still alive: its refresh
    family must contain a non-revoked, unexpired token. The database is the single source of
    truth for revocation (sign-out, password reset, reuse detection, expiry), so an outage or
    flush of any cache can never resurrect a revoked access token.
    """
    token = request.cookies.get(ACCESS_COOKIE)
    unauthenticated = AppError(401, "UNAUTHENTICATED", "Authentication required")
    if not token:
        raise unauthenticated
    try:
        claims = decode_access_token(settings, token)
    except TokenError:
        raise unauthenticated from None
    if not await session_alive(session, claims.user_id, claims.session_id):
        raise unauthenticated
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise unauthenticated
    request.state.session_id = claims.session_id
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
