# workers/run

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

CLI entry point — `python -m app.workers.run` — for running the pipeline
worker as a standalone process (Docker container, systemd unit, etc.).

## Source

- Path: `backend/app/workers/run.py`
- Layer: backend-worker

## Contract

- `main()` — configures logging, calls
  [`pipeline_worker.run_forever_sync()`](pipeline_worker.py), blocks until
  signalled.

## Dependencies

- May import: `logging`, `app.workers.pipeline_worker`.
- Must not import: routers, FastAPI app, frontend types.

## Patterns (symmetry)

- Logging format mirrors `uvicorn`'s default so the two processes look
  consistent in tail / journalctl output.
- No CLI args yet; future env-driven flags should land here (and update this
  doc) — keep `run.py` argument-free for now so deployment recipes stay simple.

## Verification checklist

- [ ] `python -m app.workers.run` starts and prints the "started" log line.
- [ ] `SIGINT` / `SIGTERM` cleanly stops the loop within one poll interval.
- [ ] Runs against the same `DATABASE_URL` the API uses (single source of truth).
