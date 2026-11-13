"""Object storage against a real, authenticated SeaweedFS S3 gateway (no mocks)."""

import io
import os
import uuid

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.storage.s3 import ObjectMissingError, S3ObjectStore, StorageUnavailableError
from tests.conftest import S3_BUCKET, S3_KEY, S3_SECRET


@pytest.fixture
def s3_settings(s3_endpoint: str) -> Settings:
    return Settings(
        app_env="test",
        s3_endpoint=s3_endpoint,
        s3_access_key=SecretStr(S3_KEY),
        s3_secret_key=SecretStr(S3_SECRET),
        s3_bucket=S3_BUCKET,  # one shared bucket: every bucket costs the store its own volumes
    )


async def collect(store: S3ObjectStore, key: str) -> bytes:
    return b"".join([c async for c in await store.open_stream(key)])


async def test_authenticated_round_trip(s3_settings: Settings) -> None:
    store = S3ObjectStore(s3_settings)
    key = f"org/{uuid.uuid4()}/doc/{uuid.uuid4()}"
    data = os.urandom(300_000)
    await store.put(key, io.BytesIO(data), "application/pdf")
    assert await store.exists(key)
    assert await collect(store, key) == data
    await store.delete(key)
    assert not await store.exists(key)


async def test_large_object_uses_multipart_and_streams_back_intact(s3_settings: Settings) -> None:
    store = S3ObjectStore(s3_settings)
    data = os.urandom(12 * 1024 * 1024)
    key = f"big/{uuid.uuid4()}"
    await store.put(key, io.BytesIO(data), "application/octet-stream")
    assert await collect(store, key) == data


async def test_wrong_credentials_are_refused(s3_settings: Settings) -> None:
    """Proves authentication is actually enforced by the gateway, not just configured."""
    await S3ObjectStore(s3_settings).ensure_bucket()
    bad = s3_settings.model_copy(update={"s3_secret_key": SecretStr("not-the-secret")})
    with pytest.raises(StorageUnavailableError):
        await S3ObjectStore(bad).check()
    with pytest.raises(StorageUnavailableError):
        await S3ObjectStore(bad).put("k", io.BytesIO(b"x"), "text/plain")


async def test_unreachable_endpoint_is_reported_as_unavailable(s3_settings: Settings) -> None:
    dead = s3_settings.model_copy(update={"s3_endpoint": "http://127.0.0.1:1"})
    with pytest.raises(StorageUnavailableError):
        await S3ObjectStore(dead).check()


async def test_missing_object_and_missing_bucket(s3_settings: Settings) -> None:
    ghost = S3ObjectStore(
        s3_settings.model_copy(update={"s3_bucket": f"ghost-{uuid.uuid4().hex[:8]}"})
    )
    with pytest.raises((ObjectMissingError, StorageUnavailableError)):
        await ghost.check()  # no such bucket: the readiness check must NOT pass
    store = S3ObjectStore(s3_settings)
    await store.ensure_bucket()
    await store.check()
    await store.ensure_bucket()  # idempotent
    with pytest.raises(ObjectMissingError):
        await store.open_stream(f"nope-{uuid.uuid4()}")


async def test_delete_prefix_and_list_keys_respect_boundaries(s3_settings: Settings) -> None:
    store = S3ObjectStore(s3_settings)
    root = f"scope-{uuid.uuid4().hex[:8]}"
    a, ab, b = f"{root}/org/a/", f"{root}/org/ab/", f"{root}/org/b/"
    for k in (f"{a}doc/1", f"{a}doc/2", f"{a}doc/3", f"{ab}doc/1", f"{b}doc/1"):
        await store.put(k, io.BytesIO(b"x"), "text/plain")
    assert sorted(await store.list_keys(a)) == [f"{a}doc/1", f"{a}doc/2", f"{a}doc/3"]
    assert await store.delete_prefix(a) == 3
    assert await store.list_keys(a) == []
    assert sorted(await store.list_keys(f"{root}/org/")) == [
        f"{ab}doc/1",
        f"{b}doc/1",
    ]  # neighbours untouched
