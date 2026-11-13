import io
import json

from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.logging import configure_logging
from app.main import create_app
from tests.conftest import fake_check


async def test_generates_request_id(plain_client: AsyncClient) -> None:
    r = await plain_client.get("/api/health/live")
    assert len(r.headers["x-request-id"]) == 32


async def test_honours_valid_incoming_request_id(plain_client: AsyncClient) -> None:
    r = await plain_client.get("/api/health/live", headers={"x-request-id": "abc-12345678"})
    assert r.headers["x-request-id"] == "abc-12345678"


async def test_rejects_unsafe_incoming_request_id(plain_client: AsyncClient) -> None:
    r = await plain_client.get("/api/health/live", headers={"x-request-id": "bad id\nwith newline"})
    assert r.headers["x-request-id"] != "bad id\nwith newline"
    assert len(r.headers["x-request-id"]) == 32


async def test_request_log_is_json_with_request_id(plain_settings: Settings) -> None:
    app = create_app(plain_settings, checks=[fake_check("postgres")])
    stream = io.StringIO()
    configure_logging("INFO", json_logs=True, stream=stream)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health/live", headers={"x-request-id": "req-0000001"})
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    entry = next(e for e in lines if e["event"] == "request")
    assert entry["request_id"] == "req-0000001"
    assert entry["status"] == 200
    assert entry["path"] == "/api/health/live"
    assert entry["level"] == "info"
    assert "duration_ms" in entry
    assert r.status_code == 200
