# workers/pipeline_worker

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Drain the `extraction_jobs` queue and run each row through the ingestion
pipeline. Exposes both a sync loop (for the CLI process) and an async loop
(for the FastAPI lifespan).

## Source

- Path: `backend/app/workers/pipeline_worker.py`
- Layer: backend-worker

## Contract

- `drain_once() -> int` — process at most one PENDING job; returns 1 when a
  job was processed, 0 when the queue was empty.
- `run_forever_sync(poll_interval_seconds=None)` — blocking loop with signal
  handlers; used by `python -m app.workers.run`.
- `run_forever_async(poll_interval_seconds=None)` — asyncio loop that runs
  `drain_once` on a thread; used by the FastAPI lifespan hook.
- `request_stop()` / `reset_stop()` — control the shared stop event.

## Dependencies

- May import: `sqlalchemy`, `app.core.config`, `app.db.session`,
  `app.models.events`, `app.services.pipeline.runner`.
- Must not import: routers, schemas, frontend types.

## Patterns (symmetry)

- Job claim uses `SELECT ... FOR UPDATE SKIP LOCKED` then flips status to
  `PROCESSING` and commits immediately — the row-lock is released so the
  pipeline runner can open its own transactions per stage.
- Orphaned `PROCESSING` rows (no `started_at`, older than
  `WORKER_STALE_CLAIM_SECONDS`) are reset to `PENDING` before each poll so a
  uvicorn reload cannot strand the queue. Hung runs (`started_at` set, no
  `completed_at`, older than `WORKER_STALE_RUN_SECONDS`) are reclaimed in place.
- Errors inside `drain_once` are caught at the loop level so one bad job does
  not kill the worker.
- `_stop_event` is checked between iterations so shutdown is bounded by one
  poll interval at worst.

## Verification checklist

- [ ] Stopping the FastAPI process drains within `WORKER_POLL_INTERVAL_SECONDS`.
- [ ] Two parallel `drain_once` calls never produce two pipeline runs for one
      job (skip-locked semantics).
- [ ] `request_stop()` followed by `run_forever_sync()` returns within one
      poll interval.
