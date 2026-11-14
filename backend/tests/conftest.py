import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer
from testcontainers.core.container import DockerContainer

from app.core.config import Settings
from app.core.readiness import Check, CheckResult
from app.db.base import to_async_url
from app.main import create_app
from tests.fake_embedder import FakeEmbedder

if TYPE_CHECKING:
    from tests.tenancy_helpers import World

APP_DB_PASSWORD = "app-role-test-password"
WORKER_DB_PASSWORD = "worker-role-test-password"
S3_KEY, S3_SECRET, S3_BUCKET = "test-access-key", "test-secret-key-0123456789", "test-bucket"
SEAWEED_IMAGE = "chrislusf/seaweedfs:latest"
PG_IMAGE = "pgvector/pgvector:pg16"
REDIS_IMAGE = "redis:7-alpine"


def fake_check(name: str, ok: bool = True, detail: str | None = None) -> Check:
    async def run() -> CheckResult:
        return CheckResult(name, ok, 0.1, detail)

    return run


# ---------- real infrastructure (testcontainers), one per test session ----------


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with PostgresContainer(PG_IMAGE, username="test", password="test", dbname="test") as pg:
        url = pg.get_connection_url().replace("+psycopg2", "")
        os.environ["DATABASE_URL"] = url
        os.environ["APP_DB_PASSWORD"] = APP_DB_PASSWORD
        os.environ["WORKER_DB_PASSWORD"] = WORKER_DB_PASSWORD
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")  # runs as the owner/superuser and creates the app role
        yield url


@pytest.fixture(scope="session")
def app_db_url(pg_url: str) -> str:
    """The API connects as `app_rw` (non-superuser, NOBYPASSRLS), never as the owner."""
    return pg_url.replace("//test:test@", f"//app_rw:{APP_DB_PASSWORD}@")


@pytest.fixture(scope="session")
def worker_db_url(pg_url: str) -> str:
    """The background worker connects as `worker_rw`, a separate least-privilege role."""
    return pg_url.replace("//test:test@", f"//worker_rw:{WORKER_DB_PASSWORD}@")


@pytest.fixture(scope="session")
def s3_endpoint() -> Iterator[str]:
    """A real SeaweedFS S3 gateway with authentication enabled, like the Compose service."""
    import time

    import boto3
    from botocore.client import Config

    script = (
        'printf \'{"identities":[{"name":"app","credentials":[{"accessKey":"%s",'
        '"secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}\' '
        f"{S3_KEY} {S3_SECRET} > /tmp/s3.json && exec weed server -dir=/data -volume.max=50 -ip.bind=0.0.0.0 -s3 -s3.config=/tmp/s3.json"
    )
    container = (
        DockerContainer(SEAWEED_IMAGE)
        .with_kwargs(entrypoint=["sh", "-c"])
        .with_command([script])
        .with_exposed_ports(8333)
    )
    with container:
        endpoint = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8333)}"
        client = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=S3_KEY, aws_secret_access_key=S3_SECRET,
            region_name="us-east-1", config=Config(connect_timeout=2, read_timeout=5, retries={"max_attempts": 1}),
        )  # fmt: skip
        deadline = time.time() + 90
        while True:
            try:
                client.list_buckets()
                break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(1)
        yield endpoint


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer(REDIS_IMAGE) as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


# ---------- app wiring ----------


@dataclass
class Outbox:
    """Test-only email sink. The shipped app can only send through SMTP."""

    messages: list[dict[str, str]] = field(default_factory=list)

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "body": body})

    def last_token(self) -> str:
        body = self.messages[-1]["body"]
        return body.split("#token=", 1)[1].split()[0]


@dataclass
class Enqueued:
    """Records processing requests instead of talking to a broker (tests run the pipeline directly)."""

    calls: list[tuple[str, str]] = field(default_factory=list)

    async def __call__(self, document_id: object, org_id: object) -> None:
        self.calls.append((str(document_id), str(org_id)))


@pytest.fixture
def enqueued() -> Enqueued:
    return Enqueued()


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def settings(app_db_url: str, redis_url: str, s3_endpoint: str) -> Settings:
    return Settings(
        app_env="test",
        log_json=True,
        database_url=app_db_url,
        s3_endpoint=s3_endpoint,
        s3_access_key=S3_KEY,  # type: ignore[arg-type]
        s3_secret_key=S3_SECRET,  # type: ignore[arg-type]
        s3_bucket=S3_BUCKET,
        redis_url=redis_url,
        app_origin="http://localhost:8080",
        cookie_secure=False,
        argon2_memory_kib=1024,  # cheap hashing in tests; production defaults are tested separately
        argon2_time_cost=1,
        signin_account_limit=5,
        refresh_grace_seconds=10,
    )


@pytest.fixture(autouse=True)
async def _clean_state(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Fresh tables and Redis for every test that touches infrastructure."""
    if "settings" not in request.fixturenames:
        yield
        return
    s: Settings = request.getfixturevalue("settings")
    owner_url: str = request.getfixturevalue("pg_url")  # TRUNCATE needs the owner
    engine = create_async_engine(to_async_url(owner_url))
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, refresh_tokens, password_resets, organizations, memberships, "
                "invitations, collections, collection_members, documents, document_pages, chunks, "
                "ingestion_jobs CASCADE"
            )
        )
    await engine.dispose()
    r = Redis.from_url(s.redis_url)
    await r.flushdb()
    await r.aclose()
    yield


@asynccontextmanager
async def make_client(
    settings: Settings,
    *,
    email_sender: object,
    ip: str = "203.0.113.7",
    base_url: str = "http://localhost:8080",
    enqueue: object | None = None,
    embedder: object | None = None,
) -> AsyncIterator[AsyncClient]:
    """A browser-like client (cookie jar, same-origin Origin header) with clean teardown."""
    app = create_app(
        settings, checks=[], email_sender=email_sender,  # type: ignore[arg-type]
        enqueue=enqueue or Enqueued(),  # type: ignore[arg-type]
        embedder=embedder or FakeEmbedder(),  # type: ignore[arg-type]
    )  # fmt: skip
    transport = ASGITransport(app=app, client=(ip, 5000))
    try:
        async with AsyncClient(
            transport=transport, base_url=base_url, headers={"origin": "http://localhost:8080"}
        ) as c:
            yield c
    finally:
        await app.state.engine.dispose()
        await app.state.redis.aclose()


@pytest.fixture
async def client(settings: Settings, outbox: Outbox) -> AsyncIterator[AsyncClient]:
    async with make_client(settings, email_sender=outbox) as c:
        yield c


# ---------- infrastructure-free fixtures for unit-style tests ----------


@pytest.fixture
def plain_settings() -> Settings:
    return Settings(app_env="test", log_json=True)


@pytest.fixture
async def plain_client(plain_settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(plain_settings, checks=[fake_check("postgres"), fake_check("redis")])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        await app.state.engine.dispose()
        await app.state.redis.aclose()


@pytest.fixture
async def world(
    settings: Settings, outbox: Outbox, worker_db_url: str, enqueued: Enqueued
) -> AsyncIterator["World"]:
    from tests.tenancy_helpers import World

    w = World(settings, outbox, worker_db_url, enqueued)
    try:
        yield w
    finally:
        await w.aclose()
