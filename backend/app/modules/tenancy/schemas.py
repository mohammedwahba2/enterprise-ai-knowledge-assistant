import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

RoleName = Literal["owner", "admin", "editor", "member", "viewer"]
InviteRoleName = Literal["admin", "editor", "member", "viewer"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("name is empty")
    return value


class CreateOrgRequest(_Strict):
    name: str = Field(min_length=1, max_length=100)
    _clean = field_validator("name", mode="after")(_clean_name)


class UpdateOrgRequest(_Strict):
    name: str = Field(min_length=1, max_length=100)
    _clean = field_validator("name", mode="after")(_clean_name)


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: RoleName


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    email: str | None  # visible to admins and owners only
    role: RoleName
    joined_at: datetime


class UpdateMemberRequest(_Strict):
    role: RoleName


class CreateInvitationRequest(_Strict):
    email: EmailStr = Field(max_length=254)
    role: InviteRoleName
    locale: Literal["en", "ar"] = "en"

    @field_validator("email", mode="after")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: InviteRoleName
    expires_at: datetime
    created_at: datetime


class AcceptInvitationRequest(_Strict):
    token: str = Field(min_length=20, max_length=200)
