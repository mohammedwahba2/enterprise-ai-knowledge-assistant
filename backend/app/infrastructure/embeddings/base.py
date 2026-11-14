"""The embedder seam. One production implementation (Ollama); test doubles live only in tests."""

from collections.abc import Sequence
from typing import Protocol


class EmbedderError(Exception):
    """Base class for embedding failures."""


class EmbedderUnavailableError(EmbedderError):
    """The embedding service could not be reached or timed out: transient, worth retrying."""


class EmbeddingFailedError(EmbedderError):
    """The service answered but the answer is unusable (unknown model, wrong dimensions): a
    configuration problem that retrying will not fix."""


class Embedder(Protocol):
    model: str
    dimensions: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector of `dimensions` floats per text, in order."""
        ...


async def embed_in_batches(
    embedder: Embedder, texts: Sequence[str], batch_size: int
) -> list[list[float]]:
    """Embed `texts` sequentially in bounded batches (memory- and timeout-friendly)."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        result = await embedder.embed(batch)
        if len(result) != len(batch):
            raise EmbeddingFailedError(f"Expected {len(batch)} vectors, received {len(result)}.")
        for vector in result:
            if len(vector) != embedder.dimensions:
                raise EmbeddingFailedError(
                    f"Model {embedder.model} returned {len(vector)} dimensions, "
                    f"expected {embedder.dimensions}."
                )
        vectors.extend(result)
    return vectors
