# services/pipeline/parsing

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Convert raw uploaded bytes into per-page text + markdown + rendered PNG for
the rest of the pipeline. Persists to `document_pages` so the Evidence viewer
can render ingested filings the same way it renders seeded ones, and so the
extraction stage can hand the LLM a stable image of the page in addition to
the OCR text.

## Source

- Path: `backend/app/services/pipeline/parsing.py`
- Layer: backend-service

## Contract

- `parse_document_bytes(data, content_type) -> list[ParsedPage]` — dispatches
  to PDF or plain-text parser.
- `persist_pages(db, document, pages) -> int` — wipes existing pages for the
  document and inserts the new batch; writes each `image_bytes` to storage
  via `LocalStorage.put_bytes_at` and stamps `DocumentPage.image_path`;
  updates `SourceDocument.page_count`.
- `ParsedPage` carries `text` (FTS / RAG / LLM-OCR), `markdown` (evidence
  viewer), and `image_bytes` (the rendered PNG that the LLM vision call uses).
- `PARSER_VERSION` — module constant. Bumping invalidates the extraction
  cache on `extraction_jobs.request_hash` because the LLM input can no longer
  be assumed equal across runs.

## Dependencies

- May import: `pypdf`, `pdf2image` (lazy — requires the host `poppler-utils`
  binary), `sqlalchemy`, `app.models.events`, `app.services.pipeline.storage`.
- Must not import: any LLM provider, other pipeline stages besides storage.

## Patterns (symmetry)

- PDFs: `pypdf.PdfReader(io.BytesIO(...))` for text; `pdf2image.convert_from_bytes`
  at 200 DPI for the per-page PNG. Per-page text failures are logged but do
  not crash the run; if `poppler` is missing on the host, page rendering
  degrades to no-images (the LLM will operate text-only), which is logged
  once with a warning.
- Page PNGs are written to `STORAGE_DIR/page_images/<document_id>/<page>.png`
  via the dedicated `LocalStorage.put_bytes_at` method (path-addressed,
  unlike the default content-addressed `put_bytes`).
- Text fallbacks: form-feed (`\f`) splits, otherwise treated as a single page.
  No image is rendered for the text-only path.
- Empty pages are kept so the page numbering matches the source document
  exactly (evidence row references stay aligned).
- `indexing.index_document_pages` runs immediately after `persist_pages` in
  the runner to populate `search_vector` and optional embeddings.

## Verification checklist

- [ ] `persist_pages` clears prior rows for the document (re-runs are idempotent):
      DELETE + flush + `expire_all()` before INSERT.
- [ ] `SourceDocument.page_count` matches the inserted row count.
- [ ] PDF parsing failures on a single page don't abort the whole document.
- [ ] `DocumentPage.image_path` is set whenever poppler is available and the
      source is a PDF.
- [ ] No LLM imports.
- [ ] `PARSER_VERSION` is folded into the extraction cache key (see
      `extraction._compute_request_hash`).
