"""The Ollama chat client against a mock HTTP transport (no model needed)."""

import json

import httpx
import pytest

from app.infrastructure.llm.base import ChatMessage, LlmFailedError, LlmUnavailableError
from app.infrastructure.llm.ollama import OllamaChat

MESSAGES = [ChatMessage("system", "be brief"), ChatMessage("user", "hello")]


def client(handler: httpx.MockTransport) -> OllamaChat:
    return OllamaChat(
        "http://ollama:11434/", "qwen3:8b", num_ctx=8192, temperature=0.1, transport=handler
    )


def ndjson(*objects: dict[str, object]) -> bytes:
    return ("\n".join(json.dumps(o) for o in objects) + "\n").encode()


async def collect(chat: OllamaChat) -> list:  # type: ignore[type-arg]
    return [c async for c in chat.stream(MESSAGES, max_tokens=300)]


async def test_streams_deltas_then_the_final_token_counts() -> None:
    seen: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        seen.append(json.loads(request.content))
        body = ndjson(
            {"message": {"content": "Hel"}, "done": False},
            {"message": {"content": "lo"}, "done": False},
            {"message": {"content": ""}, "done": True, "prompt_eval_count": 321, "eval_count": 7},
        )
        return httpx.Response(200, content=body)

    chunks = await collect(client(httpx.MockTransport(handle)))
    assert "".join(c.text for c in chunks) == "Hello"
    assert chunks[-1].done and (chunks[-1].prompt_tokens, chunks[-1].completion_tokens) == (321, 7)
    body = seen[0]
    assert body["model"] == "qwen3:8b" and body["stream"] is True
    assert body["think"] is False  # no hidden reasoning time before the first token
    assert body["options"] == {
        "num_ctx": 8192,
        "temperature": 0.1,
        "num_predict": 300,
    }  # explicit context
    assert body["keep_alive"] == "30m"
    assert body["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"},
    ]


async def test_an_unknown_model_is_a_setup_error_not_an_outage() -> None:
    with pytest.raises(LlmFailedError, match="not installed"):
        await collect(client(httpx.MockTransport(lambda _r: httpx.Response(404))))


@pytest.mark.parametrize("status", [502, 503, 504])
async def test_gateway_errors_are_reported_as_unavailable(status: int) -> None:
    with pytest.raises(LlmUnavailableError):
        await collect(client(httpx.MockTransport(lambda _r: httpx.Response(status))))


async def test_a_refused_connection_is_reported_as_unavailable() -> None:
    def handle(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LlmUnavailableError):
        await collect(client(httpx.MockTransport(handle)))


async def test_an_error_object_in_the_stream_and_garbage_are_failures() -> None:
    err = httpx.Response(200, content=ndjson({"error": "model failed to load"}))
    with pytest.raises(LlmFailedError):
        await collect(client(httpx.MockTransport(lambda _r: err)))
    with pytest.raises(LlmFailedError):
        await collect(
            client(httpx.MockTransport(lambda _r: httpx.Response(200, content=b"not json\n")))
        )


async def test_a_stream_that_ends_without_a_final_message_is_a_failure() -> None:
    body = ndjson({"message": {"content": "partial"}, "done": False})
    with pytest.raises(LlmFailedError, match="without a final"):
        await collect(client(httpx.MockTransport(lambda _r: httpx.Response(200, content=body))))
