"""A scripted chat model for tests. Unreachable from any runtime configuration: the shipped app can
only construct `OllamaChat`, so it can never return canned answers.

It records every prompt it receives, which is how the tests prove what the model was (and was
never) shown."""

import asyncio
from collections.abc import AsyncIterator, Callable

from app.infrastructure.llm.base import ChatChunk, ChatMessage, LlmUnavailableError

Reply = str | Callable[[list[ChatMessage]], str]


class FakeChat:
    def __init__(
        self,
        reply: Reply = "",
        *,
        model: str = "fake-chat",
        num_ctx: int = 8192,
        chunk_chars: int = 9,
        delay: float = 0.0,
        unavailable: bool = False,
        prompt_tokens: int = 500,
    ) -> None:
        self.reply = reply
        self.model = model
        self.num_ctx = num_ctx
        self.chunk_chars = chunk_chars
        self.delay = delay
        self.unavailable = unavailable
        self.prompt_tokens = prompt_tokens
        self.calls: list[list[ChatMessage]] = []

    @property
    def prompts(self) -> str:
        """Everything the model has ever been shown, as one string."""
        return "\n".join(m.content for call in self.calls for m in call)

    async def stream(
        self, messages: list[ChatMessage], *, max_tokens: int
    ) -> AsyncIterator[ChatChunk]:
        self.calls.append(list(messages))
        if self.unavailable:
            raise LlmUnavailableError("down")
        text = self.reply(messages) if callable(self.reply) else self.reply
        for start in range(0, len(text), self.chunk_chars):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield ChatChunk(text=text[start : start + self.chunk_chars])
        yield ChatChunk(
            done=True, prompt_tokens=self.prompt_tokens, completion_tokens=len(text) // 4
        )
