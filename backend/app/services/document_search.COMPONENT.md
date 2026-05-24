# document_search

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Read-side full-text and hybrid vector search over ingested `document_pages`.

## Source

- Path: `backend/app/services/document_search.py`
- Layer: backend-service

## Contract

- `search_pages_fts(db, q, *, company_id?, event_id?, document_type?, limit?)`
- `search_pages_vector(db, query_embedding, *, filters...)`
- `hybrid_search_pages(db, q, *, filters...) -> (hits, retrieval_mode)`
- `DocumentPageHit` dataclass with page/document/company metadata + snippet.

## Dependencies

- May import: SQLAlchemy, event/master models, `app.services.embeddings`.
- Must not: write to the database.

## Verification checklist

- [ ] FTS uses `plainto_tsquery` + `ts_headline`.
- [ ] Hybrid merge dedupes by `page_id` via reciprocal rank fusion.
- [ ] Falls back to `fts_only` when embeddings unavailable.
