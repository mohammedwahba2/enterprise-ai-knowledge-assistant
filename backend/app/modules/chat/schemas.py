import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CreateConversationRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class AskRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    collection_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    # normally inferred from the question; the UI may override it
    language: Literal["ar", "en"] | None = None

    @field_validator("content")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value.strip()


class CitationOut(BaseModel):
    marker: int
    # False when the reader no longer has access to the cited document (or it was deleted): then
    # everything that could reveal it is withheld, only the marker remains
    available: bool
    document_id: uuid.UUID | None
    document_title: str | None
    page_start: int | None
    page_end: int | None
    quote: str | None
    support_score: float


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    status: str
    refusal_reason: str | None
    error_code: str | None
    language: str | None
    partially_supported: bool
    created_at: datetime
    citations: list[CitationOut]


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
