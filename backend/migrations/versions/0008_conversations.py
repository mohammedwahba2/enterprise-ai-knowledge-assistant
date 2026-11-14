"""conversations, messages, citations and retrieval logs

Revision ID: 0008
Revises: 0007

Conversations are PRIVATE to the user who owns them: the row-level security policy requires the
caller to be that user inside that organization, so even an administrator cannot read someone
else's questions. Every table carries `organization_id` and `user_id` (denormalized) so the policy
is a plain column comparison. Citations snapshot the passage that was cited (history survives
re-indexing); whether the user may still SEE it is decided on every read, not stored.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

APP_ROLE = "app_rw"
TABLES = ("conversations", "messages", "message_citations", "retrieval_logs")


def _fk(column: str, target: str, ondelete: str = "CASCADE", nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(column, sa.Uuid(), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    owner = (_fk("organization_id", "organizations.id"), _fk("user_id", "users.id"))
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *owner,
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_conversations_owner", "conversations", ["organization_id", "user_id", "updated_at"]
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("conversation_id", "conversations.id"),
        _fk("organization_id", "organizations.id"),
        _fk("user_id", "users.id"),
        sa.Column("role", sa.String(9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_code", sa.String(40)),
        sa.Column("refusal_reason", sa.String(40)),
        sa.Column("language", sa.String(2)),
        sa.Column("model", sa.Text()),
        sa.Column("partially_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retrieval_params", sa.JSON()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("first_token_ms", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_messages_role"),
        sa.CheckConstraint(
            "status IN ('streaming','complete','refused','error')", name="ck_messages_status"
        ),
    )
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "message_citations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("message_id", "messages.id"),
        _fk("organization_id", "organizations.id"),
        _fk("user_id", "users.id"),
        # the cited passage's identity; no foreign keys on purpose: the chunk may be re-indexed or
        # purged later, and the snapshot below must outlive it
        sa.Column("chunk_id", sa.Uuid()),
        sa.Column("document_id", sa.Uuid()),
        sa.Column("collection_id", sa.Uuid()),
        sa.Column("document_title", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("marker", sa.Integer(), nullable=False),
        sa.Column("support_score", sa.Float(), nullable=False),
    )
    op.create_index("ix_message_citations_message", "message_citations", ["message_id", "marker"])

    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _fk("message_id", "messages.id"),
        _fk("organization_id", "organizations.id"),
        _fk("user_id", "users.id"),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("vector_score", sa.Float()),
        sa.Column("fts_score", sa.Float()),
        sa.Column("fused_score", sa.Float(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_retrieval_logs_message", "retrieval_logs", ["message_id", "rank"])

    mine = (
        "(organization_id = app_current_org() AND user_id = app_current_user() "
        "AND app_is_member(organization_id, app_current_user()))"
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {APP_ROLE} "
            f"USING {mine} WITH CHECK {mine}"
        )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON conversations, messages TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON message_citations, retrieval_logs TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
