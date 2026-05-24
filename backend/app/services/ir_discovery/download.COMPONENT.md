# services/ir_discovery/download

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Pulls one asset URL and lands it in two places:

1. **Canonical store** — `var/storage/aa/bb/<sha256>.<ext>` via
   [`services/pipeline/storage.LocalStorage`](../pipeline/storage.py). This
   is the path the rest of the pipeline reads from. Swapping to S3 only
   touches that module.
2. **Human mirror** — `var/ingest_runs/<symbol>/<period_slug>/<SYMBOL>_<period_slug>_<document_type>.<ext>`,
   e.g. `RELIANCE/Q3_FY2025-26/RELIANCE_Q3_FY2025-26_financial_result.pdf`.
   Period slug is always the canonical display label with spaces replaced by
   underscores (`Q3 FY2025-26` → `Q3_FY2025-26`).
   a parallel browsable layout for operators. Best-effort; failures here
   do not abort the ingest.

## Source

- Path: `backend/app/services/ir_discovery/download.py`
- Layer: backend-service

## Contract

- `fetch_to_storage(*, url, company, period, asset_key, storage=None)
  -> DownloadResult`.
- Raises `app.services.ingest_common.FetchError` for any download
  failure; the caller handles it without reraising.
- `DownloadResult` carries the `StoredFile` + absolute canonical path +
  optional mirror path + sniffed `filename` / `content_type`. The mirror
  path is `None` if the copy failed.

## Dependencies

- May import: `httpx`-backed
  `app.services.ingest_common.fetch_document_from_url`, `suffix_for`,
  `FetchError`; `app.services.pipeline.storage.{LocalStorage,
  StoredFile, get_storage}`; `app.core.config.settings`.
- Must not import: SQLAlchemy session, `app.services.ir_discovery.ingest`,
  any router module.

## Patterns (symmetry)

- The mirror path uses a `_slug` helper that keeps dots so suffixes work
  but strips other unsafe characters.
- The mirror copy is a `shutil.copyfile`, not a hard-link, so an S3 swap
  on the canonical store does not break the local mirror.
- A pre-existing mirror file with the same size is treated as
  already-correct (no re-copy).
- All log messages include the `nse_symbol or company_name` and the
  `period.display_label` so grepping the run log per company / quarter
  works.

## Verification checklist

- [ ] `fetch_to_storage` returns a `DownloadResult` with non-empty
      `stored.file_hash` and `canonical_path`.
- [ ] The mirror file under `var/ingest_runs/<symbol>/<period>/` has the
      same SHA256 as the canonical file.
- [ ] A mirror-write failure is logged but does not raise.
- [ ] Subsequent calls with the same URL do not write a second copy
      (sha256 dedupe + same-size mirror check).
