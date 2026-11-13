import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, new_id

LOCALES = ("en", "ar")
DIGIT_STYLES = ("western", "arabic-indic")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("locale IN ('en','ar')", name="ck_users_locale"),
        CheckConstraint("digit_style IN ('western','arabic-indic')", name="ck_users_digit_style"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locale: Mapped[str] = mapped_column(String(2), default="en", server_default="en")
    digit_style: Mapped[str] = mapped_column(
        String(16), default="western", server_default="western"
    )
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RefreshToken(Base):
    """One row per issued refresh token. Only the SHA-256 hash of the token is stored."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family", "family_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID]
    family_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None]
    user_agent: Mapped[str | None] = mapped_column(String(256))
    ip: Mapped[str | None] = mapped_column(String(45))


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
