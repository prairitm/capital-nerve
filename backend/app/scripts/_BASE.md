# `backend/app/scripts/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

## Purpose

One-shot maintenance / batch-job entry points run as
``python -m app.scripts.<name>``. Scripts are not imported by the API
process at request time; they exist for ops, seeding extras, and bulk
backfills.

## Inventory

- [`reindex_documents.py`](reindex_documents.py) — backfill FTS / vectors
  for every existing `SourceDocument`.
- [`export_signals_full.py`](export_signals_full.py) — render the seed
  catalog into `seed_catalog_dump/signals_full.csv`.
- [`bulk_ingest.py`](bulk_ingest.COMPONENT.md) — bulk IR-discovery
  ingestion driven by [`services/ir_discovery/`](../services/ir_discovery/_BASE.md).
- [`reprocess_metrics.py`](reprocess_metrics.COMPONENT.md) — replay
  stages 2-5 of the pipeline (normalize → metrics → signals → cards)
  over persisted `extracted_values` after the unit-rescale / sanity-bounds
  changes in Phase 1A of the analyst-trust overhaul.
- [`seed_nifty50_companies.py`](seed_nifty50_companies.COMPONENT.md) —
  bulk-create `Company` + NSE `Security` rows from
  `var/nse_nifty50.json`.

## Cross-cutting rules

- Scripts open their own `SessionLocal()` instances. They MUST close
  them on exit.
- Scripts NEVER import from `app.routers.*` or instantiate FastAPI; they
  are CLI tools and should run without a live API server.
- Scripts log via the standard `logging` module configured at startup;
  they never use `print` for status output (Typer-based CLIs may use
  `typer.echo` for human-facing summaries).
- Long-running scripts emit per-step progress so an operator can tell
  they're not hung.
- Each script has a colocated `*.COMPONENT.md` describing the CLI
  surface.
