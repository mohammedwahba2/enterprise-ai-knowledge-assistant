"""identity: users, refresh_tokens, password_resets

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("locale", sa.String(2), nullable=False, server_default="en"),
        sa.Column("digit_style", sa.String(16), nullable=False, server_default="western"),
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("locale IN ('en','ar')", name="ck_users_locale"),
        sa.CheckConstraint(
            "digit_style IN ('western','arabic-indic')", name="ck_users_digit_style"
        ),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("family_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by", sa.Uuid()),
        sa.Column("user_agent", sa.String(256)),
        sa.Column("ip", sa.String(45)),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family", "refresh_tokens", ["family_id"])
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_resets")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
