# workers/

> Inherits: [../_BASE.md](../_BASE.md)

## Purpose

Background processes that drain queues stored in Postgres. There are no
external brokers (Redis / RabbitMQ) — we lean on `SELECT ... FOR UPDATE SKIP
LOCKED` so multiple worker processes coexist safely.

## File layout

| File | Owns |
|------|------|
| [`pipeline_worker.py`](pipeline_worker.py) | Sync + async loop drivers that drain `extraction_jobs`. |
| [`run.py`](run.py) | CLI entry point — `python -m app.workers.run`. |

## How it runs

- **In-process (dev default).** [`app/main.py`](../main.py) starts
  `run_forever_async` from the FastAPI lifespan when `WORKER_INPROCESS=true`.
  One process, no extra moving parts.
- **Standalone (prod).** Set `WORKER_INPROCESS=false`, run
  `python -m app.workers.run` next to the API process. Scale horizontally —
  the row-lock prevents double-processing.

## Cross-cutting rules

- The worker is the **only** caller of `run_pipeline_for_document` in
  production. UI buttons that want a "re-run" should enqueue a new
  `ExtractionJob` row, not invoke the runner directly.
- Each worker iteration uses a fresh `SessionLocal()` to keep transaction
  boundaries clean.
- Stop signals (`SIGINT`, `SIGTERM`) flip a global `threading.Event` so both
  the sync and async loops drain gracefully without partial commits.

## Verification checklist

- [ ] `_claim_one_job` locks the row before flipping to PROCESSING.
- [ ] Two workers running in parallel never claim the same job.
- [ ] In-process worker shuts down cleanly on FastAPI lifespan exit.
- [ ] No router or schema imports here — workers are server-side only.
