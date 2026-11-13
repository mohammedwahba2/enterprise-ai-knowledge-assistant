"""collections, collection_members, documents with access-aware row-level security

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "app_rw"
TABLES = ("collections", "collection_members", "documents")
STATUSES = (
    "uploaded", "parsing", "chunking", "embedding", "ready", "ready_partial", "failed",
    "unsupported_scanned", "unsupported_garbled",
)  # fmt: skip


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("visibility", sa.String(12), nullable=False, server_default="org"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("visibility IN ('org','restricted')", name="ck_collections_visibility"),
    )
    op.create_index("ix_collections_organization_id", "collections", ["organization_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_collections_org_name ON collections (organization_id, lower(name))"
    )

    op.create_table(
        "collection_members",
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_collection_members_user", "collection_members", ["user_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="uploaded"),
        sa.Column("error_code", sa.String(40)),
        sa.Column("error_detail", sa.String(500)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN (" + ",".join(f"'{s}'" for s in STATUSES) + ")", name="ck_documents_status"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_documents_size"),
    )
    op.create_index(
        "ix_documents_org_collection_created",
        "documents",
        ["organization_id", "collection_id", sa.text("created_at DESC")],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_documents_dedupe ON documents (organization_id, collection_id, sha256) "
        "WHERE deleted_at IS NULL"
    )

    # Helpers (SECURITY DEFINER so they read other tables without recursing into their policies).
    definer = "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public"
    op.execute(
        f"CREATE FUNCTION app_is_admin(org uuid, usr uuid) RETURNS boolean {definer} AS "
        "$$ SELECT EXISTS (SELECT 1 FROM memberships WHERE organization_id = org AND user_id = usr "
        "AND role IN ('owner','admin')) $$"
    )
    op.execute(
        f"CREATE FUNCTION app_in_collection(col uuid, usr uuid) RETURNS boolean {definer} AS "
        "$$ SELECT EXISTS (SELECT 1 FROM collection_members WHERE collection_id = col AND user_id = usr) $$"
    )
    # Shared by every table that hangs off a collection (documents now, chunks later).
    op.execute(
        f"CREATE FUNCTION app_can_access_collection(col uuid, usr uuid) RETURNS boolean {definer} AS "
        "$$ SELECT EXISTS ("
        "  SELECT 1 FROM collections c "
        "  WHERE c.id = col AND EXISTS (SELECT 1 FROM memberships m "
        "      WHERE m.organization_id = c.organization_id AND m.user_id = usr) "
        "    AND (c.visibility = 'org' OR app_is_admin(c.organization_id, usr) OR app_in_collection(c.id, usr))"
        ") $$"
    )

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    me, cur = "app_current_user()", "app_current_org()"

    # collections: only the ones the user may access (restricted ones are invisible otherwise).
    # Written against the row's own columns: a helper that re-reads `collections` cannot see the
    # row being inserted by the same statement, which would break INSERT ... RETURNING.
    visible = (
        f"(organization_id = {cur} AND app_is_member(organization_id, {me}) AND "
        f"(visibility = 'org' OR app_is_admin(organization_id, {me}) OR app_in_collection(id, {me})))"
    )
    op.execute(f"CREATE POLICY col_select ON collections FOR SELECT USING {visible}")
    op.execute(
        "CREATE POLICY col_insert ON collections FOR INSERT WITH CHECK "
        f"(organization_id = {cur} AND app_is_member(organization_id, {me}))"
    )
    op.execute(
        f"CREATE POLICY col_update ON collections FOR UPDATE USING {visible} WITH CHECK (organization_id = {cur})"
    )
    op.execute(f"CREATE POLICY col_delete ON collections FOR DELETE USING {visible}")
    for cmd, clause in (("SELECT", "USING"), ("DELETE", "USING")):
        op.execute(
            f"CREATE POLICY cm_{cmd.lower()} ON collection_members FOR {cmd} {clause} "
            f"(organization_id = {cur} AND app_is_member(organization_id, {me}) "
            f"AND app_can_access_collection(collection_id, {me}))"
        )
    op.execute(
        "CREATE POLICY cm_insert ON collection_members FOR INSERT WITH CHECK "
        f"(organization_id = {cur} AND app_is_member(organization_id, {me}) "
        f"AND app_can_access_collection(collection_id, {me}))"
    )
    op.execute(
        "CREATE POLICY cm_update ON collection_members FOR UPDATE USING "
        f"(organization_id = {cur} AND app_is_member(organization_id, {me}) AND app_can_access_collection(collection_id, {me})) "
        f"WITH CHECK (organization_id = {cur})"
    )

    # documents: tenant AND membership AND access to the document's collection (database-level
    # document permissions: independent of every application filter)
    doc_access = f"(organization_id = {cur} AND app_is_member(organization_id, {me}) AND app_can_access_collection(collection_id, {me}))"
    op.execute(f"CREATE POLICY doc_select ON documents FOR SELECT USING {doc_access}")
    op.execute(f"CREATE POLICY doc_insert ON documents FOR INSERT WITH CHECK {doc_access}")
    op.execute(
        f"CREATE POLICY doc_update ON documents FOR UPDATE USING {doc_access} WITH CHECK (organization_id = {cur})"
    )
    op.execute(f"CREATE POLICY doc_delete ON documents FOR DELETE USING {doc_access}")

    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_is_admin(uuid, uuid), app_in_collection(uuid, uuid), "
        f"app_can_access_collection(uuid, uuid) TO {APP_ROLE}"
    )

    # Every existing workspace gets a default collection (runs as owner, so RLS does not apply).
    op.execute(
        "INSERT INTO collections (id, organization_id, name, description, visibility) "
        "SELECT gen_random_uuid(), id, 'General', '', 'org' FROM organizations"
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS app_can_access_collection(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_in_collection(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_is_admin(uuid, uuid)")
