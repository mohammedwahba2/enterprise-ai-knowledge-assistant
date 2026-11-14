"""Chat completions through a local Ollama server (`POST /api/chat`, streamed as NDJSON)."""

import json
from collections.abc import AsyncIterator

import httpx

from app.infrastructure.llm.base import (
    ChatChunk,
    ChatMessage,
    LlmFailedError,
    LlmUnavailableError,
)


class OllamaChat:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        num_ctx: int,
        temperature: float = 0.1,
        timeout: float = 120.0,
        keep_alive: str | None = "30m",
        transport: httpx.AsyncBaseTransport | None = None,  # tests only
    ) -> None:
        self.model = model
        self.num_ctx = num_ctx
        self._url = base_url.rstrip("/") + "/api/chat"
        self._temperature = temperature
        self._timeout = timeout
        self._keep_alive = keep_alive
        self._transport = transport

    async def stream(
        self, messages: list[ChatMessage], *, max_tokens: int
    ) -> AsyncIterator[ChatChunk]:
        body: dict[str, object] = {
            "model": self.model,
            "stream": True,
            # Ollama's default context is small and silently truncates the prompt: always explicit.
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self._temperature,
                "num_predict": max_tokens,
            },
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            # Reasoning models (Qwen3) would otherwise spend the first seconds "thinking" aloud.
            "think": False,
        }
        if self._keep_alive:
            body["keep_alive"] = self._keep_alive
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
                client.stream("POST", self._url, json=body) as response,
            ):
                if response.status_code == 404:
                    raise LlmFailedError(f"Model {self.model} is not installed.")
                if response.status_code in (502, 503, 504):
                    raise LlmUnavailableError(f"HTTP {response.status_code}")
                if response.status_code >= 400:
                    raise LlmFailedError(f"Chat request failed ({response.status_code}).")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except ValueError:
                        raise LlmFailedError("Unexpected chat response.") from None
                    if "error" in data:
                        raise LlmFailedError("The model server reported an error.")
                    text = str((data.get("message") or {}).get("content") or "")
                    if data.get("done"):
                        yield ChatChunk(
                            text=text,
                            done=True,
                            prompt_tokens=data.get("prompt_eval_count"),
                            completion_tokens=data.get("eval_count"),
                        )
                        return
                    if text:
                        yield ChatChunk(text=text)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise LlmUnavailableError("The language model is unavailable.") from exc
        raise LlmFailedError("The model stream ended without a final message.")
