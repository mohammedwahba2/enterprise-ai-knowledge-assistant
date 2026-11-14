"""Embeddings through a local Ollama server (`POST /api/embed`)."""

import asyncio
from collections.abc import Sequence

import httpx

from app.infrastructure.embeddings.base import EmbedderUnavailableError, EmbeddingFailedError

RETRIES = 2
RETRY_STATUS = {502, 503, 504}


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        dimensions: int,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,  # tests only
    ) -> None:
        self._transport = transport
        self.model = model
        self.dimensions = dimensions
        self._url = base_url.rstrip("/") + "/api/embed"
        self._timeout = timeout

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        body = {"model": self.model, "input": list(texts), "truncate": True}
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, transport=self._transport
                ) as client:
                    response = await client.post(self._url, json=body)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = exc
            else:
                if response.status_code in RETRY_STATUS:
                    last = EmbedderUnavailableError(f"HTTP {response.status_code}")
                elif response.status_code == 404:
                    raise EmbeddingFailedError(f"Model {self.model} is not installed.")
                elif response.status_code >= 400:
                    raise EmbeddingFailedError(
                        f"Embedding request failed ({response.status_code})."
                    )
                else:
                    try:
                        vectors = response.json()["embeddings"]
                    except (ValueError, KeyError, TypeError):
                        raise EmbeddingFailedError("Unexpected embedding response.") from None
                    return [[float(x) for x in vector] for vector in vectors]
            if attempt < RETRIES:
                await asyncio.sleep(0.5 * (attempt + 1))
        raise EmbedderUnavailableError("The embedding service is unavailable.") from last
