"""drop the `simple`-config full-text column (it did not earn its place)

Revision ID: 0007
Revises: 0006

Stage 6 added `content_tsv_simple` so stage 7 could MEASURE whether the language-aware
(arabic/english) configs beat plain `simple`. They do not under the chosen hybrid fusion (recall@5
0.94 vs 0.94, MRR 0.82 vs 0.81) but they clearly win when the embedder is down and full text
answers alone (MRR 0.71 vs 0.61), so the language-aware column stays and this one goes. The
evaluation computes the `simple` variant inline when it needs to (docs/eval/stage7-retrieval.md).
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv_simple")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_tsv_simple")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv_simple tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content_search)) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_content_tsv_simple ON chunks USING gin (content_tsv_simple)")
