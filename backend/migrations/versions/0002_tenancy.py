"""tenancy: organizations, memberships, invitations, app role, row-level security

Revision ID: 0002
Revises: 0001
"""

import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "app_rw"
TENANT_TABLES = ("organizations", "memberships", "invitations")
ALL_TABLES = (*TENANT_TABLES, "users", "refresh_tokens", "password_resets")


def _ensure_app_role() -> None:
    """Create (or refresh the password of) the non-superuser role the API connects as.

    The migration runs as the database owner; the API must NOT, otherwise RLS is bypassed.
    The password comes from the environment and is quoted by Postgres' own format(%L).
    """
    password = os.environ.get("APP_DB_PASSWORD")
    if not password:
        raise RuntimeError("APP_DB_PASSWORD must be set to create the application database role")
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
    ).scalar()
    verb = "ALTER" if exists else "CREATE"
    stmt = bind.execute(
        sa.text(
            f"SELECT format('{verb} ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOBYPASSRLS PASSWORD %L', cast(:pw as text))"
        ),
        {"pw": password},
    ).scalar_one()
    op.execute(stmt)


def upgrade() -> None:
    _ensure_app_role()

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        sa.CheckConstraint(
            "role IN ('owner','admin','editor','member','viewer')", name="ck_memberships_role"
        ),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # owners are never invited; they are promoted from existing members
        sa.CheckConstraint(
            "role IN ('admin','editor','member','viewer')", name="ck_invitations_role"
        ),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_invitations_pending ON invitations (organization_id, email) "
        "WHERE accepted_at IS NULL AND revoked_at IS NULL"
    )

    # ---- tenant context readers (NULL when unset, so policies fail closed) ----
    for name, setting, rtype in (
        ("app_current_org", "app.current_org", "uuid"),
        ("app_current_user", "app.current_user", "uuid"),
        ("app_invite_hash", "app.invite_hash", "text"),
    ):
        op.execute(
            f"CREATE FUNCTION {name}() RETURNS {rtype} LANGUAGE sql STABLE AS "
            f"$$ SELECT nullif(current_setting('{setting}', true), '')::{rtype} $$"
        )

    # ---- membership helpers (SECURITY DEFINER: they read the tables without RLS recursion) ----
    # They make the policies check the AUTHENTICATED USER's membership, which does not depend on
    # the organization id that came from the URL. A bug in the application's membership check
    # therefore cannot expose another organization's rows.
    definer = "LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public"
    op.execute(
        f"CREATE FUNCTION app_is_member(org uuid, usr uuid) RETURNS boolean {definer} AS "
        "$$ SELECT EXISTS (SELECT 1 FROM memberships WHERE organization_id = org AND user_id = usr) $$"
    )
    op.execute(
        f"CREATE FUNCTION app_org_has_members(org uuid) RETURNS boolean {definer} AS "
        "$$ SELECT EXISTS (SELECT 1 FROM memberships WHERE organization_id = org) $$"
    )
    op.execute(
        f"CREATE FUNCTION app_invite_valid(org uuid, hash text, usr uuid) RETURNS boolean {definer} AS "
        "$$ SELECT EXISTS (SELECT 1 FROM invitations i JOIN users u ON lower(u.email::text) = lower(i.email::text) "
        "WHERE i.organization_id = org AND i.token_hash = hash AND i.accepted_at IS NULL "
        "AND i.revoked_at IS NULL AND i.expires_at > now() AND u.id = usr) $$"
    )

    # RLS is enabled but NOT forced: the table owner (migrations) is exempt, and the API connects
    # as `app_rw`, which owns nothing (asserted in tests). FORCE would also bind the SECURITY
    # DEFINER helpers above (they run as the owner) and make them recurse into the policies.
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    me = "app_current_user()"
    cur = "app_current_org()"
    member_of_current = f"({cur} IS NOT NULL AND app_is_member({cur}, {me}))"

    # organizations
    op.execute(
        "CREATE POLICY org_select ON organizations FOR SELECT USING ("
        f"app_is_member(id, {me}) OR (id = {cur} AND NOT app_org_has_members(id)))"
    )  # second clause: only the brand-new org inside the transaction that creates it
    op.execute(f"CREATE POLICY org_insert ON organizations FOR INSERT WITH CHECK (id = {cur})")
    op.execute(
        "CREATE POLICY org_update ON organizations FOR UPDATE "
        f"USING (id = {cur} AND app_is_member(id, {me})) WITH CHECK (id = {cur})"
    )
    op.execute(
        f"CREATE POLICY org_delete ON organizations FOR DELETE USING (id = {cur} AND app_is_member(id, {me}))"
    )

    # memberships: own rows always; others only for members of the current org
    op.execute(
        "CREATE POLICY mem_select ON memberships FOR SELECT "
        f"USING (user_id = {me} OR (organization_id = {cur} AND app_is_member(organization_id, {me})))"
    )
    op.execute(
        "CREATE POLICY mem_insert ON memberships FOR INSERT WITH CHECK (organization_id = "
        f"{cur} AND (app_is_member(organization_id, {me}) OR NOT app_org_has_members(organization_id) "
        f"OR (user_id = {me} AND app_invite_valid(organization_id, app_invite_hash(), {me}))))"
    )  # members add members; the creator bootstraps an empty org; an invitee joins with a valid token
    op.execute(
        "CREATE POLICY mem_update ON memberships FOR UPDATE "
        f"USING (organization_id = {cur} AND app_is_member(organization_id, {me})) "
        f"WITH CHECK (organization_id = {cur})"
    )
    op.execute(
        "CREATE POLICY mem_delete ON memberships FOR DELETE "
        f"USING (organization_id = {cur} AND app_is_member(organization_id, {me}))"
    )

    # invitations: members of the current org; plus lookup-by-token for accepting
    op.execute(
        "CREATE POLICY inv_select ON invitations FOR SELECT USING "
        f"({member_of_current} AND organization_id = {cur} OR token_hash = app_invite_hash())"
    )
    op.execute(
        "CREATE POLICY inv_insert ON invitations FOR INSERT WITH CHECK "
        f"(organization_id = {cur} AND app_is_member(organization_id, {me}))"
    )
    op.execute(
        "CREATE POLICY inv_update ON invitations FOR UPDATE USING "
        f"(organization_id = {cur} AND (app_is_member(organization_id, {me}) "
        f"OR app_invite_valid(organization_id, app_invite_hash(), {me}))) "
        f"WITH CHECK (organization_id = {cur})"
    )
    op.execute(
        "CREATE POLICY inv_delete ON invitations FOR DELETE "
        f"USING (organization_id = {cur} AND app_is_member(organization_id, {me}))"
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for table in ALL_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app_current_org(), app_current_user(), app_invite_hash() TO {APP_ROLE}"
    )


def downgrade() -> None:
    # Roles are cluster-wide, so the role itself is kept; its privileges in this database are dropped.
    op.execute(f"DROP OWNED BY {APP_ROLE}")
    # org_select reads memberships, so it must go before memberships can be dropped
    op.execute("DROP POLICY IF EXISTS org_select ON organizations")
    for table in ("invitations", "memberships", "organizations"):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS app_invite_valid(uuid, text, uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_org_has_members(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_is_member(uuid, uuid)")
    for name in ("app_invite_hash", "app_current_user", "app_current_org"):
        op.execute(f"DROP FUNCTION IF EXISTS {name}()")
