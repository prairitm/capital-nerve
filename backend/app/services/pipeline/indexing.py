"""Stage 1b: full-text and vector indexing for document pages.

Runs immediately after `parsing.persist_pages` so every ingested filing
(concall, result, presentation, announcement, etc.) is searchable.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.pgvector_cap import pgvector_ready
from app.models.events import DocumentPage, DocumentPageEmbedding
from app.services.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


def index_document_pages(db: Session, *, document_id: int) -> dict[str, int]:
    """Rebuild FTS vectors and page embeddings for one document."""
    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
    ).all()

    db.execute(
        update(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .values(
            search_vector=func.to_tsvector("english", func.coalesce(DocumentPage.page_text, ""))
        )
    )

    page_ids = [p.page_id for p in pages]
    embeddings_written = 0
    provider = get_embedding_provider()
    if page_ids and provider.is_available and pgvector_ready(db):
        db.execute(
            delete(DocumentPageEmbedding).where(DocumentPageEmbedding.page_id.in_(page_ids))
        )
        pairs = [(p.page_id, (p.page_text or "").strip()) for p in pages]
        non_empty = [(pid, text) for pid, text in pairs if text]
        if non_empty:
            try:
                vectors = provider.embed_texts([text for _, text in non_empty])
            except Exception as exc:
                logger.warning("Embedding failed for document %s: %s", document_id, exc)
                vectors = []
            for (page_id, _), vector in zip(non_empty, vectors):
                db.add(
                    DocumentPageEmbedding(
                        page_id=page_id,
                        model_name=provider.name,
                        embedding=vector,
                    )
                )
                embeddings_written += 1

    db.flush()
    return {"fts_pages": len(pages), "embeddings": embeddings_written}
