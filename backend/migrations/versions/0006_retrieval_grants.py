"""let the API role read chunks (retrieval), still through row-level security

Revision ID: 0006
Revises: 0005

The `chunks` SELECT policy for `app_rw` has existed since 0004 (a member sees a chunk only when
they belong to the organization AND may access its collection) but the table privilege was withheld
until the API had a reason to read it. Retrieval is that reason. Writes stay worker-only.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON chunks TO app_rw")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON chunks FROM app_rw")
