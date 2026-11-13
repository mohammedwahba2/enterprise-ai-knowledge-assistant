"""RFC 7807 problem+json responses with stable machine-readable codes."""

from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_log = structlog.get_logger("errors")
PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    """Domain error rendered as problem+json with a stable machine-readable code."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        *,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.title = title
        self.headers = headers or {}
        self.extra = extra


def problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
        **extra,
    }
    headers = dict(headers or {})
    if body["request_id"]:
        # Errors raised past the request-context middleware (500s) need the header re-added.
        headers["x-request-id"] = body["request_id"]
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem(request, exc.status, exc.code, exc.title, exc.headers, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == HTTPStatus.NOT_FOUND else f"HTTP_{exc.status_code}"
        return problem(request, exc.status_code, code, HTTPStatus(exc.status_code).phrase)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return problem(request, 422, "VALIDATION_ERROR", "Validation failed", errors=errors)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        _log.error("unhandled_exception", exc_info=exc)
        return problem(request, 500, "INTERNAL_ERROR", "Internal server error")
