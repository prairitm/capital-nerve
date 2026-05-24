# embeddings

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Pluggable embedding providers for document-page vector indexing at ingest time
and query embedding at RAG time.

## Source

- Path: `backend/app/services/embeddings.py`
- Layer: backend-service

## Contract

- `EmbeddingProvider` protocol — `is_available`, `embed_texts(texts) -> list[list[float]]`.
- `get_embedding_provider()` — picks implementation from `EMBEDDING_PROVIDER` env.

## Dependencies

- May import: `openai` (lazy, inside `OpenAIEmbeddingProvider` only).
- Must not: be imported from pipeline stages other than `indexing.py`.

## Verification checklist

- [ ] `get_embedding_provider()` returns mock when `EMBEDDING_PROVIDER=openai` but no API key (non-production).
- [ ] Production boot fails when `EMBEDDING_PROVIDER=openai` without `OPENAI_API_KEY`.
