"""document full-text search and page embeddings

Adds PostgreSQL FTS on `document_pages.page_text`. When the host Postgres
ships the `vector` extension (e.g. pgvector/pgvector Docker image), also
creates `document_page_embeddings` for hybrid RAG retrieval.

Revision ID: 0004_document_search
Revises: 0003_market_data
Create Date: 2026-05-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_search"
down_revision: Union[str, None] = "0003_market_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pgvector_installable(connection) -> bool:
    row = connection.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector' LIMIT 1")
    ).first()
    return row is not None


def _embeddings_table_exists(connection) -> bool:
    row = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'document_page_embeddings' "
            "LIMIT 1"
        )
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "document_pages",
        sa.Column("search_vector", sa.dialects.postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index(
        "ix_document_pages_search_vector",
        "document_pages",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.execute(
        "UPDATE document_pages "
        "SET search_vector = to_tsvector('english', coalesce(page_text, ''))"
    )

    if not _pgvector_installable(bind):
        return

    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        # Homebrew Postgres without pgvector binaries — FTS still works.
        return

    if _embeddings_table_exists(bind):
        return

    op.execute(
        """
        CREATE TABLE document_page_embeddings (
            page_id INTEGER NOT NULL PRIMARY KEY
                REFERENCES document_pages(page_id) ON DELETE CASCADE,
            model_name VARCHAR NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_document_page_embeddings_hnsw "
        "ON document_page_embeddings USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()

    if _embeddings_table_exists(bind):
        op.execute("DROP INDEX IF EXISTS ix_document_page_embeddings_hnsw")
        op.drop_table("document_page_embeddings")

    op.drop_index("ix_document_pages_search_vector", table_name="document_pages")
    op.drop_column("document_pages", "search_vector")

    if _pgvector_installable(bind):
        op.execute("DROP EXTENSION IF EXISTS vector")
