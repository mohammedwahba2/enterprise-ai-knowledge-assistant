"""embeddings and lexical search columns on chunks

Revision ID: 0005
Revises: 0004

Adds, to `chunks`:
  * `embedding vector(1024)` + `embedding_model` (a vector without its model is meaningless, so both
    or neither), indexed with HNSW (cosine). Changing the model is a supported re-index, not a
    migration: chunks embedded by another model are simply stale (see `reindex_stale`).
  * `content_tsv`: language-aware full text (generated from the already search-normalized text:
    `arabic` config for Arabic chunks, `english` for English, both for mixed) and
    `content_tsv_simple`: the same text with the `simple` config, so stage 7 can measure the Arabic
    stemmer instead of assuming it helps.
The API role still has no privileges on `chunks`; retrieval grants arrive with stage 7.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

DIMENSIONS = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE chunks ADD COLUMN embedding vector({DIMENSIONS})")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding_model text")
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT ck_chunks_embedding_model "
        "CHECK ((embedding IS NULL) = (embedding_model IS NULL))"
    )
    op.execute(
        """
        ALTER TABLE chunks ADD COLUMN content_tsv tsvector GENERATED ALWAYS AS (
          CASE lang
            WHEN 'ar' THEN to_tsvector('arabic'::regconfig, content_search)
            WHEN 'en' THEN to_tsvector('english'::regconfig, content_search)
            ELSE to_tsvector('arabic'::regconfig, content_search)
                 || to_tsvector('english'::regconfig, content_search)
          END
        ) STORED
        """
    )
    op.execute(
        "ALTER TABLE chunks ADD COLUMN content_tsv_simple tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, content_search)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
    op.execute("CREATE INDEX ix_chunks_content_tsv ON chunks USING gin (content_tsv)")
    op.execute("CREATE INDEX ix_chunks_content_tsv_simple ON chunks USING gin (content_tsv_simple)")
    # Finds chunks that were never embedded without scanning every row.
    op.execute("CREATE INDEX ix_chunks_unembedded ON chunks (document_id) WHERE embedding IS NULL")


def downgrade() -> None:
    for index in (
        "ix_chunks_unembedded",
        "ix_chunks_content_tsv_simple",
        "ix_chunks_content_tsv",
        "ix_chunks_embedding_hnsw",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")
    for column in ("content_tsv_simple", "content_tsv", "embedding_model", "embedding"):
        op.execute(f"ALTER TABLE chunks DROP COLUMN IF EXISTS {column}")
