"""Runtime checks for pgvector / document_page_embeddings availability."""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


def pgvector_extension_available(connection: Connection | Engine) -> bool:
    """True when the `vector` extension is installable on this Postgres server."""
    row = connection.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector' LIMIT 1")
    ).first()
    return row is not None


def embeddings_table_exists(connection: Connection | Engine | Session) -> bool:
    if isinstance(connection, Session):
        bind = connection.get_bind()
    else:
        bind = connection
    return inspect(bind).has_table("document_page_embeddings")


def pgvector_ready(connection: Connection | Engine | Session) -> bool:
    """True when semantic vector search can run (extension table present)."""
    return embeddings_table_exists(connection)
