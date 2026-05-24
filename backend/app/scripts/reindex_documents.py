"""Backfill FTS vectors and embeddings for all source documents."""
from __future__ import annotations

import logging
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.events import SourceDocument
from app.services.pipeline import indexing as indexing_stage

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    db = SessionLocal()
    try:
        document_ids = db.scalars(select(SourceDocument.document_id).order_by(SourceDocument.document_id)).all()
        total = len(document_ids)
        logger.info("Reindexing %s document(s)", total)
        for i, document_id in enumerate(document_ids, start=1):
            stats = indexing_stage.index_document_pages(db, document_id=document_id)
            db.commit()
            logger.info(
                "[%s/%s] document_id=%s fts_pages=%s embeddings=%s",
                i,
                total,
                document_id,
                stats["fts_pages"],
                stats["embeddings"],
            )
    except Exception:
        db.rollback()
        logger.exception("Reindex failed")
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
