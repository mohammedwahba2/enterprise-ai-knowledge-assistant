"""A deterministic embedder for tests. It is unreachable from any runtime configuration: the shipped
app can only construct `OllamaEmbedder`.

Vectors are hashed bags of normalized words, so texts sharing words are close in cosine distance
(enough for retrieval plumbing and metrics tests) while meaning, synonyms and cross-language
similarity are deliberately NOT modelled.
"""

import hashlib
import math
import re
from collections.abc import Sequence

from app.infrastructure.embeddings.base import EmbedderUnavailableError
from app.modules.processing.arabic import search_normalize

DIMENSIONS = 1024
_WORD = re.compile(r"\w+", re.UNICODE)


def vectorize(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for word in _WORD.findall(search_normalize(text).lower()):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "big") % dimensions
        vector[slot] += 1.0 if digest[4] % 2 else -1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class FakeEmbedder:
    def __init__(
        self,
        model: str = "fake-hash-1024",
        dimensions: int = DIMENSIONS,
        *,
        unavailable: bool = False,
        wrong_dimensions: bool = False,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.unavailable = unavailable
        self.wrong_dimensions = wrong_dimensions
        self.calls: list[int] = []  # batch sizes, to assert batching
        self.texts: list[str] = []  # everything it was asked to embed

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(len(texts))
        self.texts.extend(texts)
        if self.unavailable:
            raise EmbedderUnavailableError("down")
        dims = self.dimensions - 1 if self.wrong_dimensions else self.dimensions
        return [vectorize(t, dims) for t in texts]
