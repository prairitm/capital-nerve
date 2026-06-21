# services/pipeline/indexing

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Rebuild PostgreSQL FTS (`search_vector`) and pgvector embeddings for all pages
of a source document immediately after parsing.

## Source

- Path: `backend/app/services/pipeline/indexing.py`
- Layer: backend-service

## Contract

- `index_document_pages(db, *, document_id) -> dict[str, int]` — returns
  `{ "fts_pages": N, "embeddings": M }`.

## Dependencies

- May import: `sqlalchemy`, `app.models.events`, `app.services.embeddings`.
- Must not import: LLM extraction providers.

## Patterns (symmetry)

- Called from `runner.py` right after `persist_pages` + `db.flush()`.
- Wipes and re-inserts embeddings for the document's pages on every run.
- Skips vector rows when the embedding provider is unavailable or embed fails.

## Verification checklist

- [ ] `search_vector` populated via `to_tsvector('english', page_text)`.
- [ ] Re-running the pipeline rebuilds FTS and embeddings idempotently.
- [ ] Empty `page_text` pages get FTS but no embedding row.
