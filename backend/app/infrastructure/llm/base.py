"""The language-model seam. One production implementation (Ollama); doubles live only in tests."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


class LlmError(Exception):
    """Base class for generation failures."""


class LlmUnavailableError(LlmError):
    """The model server could not be reached, timed out, or is overloaded: transient."""


class LlmFailedError(LlmError):
    """The model server answered with an error (unknown model, bad request): a setup problem."""


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatChunk:
    text: str = ""
    done: bool = False
    # present on the final chunk, as reported by the server
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatModel(Protocol):
    model: str
    num_ctx: int

    def stream(self, messages: list[ChatMessage], *, max_tokens: int) -> AsyncIterator[ChatChunk]:
        """Yield text deltas, then a final chunk with `done=True` and the token counts."""
        ...
