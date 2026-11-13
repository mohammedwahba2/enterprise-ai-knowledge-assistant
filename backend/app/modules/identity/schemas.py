import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Locale = Literal["en", "ar"]
DigitStyle = Literal["western", "arabic-indic"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_email(value: str) -> str:
    return value.strip().lower()


class SignUpRequest(_Strict):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=1024)
    display_name: str = Field(min_length=1, max_length=80)
    locale: Locale = "en"

    @field_validator("email", mode="after")
    @classmethod
    def _lower(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("display_name", mode="after")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("display name is empty")
        return v


class SignInRequest(_Strict):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=1024)

    @field_validator("email", mode="after")
    @classmethod
    def _lower(cls, v: str) -> str:
        return _clean_email(v)


class ForgotPasswordRequest(_Strict):
    email: EmailStr = Field(max_length=254)
    locale: Locale | None = None

    @field_validator("email", mode="after")
    @classmethod
    def _lower(cls, v: str) -> str:
        return _clean_email(v)


class ResetPasswordRequest(_Strict):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(max_length=1024)


class UpdateMeRequest(_Strict):
    locale: Locale | None = None
    digit_style: DigitStyle | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    locale: Locale
    digit_style: DigitStyle
