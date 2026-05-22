# services/pipeline/parsing

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Convert raw uploaded bytes into per-page text + markdown for the rest of the
pipeline. Persists to `document_pages` so the Evidence viewer can render
ingested filings the same way it renders seeded ones.

## Source

- Path: `backend/app/services/pipeline/parsing.py`
- Layer: backend-service

## Contract

- `parse_document_bytes(data, content_type) -> list[ParsedPage]` — dispatches
  to PDF or plain-text parser.
- `persist_pages(db, document, pages) -> int` — wipes existing pages for the
  document and inserts the new batch; updates `SourceDocument.page_count`.
- `ParsedPage` carries both `text` (fed to the LLM) and `markdown` (rendered
  in the evidence viewer).

## Dependencies

- May import: `pypdf`, `sqlalchemy`, `app.models.events`.
- Must not import: any LLM provider, other pipeline stages.

## Patterns (symmetry)

- PDFs: `pypdf.PdfReader(io.BytesIO(...))`; per-page failures are logged but
  do not crash the run.
- Text fallbacks: form-feed (`\f`) splits, otherwise treated as a single page.
- Empty pages are kept so the page numbering matches the source document
  exactly (evidence row references stay aligned).

## Verification checklist

- [ ] `persist_pages` clears prior rows for the document (re-runs are idempotent).
- [ ] `SourceDocument.page_count` matches the inserted row count.
- [ ] PDF parsing failures on a single page don't abort the whole document.
- [ ] No LLM imports.
