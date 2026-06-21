# services/ir_discovery/ingest

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

End-to-end persistence + pipeline driver for one (Company, PeriodSpec)
pair. Mirrors the bookkeeping inside
[`routers/ingest.py:ingest_upload`](../../routers/ingest.py) so a bulk
ingest produces the same `CompanyEvent` + `SourceDocument` +
`ExtractionJob` + `ReviewQueue` rows the HTTP endpoint produces, then
calls `services.pipeline.runner.run_pipeline_for_document` in-process.

## Source

- Path: `backend/app/services/ir_discovery/ingest.py`
- Layer: backend-service (write-side, intake-only)

## Contract

- `ingest_one(db, *, company, period, assets, queued_by_user_id,
  asset_keys=None, skip_pipeline=False, force_reextract=False,
  discovery_source_by_key=None, fallback_by_asset_key=None) -> IngestOutcome`.
- `assets` is a `PeriodAssetSet` returned by either the exchange tier
  (`exchange.discover_period_assets`) or the agent fallback. `asset_keys`
  optionally filters which slots are processed (used by `--doc-types`).
- `discovery_source_by_key` (asset_key -> `"bse" | "nse" | "agent"`)
  is recorded on each `AssetIngestResult.discovery_source` and on
  `SourceDocument.meta.ir_discovery.discovery_source`. The recorded
  source is the one that *actually downloaded* — if the primary URL
  fails and a fallback succeeds, the fallback's source wins.
- `fallback_by_asset_key` (asset_key -> list of `(AssetMatch, source)`)
  is the tier-1 → tier-2 candidate chain. The primary URL on `assets`
  is tried first; on `FetchError` the function walks the fallback list
  in order and keeps the first one that downloads. `result.url` /
  `result.discovery_source` reflect the chosen candidate.
- Per-asset behaviour:
  - Annual / quarterly mismatch → asset skipped with `error` set.
  - Every candidate (primary + fallbacks) raises `FetchError` →
    status `failed`, `error` populated with the *last* candidate's
    error, no DB row.
  - First-time successful download + pipeline run → status `ingested`.
  - Re-download of an already-stored file → status `duplicate`
    (`SourceDocument` reused via `file_hash`). If the document already
    completed extraction (`COMPLETED` + `page_count > 0`) and
    `force_reextract` is false, no new `ExtractionJob` is created and
    the pipeline is not re-run (prevents races with the in-process worker).
  - Inline pipeline runs create jobs as `PROCESSING` (not `PENDING`) so
    the dev worker does not claim the same row while `bulk_ingest` runs
    the pipeline in-process.
  - `skip_pipeline=True` → status `queued` and the worker (or a later
    `ingest_one` call) drains the row.
- `IngestOutcome` aggregates per-pair results and exposes
  `to_jsonable()` so the CLI can serialize one row to the JSONL run log
  without further work.
- The function never raises for asset-level errors — every failure
  surfaces in the corresponding `AssetIngestResult`.

## Dependencies

- May import: `sqlalchemy`, `app.db.enums`, `app.models.{events,
  review}`, `app.services.ingest_common`, `.download`, `.schemas`,
  `app.services.pipeline.runner.run_pipeline_for_document`.
- Must not import: `agents`, FastAPI, anything from `app.routers.*`.

## Patterns (symmetry)

- `(EventType, DocumentType)` resolution comes exclusively from
  `DOC_TYPE_BY_ASSET_KEY` in `.schemas`. Adding a new asset slot is
  centralized there.
- Re-using a `SourceDocument` by `file_hash` mirrors the existing
  upload-endpoint logic — refresh `event_id`, `period_id`,
  `document_type`, `extraction_status=PENDING`. Concurrent workers that
  race on the same hash recover via a savepoint + re-select (NSE often
  maps one PDF to multiple quarters).
- A `CompanyEvent` is reused per `(company, period, event_type)`
  triple to avoid event row explosion when the same asset is
  re-ingested. Annual report events live on the annual period;
  quarterly assets live on the quarterly period.
- `ReviewQueue` rows always use `review_type="new_document_ingested"`,
  `priority=MEDIUM`, `status="OPEN"` — same as the HTTP endpoint.
- Pipeline call shape matches
  [`routers/ingest.COMPONENT.md`](../../routers/ingest.COMPONENT.md):
  the row is committed BEFORE `run_pipeline_for_document` opens its own
  transaction inside the same session.
- `_event_date(period) = period.period_end` is a placeholder; if a real
  filing date becomes available later the agent prompt can return it
  separately.
- `SourceDocument.document_title` and `CompanyEvent.event_title` always use
  [`standard_document_title`](../ingest_common.py) — e.g.
  `RELIANCE Q3 FY2025-26 Financial Results` — never the agent's free-text
  title. The agent title is preserved in `SourceDocument.meta.ir_discovery.agent_title`.

## Verification checklist

- [ ] `ingest_one` writes a `CompanyEvent` + `SourceDocument` +
      `ExtractionJob` + `ReviewQueue` row per non-null asset.
- [ ] Re-running with the same `PeriodAssetSet` produces all
      `duplicate` results and zero new `SourceDocument` rows.
- [ ] An `annual_report` asset on a quarterly `PeriodSpec` (or vice
      versa) is skipped with a clear error string.
- [ ] `skip_pipeline=True` leaves the job in `PENDING` status.
- [ ] On pipeline failure, the asset row carries `status=failed` and
      the error message; the `SourceDocument` survives so an admin can
      retry.
- [ ] `AssetIngestResult.discovery_source` is populated on every
      `to_jsonable()` row when the caller supplied
      `discovery_source_by_key`.
- [ ] When the primary URL fails to download, each
      `fallback_by_asset_key[asset_key]` candidate is tried in order
      and the successful one's `source` becomes the recorded
      `discovery_source` (test:
      `test_primary_html_wrapper_falls_through_to_fallback`).
- [ ] If every candidate fails, the result is `failed` with the last
      candidate's error message; no DB rows are written.
