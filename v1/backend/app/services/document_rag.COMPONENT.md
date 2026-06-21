# document_rag

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Hybrid-retrieval RAG Q&A over ingested filings with page-linked citations.

## Source

- Path: `backend/app/services/document_rag.py`
- Layer: backend-service

## Contract

- `ask(db, q, *, company_id?, event_id?) -> AskResult` with `answer`, `citations`, `retrieval_mode`.

## Dependencies

- May import: `document_search`, `pipeline.llm` (`answer_from_context`, RAG types).
- Must not: write to the database.

## Verification checklist

- [ ] Returns empty answer when hybrid search finds no hits.
- [ ] Mock LLM path produces citations with correct `page_number`.
- [ ] `retrieval_mode` is `hybrid` or `fts_only`.
