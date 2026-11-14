"""document processing: pages, chunks, ingestion jobs, extraction metadata, worker role

Revision ID: 0004
Revises: 0003
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

APP_ROLE = "app_rw"
WORKER_ROLE = "worker_rw"
NEW_TABLES = ("document_pages", "chunks", "ingestion_jobs")


def _ensure_worker_role() -> None:
    """The background worker gets its own least-privilege role (it has no user to scope RLS by)."""
    password = os.environ.get("WORKER_DB_PASSWORD")
    if not password:
        raise RuntimeError("WORKER_DB_PASSWORD must be set to create the worker database role")
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": WORKER_ROLE}
    ).scalar()
    verb = "ALTER" if exists else "CREATE"
    stmt = bind.execute(
        sa.text(
            f"SELECT format('{verb} ROLE {WORKER_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOBYPASSRLS PASSWORD %L', cast(:pw as text))"
        ),
        {"pw": password},
    ).scalar_one()
    op.execute(stmt)


def upgrade() -> None:
    _ensure_worker_role()

    op.add_column("documents", sa.Column("language", sa.String(8)))
    op.add_column("documents", sa.Column("pagination", sa.String(8)))
    op.add_column("documents", sa.Column("viewer_key", sa.String(255)))
    op.add_column("documents", sa.Column("page_summary", sa.dialects.postgresql.JSONB()))
    op.add_column("documents", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_documents_language", "documents", "language IS NULL OR language IN ('en','ar','mixed')"
    )
    op.create_check_constraint(
        "ck_documents_pagination",
        "documents",
        "pagination IS NULL OR pagination IN ('native','virtual')",
    )

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extraction_state", sa.String(12), nullable=False),
        sa.Column("image_area_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_doc_page"),
        sa.CheckConstraint(
            "extraction_state IN ('text','image_only','garbled')", name="ck_document_pages_state"
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_document_pages_number"),
    )
    op.create_index(
        "ix_document_pages_org_collection", "document_pages", ["organization_id", "collection_id"]
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_search", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(5), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_index"),
        sa.CheckConstraint("lang IN ('ar','en','mixed')", name="ck_chunks_lang"),
        sa.CheckConstraint("page_start >= 1 AND page_end >= page_start", name="ck_chunks_pages"),
    )
    op.create_index("ix_chunks_org_collection", "chunks", ["organization_id", "collection_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("error_detail", sa.String(500)),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','abandoned')",
            name="ck_ingestion_jobs_status",
        ),
    )
    op.create_index("ix_ingestion_jobs_document", "ingestion_jobs", ["document_id", "started_at"])

    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    me, cur = "app_current_user()", "app_current_org()"
    access = f"(organization_id = {cur} AND app_is_member(organization_id, {me}) AND app_can_access_collection(collection_id, {me}))"
    # API side: read-only and access-aware (members see pages of documents they may access)
    for table, prefix in (("document_pages", "pg"), ("chunks", "ck"), ("ingestion_jobs", "jb")):
        op.execute(
            f"CREATE POLICY {prefix}_select ON {table} FOR SELECT TO {APP_ROLE} USING {access}"
        )
        # worker side: full access to exactly these tables (the worker acts for the system, not a user)
        op.execute(
            f"CREATE POLICY {prefix}_worker_all ON {table} FOR ALL TO {WORKER_ROLE} USING (true) WITH CHECK (true)"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {WORKER_ROLE}")
    op.execute(f"GRANT SELECT ON document_pages TO {APP_ROLE}")
    # documents and organizations: only what the worker needs
    op.execute(
        f"CREATE POLICY doc_worker_all ON documents FOR ALL TO {WORKER_ROLE} USING (true) WITH CHECK (true)"
    )
    op.execute(f"GRANT SELECT ON documents TO {WORKER_ROLE}")
    op.execute(
        "GRANT UPDATE (status, error_code, error_detail, page_count, page_summary, language, "
        f"pagination, viewer_key, processed_at, updated_at, purged_at) ON documents TO {WORKER_ROLE}"
    )
    op.execute(
        f"CREATE POLICY org_worker_select ON organizations FOR SELECT TO {WORKER_ROLE} USING (true)"
    )
    op.execute(f"GRANT SELECT (id) ON organizations TO {WORKER_ROLE}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {WORKER_ROLE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS doc_worker_all ON documents")
    op.execute("DROP POLICY IF EXISTS org_worker_select ON organizations")
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    op.execute(f"DROP OWNED BY {WORKER_ROLE}")
    for col in ("processed_at", "page_summary", "viewer_key", "pagination", "language"):
        op.drop_column("documents", col)
