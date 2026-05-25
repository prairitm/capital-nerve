# unified_ask

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Single natural-language entry point that routes investor questions to structured
SQL (`data_ask`) or filing RAG (`document_rag`), with SQL-empty fallback to RAG.

## Source

- Path: `backend/app/services/unified_ask.py`
- Layer: backend-service (read-only orchestration)

## Contract

- `classify_route(question) -> "sql" | "rag"` — keyword/heuristic router.
- `ask_unified(db, question, company_id?, event_id?) -> UnifiedAskResult`
- `UnifiedAskResult`: `answer`, `mode`, optional `citations`/`retrieval_mode` (RAG)
  or `sql`/`columns`/`rows`/`row_count` (SQL).

## Dependencies

- May import: `data_ask.ask_data`, `document_rag.ask`.
- Must not: import FastAPI.

## Patterns (symmetry)

- Exposed as `POST /search/ask` only; `POST /search/ask-data` delegates here with `mode=sql` forced.
- SQL path with zero rows falls back to RAG with a short prefix on the answer.

## Verification checklist

- [ ] EPS + quarter + FY questions route to `sql`
- [ ] Management / concall questions route to `rag`
- [ ] Empty SQL result triggers RAG fallback
