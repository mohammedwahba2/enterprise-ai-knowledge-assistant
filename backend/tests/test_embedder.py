"""The Ollama client and batching helper, against a mock HTTP transport (no model needed)."""

import json

import httpx
import pytest

from app.infrastructure.embeddings.base import (
    EmbedderUnavailableError,
    EmbeddingFailedError,
    embed_in_batches,
)
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from tests.fake_embedder import FakeEmbedder, vectorize


def embedder(handler: httpx.MockTransport, dims: int = 4) -> OllamaEmbedder:
    return OllamaEmbedder("http://ollama:11434/", "bge-m3", dims, timeout=5, transport=handler)


async def test_posts_the_batch_and_returns_vectors_in_order() -> None:
    seen: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"embeddings": [[float(i)] * 4 for i in range(len(body["input"]))]}
        )

    vectors = await embedder(httpx.MockTransport(handle)).embed(["a", "b"])
    assert vectors == [[0.0] * 4, [1.0] * 4]
    assert seen == [{"model": "bge-m3", "input": ["a", "b"], "truncate": True}]


async def test_transient_server_errors_are_retried_then_succeed() -> None:
    calls = {"n": 0}

    def handle(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"embeddings": [[0.0] * 4]})

    assert await embedder(httpx.MockTransport(handle)).embed(["x"]) == [[0.0] * 4]
    assert calls["n"] == 3


async def test_a_server_that_stays_down_is_reported_unavailable() -> None:
    def handle(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(EmbedderUnavailableError):
        await embedder(httpx.MockTransport(handle)).embed(["x"])


@pytest.mark.parametrize(
    ("response", "why"),
    [
        (httpx.Response(404), "missing model"),
        (httpx.Response(400), "bad request"),
        (httpx.Response(200, json={"nope": 1}), "unexpected body"),
        (httpx.Response(200, text="not json"), "not json"),
    ],
)
async def test_unusable_answers_are_permanent_failures_not_retried(
    response: httpx.Response, why: str
) -> None:
    calls = {"n": 0}

    def handle(_r: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return response

    with pytest.raises(EmbeddingFailedError):
        await embedder(httpx.MockTransport(handle)).embed(["x"])
    assert calls["n"] == 1, why


async def test_empty_input_makes_no_request() -> None:
    def handle(_r: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert await embedder(httpx.MockTransport(handle)).embed([]) == []


async def test_batches_are_bounded_and_in_order() -> None:
    fake = FakeEmbedder()
    texts = [f"text number {i}" for i in range(19)]
    vectors = await embed_in_batches(fake, texts, 8)
    assert fake.calls == [8, 8, 3]
    assert vectors == [vectorize(t) for t in texts]


async def test_wrong_dimensions_are_rejected_before_anything_is_stored() -> None:
    with pytest.raises(EmbeddingFailedError, match="dimensions"):
        await embed_in_batches(FakeEmbedder(wrong_dimensions=True), ["a"], 8)
