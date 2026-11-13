from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import fake_check


async def test_live_does_not_depend_on_anything(plain_settings: Settings) -> None:
    app = create_app(plain_settings, checks=[fake_check("postgres", ok=False)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ready_ok(plain_client: AsyncClient) -> None:
    r = await plain_client.get("/api/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert {c["name"] for c in body["checks"]} == {"postgres", "redis"}


async def test_ready_reports_failing_dependency(plain_settings: Settings) -> None:
    app = create_app(
        plain_settings,
        checks=[fake_check("postgres"), fake_check("redis", ok=False, detail="ConnectionError")],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    failing = [c for c in body["checks"] if not c["ok"]]
    assert [c["name"] for c in failing] == ["redis"]


async def test_ready_with_unreachable_real_dependencies_returns_503_without_leaking_urls() -> None:
    plain_settings = Settings(
        app_env="test",
        database_url="postgresql://u:supersecret@127.0.0.1:1/db",
        redis_url="redis://:supersecret@127.0.0.1:1/0",
        s3_endpoint="http://127.0.0.1:1",
        readiness_timeout_seconds=0.5,
    )
    app = create_app(plain_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health/ready")
    assert r.status_code == 503
    assert "supersecret" not in r.text
    assert all(not c["ok"] for c in r.json()["checks"])
