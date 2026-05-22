# routers/ingest

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Document intake. One upload endpoint feeds the ingestion pipeline; a list
endpoint returns queue state for the admin UI. Writes to `extraction_jobs`,
which the worker drains via [`app/services/pipeline/runner.py`](../services/pipeline/runner.py).

## Source

- Path: `backend/app/routers/ingest.py`
- Prefix: `/ingest`
- Tags: `["ingest"]`
- Layer: backend-router

## Endpoints

- `POST /ingest/upload` (202, **multipart**) — the only ingestion entrypoint:
  - File field: `file?` (PDF / markdown / plain text) — optional when
    `document_url` is set; the server fetches http(s) URLs (50 MB cap).
  - Form fields: `company_id`, `event_type`, `document_type`, `document_title`,
    `event_date?`, `period_id?`, `period_label?`, `document_url?`.
  - Requires at least one of `file` or `document_url`. When both are sent,
    `file` supplies the bytes and `document_url` is stored as `source_url`.
  - Writes the bytes to `services/pipeline/storage.LocalStorage`, dedupes by
    sha256 against `SourceDocument.file_hash`, creates the
    `ExtractionJob(status=PENDING)` row the worker polls.
  - Returns `{queued, event_id, document_id, job_id, review_id, file_hash, size_bytes}`.
- `GET /ingest/jobs?limit=` — most recent jobs joined with `SourceDocument`
  and `Company`. Drives the admin "Recent jobs" panel.

## Dependencies

- Imports: `fastapi`, `sqlalchemy`, `app.db.enums`, models (`CompanyEvent`,
  `SourceDocument`, `ExtractionJob`, `ReviewQueue`, `Company`,
  `FinancialPeriod`, `AppUser`), `app.services.pipeline.storage.get_storage`.

## Patterns (symmetry)

- The upload endpoint creates `CompanyEvent(is_published=False)` and
  `SourceDocument(extraction_status=PENDING)` — keep this draft semantic so
  unprocessed documents never leak into the feed.
- Reviews always use `review_type="new_document_ingested"`,
  `priority=MEDIUM`, `status="OPEN"`.
- HTTP 202 on intake — the real work happens asynchronously in the worker.
- Period resolution order: `period_id` → exact `period_label` → parsed
  `Q[1-4] FY…` label (find/create by `fy_year`+`quarter`) → date lookup →
  create-new-quarterly-from-date. Returns HTTP 400 if none resolve.
- Re-uploading the same `file_hash` updates the existing `SourceDocument`
  (`period_id`, `event_id`, `extraction_status=PENDING`) before queuing a job.
- `_suffix_for` keeps storage files introspectable; do not strip suffixes.

## Verification checklist

- [ ] `POST /ingest/upload` rejects requests with neither `file` nor `document_url`.
- [ ] `POST /ingest/upload` rejects empty file bodies and empty remote documents with HTTP 400.
- [ ] URL-only intake fetches http(s) links and stores the URL on `SourceDocument.source_url`.
- [ ] Duplicate uploads reuse the existing `SourceDocument` (no unique-index
      violation on `file_hash`) and refresh `period_id` / `event_id`.
- [ ] `POST /ingest/upload` rejects uploads when period cannot be resolved.
- [ ] Labels like `Q4 FY25-26` create or match `FinancialPeriod` rows.
- [ ] `ExtractionJob` is created only after the file is persisted.
- [ ] `is_published=False` and `extraction_status=PENDING` on the created rows.
- [ ] `GET /ingest/jobs` returns rows ordered by `created_at DESC`.
- [ ] There is no JSON-only `POST /ingest` stub; the only ingestion entry
      point is the multipart upload.
