# services/ingest_common

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Shared building blocks that both the multipart ingest router
([`routers/ingest.py`](../routers/ingest.py)) and the standalone bulk-ingest
CLI ([`scripts/bulk_ingest.py`](../scripts/bulk_ingest.py)) rely on:

- HTTP fetch of a remote PDF / text filing into raw bytes (with size cap and
  content-type sniffing).
- Storage suffix derivation from filename + content-type.
- `FinancialPeriod` resolution by id, label, or event date — creating a
  quarterly (or annual) row on the fly when needed.

Splitting these helpers out of the router lets the CLI ingest documents
without dragging FastAPI into the call graph.

## Source

- Path: `backend/app/services/ingest_common.py`
- Layer: backend-service (write-side helper, but does not own ingestion
  bookkeeping; tables are still written by the router or by
  [`services/ir_discovery/ingest.py`](ir_discovery/_BASE.md))

## Contract

- **Canonical period labels** (match `seed_catalog` / `FinancialPeriod.display_label`):
  - Quarterly: `format_quarterly_display_label(fy_year, quarter)` → `Q3 FY2025-26`
  - Annual: `format_annual_display_label(fy_year)` → `FY2025-26`
  - Slug: `period_slug_from_display_label(display_label)` → `Q3_FY2025-26`
- **Standard document naming** (bulk ingest mirror + DB titles):
  - `standard_document_basename(document_type)` → `financial_result`
  - `standard_document_title(symbol, display_label, document_type)` →
    `RELIANCE Q3 FY2025-26 Financial Results`
- `fetch_document_from_url(url) -> (bytes, filename, content_type)` —
  raises `FetchError` on bad scheme, oversize body, HTTP/network errors,
  empty bodies, and non-PDF/text content. Also rejects responses that
  *claim* to be a PDF (URL ends in `.pdf` or `Content-Type: application/pdf`)
  but whose body does not start with the `%PDF-` magic header — BSE's
  CDN returns a 200 OK HTML wrapper page when an attachment id is
  missing, and we will not store that as a fake `.pdf`.
- For known exchange CDN hosts (`bseindia.com`, `nseindia.com`,
  `nsearchives.nseindia.com`) the fetcher uses a browser-style
  `User-Agent` + `Referer` and a 60s read timeout. Without these,
  NSE archive downloads silently hang.
- `suffix_for(filename, content_type) -> str` — returns one of
  `.pdf` / `.md` / `.txt` / `.bin`.
- `resolve_period_id(db, *, period_id, period_label, event_date) -> int | None`
  — `None` only when all three inputs are absent. Raises
  `PeriodResolutionError` when a passed `period_id` does not exist.
- `parse_period_label("Q4 FY25-26") -> (4, 2025)` — returns `None` for
  unrecognised labels.
- `quarter_date_bounds(fy_year, quarter) -> (start, end, fy_label, display_label)`
  — Indian-FY math (Apr-Jun = Q1).
- `create_period_from_quarter(db, *, fy_year, quarter)` /
  `create_period_from_date(db, d)` /
  `create_annual_period(db, *, fy_year)` — idempotent inserts; safe to call
  inside an active transaction.
- `MAX_URL_BYTES` — public constant, currently 50 MB.

## Dependencies

- May import: `httpx`, `sqlalchemy`, `app.db.enums.PeriodType`,
  `app.models.master.FinancialPeriod`.
- Must not import: any FastAPI symbol, any router module, anything from
  `app.services.pipeline` (storage / pipeline are downstream consumers, not
  upstream deps).

## Patterns (symmetry)

- Public exceptions are `ValueError` subclasses
  (`FetchError`, `PeriodResolutionError`) so non-HTTP callers can `except`
  cleanly. The router converts each into HTTP 400 with the same `str(exc)`.
- Period creation is idempotent: every helper does a
  `select(...).first()` before inserting, mirroring the seed catalog rule
  documented in [`seed/seed_catalog.COMPONENT.md`](../seed/seed_catalog.COMPONENT.md).
- Suffix detection prefers the filename extension; content-type is the
  fallback. The router and the CLI both rely on this so storage objects
  stay introspectable on disk / in S3.

## Verification checklist

- [ ] `fetch_document_from_url` rejects non-http(s) schemes, oversize
      bodies, non-PDF/text payloads, and HTML pages served with a
      `.pdf` URL or `application/pdf` content-type (PDF magic check).
- [ ] `fetch_document_from_url` sends browser-style headers + a 60s
      read timeout for hosts under `nseindia.com` / `bseindia.com`.
- [ ] `resolve_period_id` returns the existing row's id for an exact
      `display_label` match, parses `Q4 FY25-26` style labels, and creates
      a quarterly row from `event_date` when no other input matches.
- [ ] `quarter_date_bounds(2025, 1)` returns `(2025-04-01, 2025-06-30,
      "FY2025-26", "Q1 FY2025-26")`.
- [ ] `create_annual_period(db, fy_year=2025)` is a no-op the second time.
- [ ] `routers/ingest.py` imports `fetch_document_from_url`,
      `resolve_period_id`, and `suffix_for` from this module — there is no
      duplicate copy in the router.
