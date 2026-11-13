import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Visibility = Literal["org", "restricted"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("must not be empty")
    return value


class CreateCollectionRequest(_Strict):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    visibility: Visibility = "org"
    _n = field_validator("name", mode="after")(_clean)


class UpdateCollectionRequest(_Strict):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    visibility: Visibility | None = None

    @field_validator("name", mode="after")
    @classmethod
    def _n(cls, v: str | None) -> str | None:
        return None if v is None else _clean(v)


class CollectionOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    visibility: Visibility
    document_count: int
    member_count: int | None  # admins and owners only
    can_upload: bool


class SetMembersRequest(_Strict):
    user_ids: list[uuid.UUID] = Field(max_length=500)


class CollectionMemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    collection_name: str
    title: str
    original_filename: str
    mime_type: str
    size_bytes: int
    status: str
    error_code: str | None
    page_count: int | None
    uploaded_by_name: str | None
    created_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    next_cursor: str | None


class UploadResult(BaseModel):
    filename: str
    outcome: Literal["created", "duplicate", "rejected"]
    document: DocumentOut | None = None
    error_code: str | None = None
