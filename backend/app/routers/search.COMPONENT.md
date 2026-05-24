# routers/search

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Lightweight ILIKE search across companies, events, and intelligence cards, plus
full-text search over ingested filing pages and a cited RAG Q&A endpoint.

## Source

- Path: `backend/app/routers/search.py`
- Prefix: `/search`
- Tags: `["search"]`
- Layer: backend-router

## Endpoints

- `GET /search?q=` — `q` is required (`Query(min_length=1)`). Optional
  `company_id`, `document_type`. Returns
  `{ companies, events, cards, document_hits }`.
- `POST /search/ask` — body `{ q, company_id?, event_id? }`. Returns cited
  answer with `retrieval_mode` (`hybrid` | `fts_only`).

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select` / `or_`, models (`Company`, `Sector`,
  `CompanyEvent`, `IntelligenceCard`, `AppUser`), helper `company_brief`,
  `document_search.search_pages_fts`, `document_rag.ask`.

## Patterns (symmetry)

- Single string-LIKE pattern: `f"%{q.lower()}%"` for companies/events/cards.
- Caps: 10 companies, 10 events, 15 cards, **15 document_hits**.
- Document FTS uses PostgreSQL `plainto_tsquery` + `ts_headline` via
  `document_search.search_pages_fts`.
- The response uses ad hoc dicts for GET (no `response_model`). When you add a
  field, mirror it in the frontend `SearchResult` interface.

## Verification checklist

- [ ] Pattern uses lower-cased `f"%{q.lower()}%"` for ILIKE dimensions
- [ ] Caps preserved (10 / 10 / 15 / 15)
- [ ] Field additions mirrored in `frontend/src/api/types.ts SearchResult`
- [ ] No new search type added without updating `TopSearch` and `SearchPage`
- [ ] `POST /search/ask` returns citations with `document_id` + `page_number`
