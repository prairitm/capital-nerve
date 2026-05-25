# routers/documents

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Document detail payload powering the Document page and the Evidence Viewer.

## Source

- Path: `backend/app/routers/documents.py`
- Prefix: `/documents`
- Tags: `["documents"]`
- Layer: backend-router

## Endpoints

- `GET /documents/{document_id}` — returns a dict with `document_id`, `document_type`, `document_title`, `has_source_file`, `source_content_type`, `document_date`, `extraction_confidence`, `extraction_status`, `values_extracted`, `cards_generated`, `page_count`, `company`, `pages`, `cards`, `evidence`. `evidence` merges `card_evidence` and supplemental `ExtractedValue` rows, **deduped by `(page_number, label, value)`** for the panel (prefers rows with `source_text`). Supplemental rows use negative `card_evidence_id` and `evidence_type="extracted_value"`.
- `POST /documents/{document_id}/reextract` — queues a new `ExtractionJob` for that document only (same stored file; does not require re-upload). Returns `202` with `{ queued, document_id, job_id, extraction_status }`. `409` when a `PENDING`/`PROCESSING` job already exists; `400` when there is no source file on disk.
- `GET /documents/{document_id}/file` — streams the stored upload bytes (`Content-Disposition: inline`) for PDF viewing in the Evidence Viewer. Requires auth; 404 when `storage_path` is missing or the file no longer exists on disk.
- 404 when the document does not exist.

## Dependencies

- Imports: `fastapi`, `fastapi.responses.Response`, `sqlalchemy.select`, models (`DocumentPage`, `SourceDocument`, `ExtractionJob`, `CardEvidence`, `IntelligenceCard`, `Company`, `AppUser`), `app.db.enums.ExtractionStatus`, `app.services.pipeline.storage.get_storage`.

## Patterns (symmetry)

- `pages` are sorted ascending by `page_number` — the EvidenceViewer assumes this order.
- `cards` is filtered to `document_id` only (this view is per-document; for event-level cards use `/events/{event_id}`).
- Each `evidence` row is keyed by `card_evidence_id` and includes `page_number` for client-side filtering by active page.
- Enums are serialized as `.value` strings. Floats are cast explicitly from `Numeric`.

## Verification checklist

- [ ] Pages sorted ascending by `page_number`
- [ ] Cards filtered by `document_id`
- [ ] Evidence rows expose `page_number` for the viewer's active-page filter
- [ ] `has_source_file` / `source_content_type` mirrored in `DocumentDetail` (`frontend/src/api/types.ts`)
- [ ] `/file` returns inline bytes with correct `Content-Type` for uploaded PDFs
- [ ] `/reextract` rejects when `storage_path` is missing and when a job is already active
