import io
import json

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.logging import configure_logging
from app.main import create_app


def _app(plain_settings: Settings) -> FastAPI:
    app = create_app(plain_settings, checks=[])

    @app.get("/api/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/api/needs-int")
    async def needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    return app


async def test_unhandled_error_is_problem_json_without_internals(plain_settings: Settings) -> None:
    stream = io.StringIO()
    app = _app(plain_settings)
    configure_logging("INFO", json_logs=True, stream=stream)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as c:
        r = await c.get("/api/boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["request_id"] == r.headers["x-request-id"]
    assert "secret internal detail" not in r.text
    logged = [json.loads(x) for x in stream.getvalue().splitlines() if x.strip()]
    err = next(e for e in logged if e["event"] == "unhandled_exception")
    assert "secret internal detail" in err["exception"]


async def test_unknown_route_has_stable_code(plain_client: AsyncClient) -> None:
    r = await plain_client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


async def test_validation_error_shape(plain_settings: Settings) -> None:
    app = _app(plain_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/needs-int", params={"n": "x"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["errors"][0]["loc"] == ["query", "n"]
