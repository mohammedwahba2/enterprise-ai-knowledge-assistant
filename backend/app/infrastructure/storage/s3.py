"""S3-compatible object storage (SeaweedFS in Compose). Sync boto3 calls run in worker threads."""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import IO, Any, Protocol

import boto3
import structlog
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings

_log = structlog.get_logger("storage")
CHUNK = 64 * 1024
_TRANSIENT = {"InternalError", "ServiceUnavailable", "SlowDown", "RequestTimeout"}


class StorageUnavailableError(Exception):
    """The object store could not be reached or rejected our credentials."""


class ObjectMissingError(Exception):
    """The requested object does not exist."""


class ObjectStore(Protocol):
    async def ensure_bucket(self) -> None: ...
    async def check(self) -> None: ...
    async def put(self, key: str, fileobj: IO[bytes], content_type: str) -> None: ...
    async def open_stream(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def delete_prefix(self, prefix: str) -> int: ...
    async def exists(self, key: str) -> bool: ...
    async def list_keys(self, prefix: str) -> list[str]: ...


class _KeepOpen:
    """boto3 closes file objects it uploads; retries must be able to read the same one again."""

    def __init__(self, inner: IO[bytes]) -> None:
        self._inner = inner

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._inner.seek(offset, whence)

    def tell(self) -> int:
        return self._inner.tell()

    def close(self) -> None:  # intentionally a no-op
        return None


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
            region_name=settings.s3_region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 2, "mode": "standard"},
                connect_timeout=3,
                read_timeout=60,
            ),
        )
        self._bucket_ready = False

    async def _call(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                raise ObjectMissingError(code) from exc
            _log.error("storage_error", code=code)
            raise StorageUnavailableError(code) from exc
        except (BotoCoreError, OSError) as exc:
            _log.error("storage_unreachable", error=type(exc).__name__)
            raise StorageUnavailableError(type(exc).__name__) from exc

    async def check(self) -> None:
        await self._call(self._client.head_bucket, Bucket=self._bucket)

    async def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            await self._call(self._client.head_bucket, Bucket=self._bucket)
        except (StorageUnavailableError, ObjectMissingError):
            await self._call(self._client.create_bucket, Bucket=self._bucket)
        self._bucket_ready = True

    async def put(self, key: str, fileobj: IO[bytes], content_type: str) -> None:
        await self.ensure_bucket()
        # A freshly created bucket can answer InternalError while the store allocates its first
        # volume; retry those briefly. Authentication and other errors are never retried.
        for attempt in range(1, 5):
            fileobj.seek(0)
            try:
                await self._call(
                    self._client.upload_fileobj, _KeepOpen(fileobj), self._bucket, key,
                    ExtraArgs={"ContentType": content_type},
                )  # fmt: skip
                return
            except StorageUnavailableError as exc:
                if attempt == 4 or str(exc) not in _TRANSIENT:
                    raise
                await asyncio.sleep(0.5 * attempt)

    async def _read(self, body: Any) -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = await asyncio.to_thread(body.read, CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(body.close)

    async def open_stream(self, key: str) -> AsyncIterator[bytes]:
        """Fail fast (before response headers are sent) if the object is missing/unreachable."""
        await self._call(self._client.head_object, Bucket=self._bucket, Key=key)
        response = await self._call(self._client.get_object, Bucket=self._bucket, Key=key)
        return self._read(response["Body"])

    async def delete(self, key: str) -> None:
        await self._call(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            await self._call(self._client.head_object, Bucket=self._bucket, Key=key)
        except ObjectMissingError:
            return False
        return True

    async def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self._bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = await self._call(self._client.list_objects_v2, **kwargs)
            keys += [o["Key"] for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return keys
            token = page.get("NextContinuationToken")

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under `prefix` (used when a workspace is deleted)."""
        deleted = 0
        token: str | None = None
        while True:
            kwargs = {
                "Bucket": self._bucket,
                "Prefix": prefix,
                **({"ContinuationToken": token} if token else {}),
            }
            page = await self._call(self._client.list_objects_v2, **kwargs)
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                await self._call(
                    self._client.delete_objects, Bucket=self._bucket, Delete={"Objects": keys}
                )
                deleted += len(keys)
            if not page.get("IsTruncated"):
                return deleted
            token = page.get("NextContinuationToken")
