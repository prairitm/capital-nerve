# scripts/bulk_ingest

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Standalone CLI entry point for the IR-discovery + bulk ingest workflow
documented in [`services/ir_discovery/_BASE.md`](../services/ir_discovery/_BASE.md).
Given a time period, walks every `Company` row in the DB (filterable via
`--symbols`), asks the OpenAI Agents SDK + WebSearch agent for the
financial-results / transcript / presentation / annual-report PDFs per
quarter, downloads them, persists the same `CompanyEvent` /
`SourceDocument` / `ExtractionJob` rows that `POST /ingest/upload`
produces, and runs the production pipeline inline.

## Source

- Path: `backend/app/scripts/bulk_ingest.py`
- Entry: `python -m app.scripts.bulk_ingest [options]`
- Layer: backend-script

## CLI surface

Period range (provide exactly one):

- `--from "Q1 FY25-26" --to "Q3 FY25-26"`
- `--start 2024-04-01 --end 2026-03-31`
- `--last-quarters 6`

Optional:

- `--symbols RELIANCE,TCS` — filter Company sweep.
- `--doc-types financial_report_pdf,transcript,presentation,annual_report`.
- `--include-annual` — adds an ANNUAL `PeriodSpec` for every FY whose
  Q4 is in range.
- `--concurrency N` — bound concurrent agent calls
  (default: `settings.IR_AGENT_CONCURRENCY`).
- `--dry-run` — agent discovery only, no downloads, no DB writes.
- `--skip-pipeline` — persist intake rows but leave the job PENDING for
  the worker.
- `--admin-email you@x.com` — `AppUser` whose id is stamped on
  `ExtractionJob.meta.queued_by_user_id`. Defaults to the first
  `user_type=ADMIN` row.
- `--log-level INFO`.

## Behaviour

- Run id: `<UTC timestamp>-<6 hex>`. Per-run JSONL log is written to
  `IR_AGENT_RUNS_DIR/<run_id>/run.log.jsonl`. Each line is one of:
  - `kind=agent_error` — the agent call failed for that pair.
  - `kind=dry_run` — `--dry-run` payload (asset URLs only).
  - `kind=ingest_outcome` — full `IngestOutcome` JSON (one per
    `(Company, PeriodSpec)` pair).
- Companies with no `nse_symbol` are skipped at startup with a warning
  log line — the agent can't web-search reliably without a ticker.
- Each `(Company, PeriodSpec)` pair is processed concurrently behind an
  `asyncio.Semaphore(concurrency)`. The semaphore wraps only the agent
  call; downloads + DB writes + pipeline runs run on a worker thread
  via `asyncio.to_thread`.
- Each pair gets a fresh `SessionLocal()` so transaction boundaries
  match the in-process pipeline worker.
- Exit code:
  - `0` — every pair completed (including pairs where the agent
    returned no assets).
  - `1` — at least one pair-level failure logged.
  - `2` — bad CLI inputs (period parsing, missing admin user, no
    matching companies).

## Dependencies

- May import: `typer`, `app.core.config.settings`, `app.db.session`,
  `app.models.{master, user}`, `app.services.ir_discovery.*`.
- Must not import: any FastAPI router, any HTTP client beyond what
  `services.ingest_common` already pulls in, anything from
  `app.services.pipeline.runner` directly (call it via `ingest_one`).

## Verification checklist

- [ ] Running with no period flag exits with code 2 and a clear error.
- [ ] Running with two period flags (e.g. `--from` + `--start`) exits
      with code 2.
- [ ] `--dry-run` writes one `kind=dry_run` JSONL line per pair and
      makes zero DB writes.
- [ ] A successful run writes one `kind=ingest_outcome` JSONL line per
      pair, each containing the `assets[]`, `errors[]`, and `summary`
      counts produced by `ingest_one`.
- [ ] An invalid asset key on `--doc-types` raises a Typer
      `BadParameter` before any agent call.
- [ ] No `AppUser(user_type=ADMIN)` exists -> CLI exits with code 2
      and a hint about `--admin-email`.
