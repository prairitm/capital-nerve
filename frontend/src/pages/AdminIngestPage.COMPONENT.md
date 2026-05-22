# AdminIngestPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Admin-only ingestion console at `/admin/ingest`. Uploads source documents
into the real pipeline (parse → LLM extract → metrics → signals → cards) and
shows the live queue of `ExtractionJob`s with their status, model, confidence,
and card counts.

## Source

- Path: `frontend/src/pages/AdminIngestPage.tsx`
- Route: `/admin/ingest`
- Layer: frontend-page (admin)

## Contract

- Reads:
  - `GET /v1/companies` — populates the company picker.
  - `GET /ingest/jobs?limit=30` — recent extraction jobs, polled every 4s.
- Writes:
  - `POST /admin/companies` — create issuer before first upload.
  - `POST /admin/clear-all-companies` — purge every company and dependent intelligence (confirm dialog).
  - `GET /admin/sectors` — sector datalist for new company form.
  - `POST /ingest/upload` via `apiUpload(...)` with `FormData` containing
    `file?` and/or `document_url?` (at least one required), `company_id`,
    `event_type`, `document_type`, `document_title`, `period_label` (same value
    as `document_title`, e.g. `Q4 FY25-26`), optional `event_date` (overrides
    label-based period when set).
- Response: `IngestUploadResponse { job_id, document_id, event_id, review_id, file_hash, size_bytes }`.

## Dependencies

- May import: `@tanstack/react-query`, `react-router-dom` (`Navigate`),
  `lucide-react`, `clsx`, `@/api/client` (`api`, `apiUpload`), `@/api/types`,
  `@/components/common/Spinner` (`PageLoader`), `@/store/auth`.
- Must not: import the LLM / pipeline server-side modules; the frontend only
  talks to HTTP endpoints.

## Patterns (symmetry)

- Page guard: `if (user && user.user_type !== "ADMIN") return <Navigate to="/" replace />;`
  (same convention as [`AdminReviewPage`](AdminReviewPage.tsx)).
- React Query is `enabled: user?.user_type === "ADMIN"`.
- Jobs query uses `refetchInterval: 4000` so the table updates while the
  worker processes — keep this interval ≥ the worker's poll interval.
- On successful upload, invalidate both `["extraction-jobs"]` and
  `["review"]` so the Review Queue and the jobs panel reflect the new row.
- On successful clear-all, invalidate `["companies"]`, `["extraction-jobs"]`,
  `["review"]`, `["watchlist"]`, `["feedSummary"]`, and `["feed"]`; reset the
  selected company id.
- Multipart upload uses `apiUpload` (multipart/form-data) — never call `api()`
  with `FormData`; that helper hard-codes JSON content type.

## UI / UX

- **Start fresh** banner (destructive): `window.confirm` then `POST /admin/clear-all-companies`; status text under the banner on success.
- Company field: **Existing** dropdown vs **New company** inline form (create then auto-select).
- Two-column layout on `lg+`: 1/3 form, 2/3 jobs table.
- Form fields use the `.input` utility; file picker hides browser styling via
  `file:rounded-md file:bg-surface-2`.
- Status chips reuse `chip-positive` / `chip-negative` / `chip-mixed` /
  `chip-low` / `chip-neutral` — never invent new chip utilities; if a state
  needs a new tone, add it to [`styles.css`](../styles.css).
- Mobile: stacks the form above the table (`grid-cols-1`).

## Verification checklist

- [ ] Non-admin users redirected to `/`.
- [ ] Jobs query enabled only for admins.
- [ ] Upload disabled until a file or document URL, company, and period label are set.
- [ ] `document_title` and `period_label` sent with the same trimmed period string.
- [ ] Picking a file clears the URL field; typing a URL clears the file input.
- [ ] Successful upload clears the file input and URL field (period label is kept).
- [ ] Status chips use existing `chip-*` utilities (no `chip-warning` etc.).
- [ ] Cost/tokens columns degrade to `—` when null (mock provider has none).
- [ ] Jobs table shows `meta.stages.signals` in the Signals column; completed jobs with zero signals show **No signals fired** under status.
- [ ] Clear-all requires confirm; success message shows count and symbols removed.
