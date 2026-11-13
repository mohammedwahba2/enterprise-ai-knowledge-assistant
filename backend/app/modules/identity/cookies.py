from datetime import datetime

from fastapi import Response

from app.core.config import Settings

ACCESS_COOKIE = "ka_at"
REFRESH_COOKIE = "ka_rt"
CSRF_COOKIE = "ka_csrf"
HINT_COOKIE = "ka_session"  # UX hint for the frontend proxy only; never a security boundary
CSRF_HEADER = "x-csrf-token"

ACCESS_PATH = "/api"
REFRESH_PATH = "/api/v1/auth"


def set_session_cookies(
    response: Response,
    settings: Settings,
    *,
    access: str,
    refresh: str,
    csrf: str,
    refresh_expires: datetime,
    now: datetime,
) -> None:
    refresh_age = max(int((refresh_expires - now).total_seconds()), 0)
    common = {"samesite": "lax", "secure": settings.cookie_secure}
    response.set_cookie(
        ACCESS_COOKIE, access, max_age=settings.access_ttl_seconds, path=ACCESS_PATH,
        httponly=True, **common,  # type: ignore[arg-type]
    )  # fmt: skip
    response.set_cookie(
        REFRESH_COOKIE, refresh, max_age=refresh_age, path=REFRESH_PATH,
        httponly=True, **common,  # type: ignore[arg-type]
    )  # fmt: skip
    # Readable by JS on purpose: double-submit CSRF token and a non-sensitive session hint.
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=refresh_age, path="/", httponly=False, **common,  # type: ignore[arg-type]
    )  # fmt: skip
    response.set_cookie(
        HINT_COOKIE, "1", max_age=refresh_age, path="/", httponly=False, **common,  # type: ignore[arg-type]
    )  # fmt: skip


def clear_session_cookies(response: Response, settings: Settings) -> None:
    for name, path, httponly in (
        (ACCESS_COOKIE, ACCESS_PATH, True),
        (REFRESH_COOKIE, REFRESH_PATH, True),
        (CSRF_COOKIE, "/", False),
        (HINT_COOKIE, "/", False),
    ):
        response.delete_cookie(
            name, path=path, httponly=httponly, samesite="lax", secure=settings.cookie_secure
        )
