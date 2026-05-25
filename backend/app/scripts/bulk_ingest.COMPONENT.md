# scripts/bulk_ingest

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Standalone CLI entry point for the IR-discovery + bulk ingest workflow
documented in [`services/ir_discovery/_BASE.md`](../services/ir_discovery/_BASE.md).
Given a time period, walks every `Company` row in the DB (filterable via
`--symbols`) and resolves the financial-results / transcript /
presentation / annual-report PDF for each `(Company, PeriodSpec)` pair
using the two-tier discovery flow:

1. **Tier 1** — `services/ir_discovery/exchange.discover_period_assets`
   hits the BSE corporate-filings API (`AnnGetData/w`) first and the
   NSE `corporate-announcements` API for the same window. BSE wins the
   primary slot when both have a hit; NSE's same-type filing is parked
   as a download-time fallback. Free, deterministic, mandate-backed.
2. **Tier 2** — `services/ir_discovery/agent.find_period_assets`
   (OpenAI Agents SDK + WebSearchTool) runs whenever any slot is
   missing AND `--no-agent-fallback` was NOT passed. Its URLs become
   the primary for empty slots; for slots tier-1 already filled, the
   agent's URL is appended to that slot's fallback chain.
3. **Download with fallback** — at ingest time, the primary URL is
   tried first. If it raises `FetchError` (HTTP error, oversized
   body, or — most importantly — a 200 OK HTML wrapper masquerading
   as a PDF), the next fallback in the chain is tried, until one
   succeeds or the chain is exhausted. The successful candidate's
   source becomes the recorded `discovery_source` on the JSONL row
   and on `SourceDocument.meta.ir_discovery.discovery_source`.

Each filled slot is downloaded, persisted as the same `CompanyEvent` /
`SourceDocument` / `ExtractionJob` rows that `POST /ingest/upload`
produces, and the production pipeline is run inline.

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
- `--force-reextract` — when the same `file_hash` was already extracted
  successfully, run the pipeline again anyway. Default: completed
  duplicates skip pipeline re-run (avoids `uq_document_pages` races).
- `--no-agent-fallback` — skip the WebSearch agent. Tier-1 results
  only; missing slots stay missing. Useful for cost-bound runs and
  for verifying BSE/NSE coverage in isolation.
- `--agent-only` — skip the BSE/NSE tier-1 entirely; rely on the
  WebSearch agent for every slot. Mutually exclusive with
  `--no-agent-fallback`. Useful when an exchange API is down, when
  benchmarking the agent in isolation, or when running on companies
  that don't trade on NSE/BSE.
- `--admin-email you@x.com` — `AppUser` whose id is stamped on
  `ExtractionJob.meta.queued_by_user_id`. Defaults to the first
  `user_type=ADMIN` row.
- `--log-level INFO`.

## Behaviour

- Run id: `<UTC timestamp>-<6 hex>`. Per-run JSONL log is written to
  `IR_AGENT_RUNS_DIR/<run_id>/run.log.jsonl`. Each line is one of:
  - `kind=agent_error` — the agent fallback call failed for that
    pair (tier-1 results may still have been ingested for that pair
    if any slots were filled before the agent ran).
  - `kind=dry_run` — `--dry-run` payload (asset URLs only). Each
    asset entry includes a `discovery_source` field
    (`"bse" | "nse" | "agent" | null`) and a `fallbacks` list of
    `{url, title, source}` candidates that download-side code would
    try if the primary fails.
  - `kind=ingest_outcome` — full `IngestOutcome` JSON (one per
    `(Company, PeriodSpec)` pair). Each `assets[]` entry carries
    `discovery_source`.
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
- [ ] `--no-agent-fallback` does NOT require `OPENAI_API_KEY` to be set
      (the agent path is never taken).
- [ ] `--agent-only` skips every BSE/NSE HTTP call; the JSONL rows
      have `discovery_source` set to `"agent"` (or null) for every
      asset, never `"bse"` / `"nse"`.
- [ ] `--no-agent-fallback --agent-only` exits with code 2 (mutually
      exclusive).
- [ ] Each `assets[]` entry in `kind=ingest_outcome` rows has
      `discovery_source` set to one of `"bse" | "nse" | "agent"`.
- [ ] When BSE's primary URL is rejected at download time (HTML
      wrapper, oversized, network error), the run still ingests the
      slot if any fallback (NSE same-type filing or agent URL) is
      downloadable, and the recorded `discovery_source` is the one
      that actually downloaded.
