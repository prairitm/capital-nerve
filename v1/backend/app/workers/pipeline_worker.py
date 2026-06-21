"""Polling worker that drains the `extraction_jobs` queue.

The worker stays intentionally simple: claim one PENDING row at a time via
`SELECT ... FOR UPDATE SKIP LOCKED`, run the pipeline, commit, repeat. Two
workers can run side-by-side safely because of the row-lock.

It can be driven two ways:

- **In-process** (default for `dev`): started from FastAPI's lifespan hook so a
  single `uvicorn` process gets ingestion for free.
- **Standalone**: `python -m app.workers.run`, suitable for prod where the API
  process should stay lean and workers scale independently.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.enums import ExtractionStatus
from app.db.session import SessionLocal
from app.models.events import ExtractionJob
from app.services.pipeline.runner import run_pipeline_for_document

logger = logging.getLogger(__name__)


def _reset_orphaned_claims(db: Session) -> int:
    """PROCESSING rows never started are worker-crash orphans — put them back on the queue."""
    now = datetime.now(timezone.utc)
    claim_cutoff = now - timedelta(seconds=settings.WORKER_STALE_CLAIM_SECONDS)
    result = db.execute(
        update(ExtractionJob)
        .where(
            ExtractionJob.status == ExtractionStatus.PROCESSING,
            ExtractionJob.started_at.is_(None),
            ExtractionJob.completed_at.is_(None),
            ExtractionJob.created_at < claim_cutoff,
        )
        .values(status=ExtractionStatus.PENDING)
        .returning(ExtractionJob.extraction_job_id)
    )
    reset_ids = list(result.scalars().all())
    if reset_ids:
        db.commit()
        logger.info("Reset %s orphaned PROCESSING job(s) to PENDING: %s", len(reset_ids), reset_ids)
    return len(reset_ids)


@contextmanager
def _claim_one_job(db: Session) -> Iterator[ExtractionJob | None]:
    """Lock and claim a single PENDING job inside one transaction.

    Also reclaims hung PROCESSING rows (pipeline started but never finished).
    Orphaned claims (PROCESSING, no `started_at`) are reset to PENDING first so
    only one worker runs the pipeline. Returns `None` if the queue is empty.
    """
    _reset_orphaned_claims(db)

    now = datetime.now(timezone.utc)
    run_cutoff = now - timedelta(seconds=settings.WORKER_STALE_RUN_SECONDS)
    hung_stmt = (
        select(ExtractionJob)
        .where(
            ExtractionJob.status == ExtractionStatus.PROCESSING,
            ExtractionJob.completed_at.is_(None),
            ExtractionJob.started_at.isnot(None),
            ExtractionJob.started_at < run_cutoff,
        )
        .order_by(ExtractionJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    hung = db.execute(hung_stmt).scalar_one_or_none()
    if hung:
        logger.info("Reclaiming hung PROCESSING job %s", hung.extraction_job_id)
        db.commit()
        yield hung
        return

    stmt = (
        select(ExtractionJob)
        .where(ExtractionJob.status == ExtractionStatus.PENDING)
        .order_by(ExtractionJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = db.execute(stmt).scalar_one_or_none()
    if not job:
        yield None
        return
    # Flip to PROCESSING under the lock so the next worker poll won't try to
    # claim the same row. Commit immediately to release the row-lock; the real
    # pipeline runner opens its own transactions per stage.
    job.status = ExtractionStatus.PROCESSING
    db.commit()
    yield job


def drain_once() -> int:
    """Process up to one job. Returns 1 if a job was processed, 0 otherwise."""
    db = SessionLocal()
    try:
        with _claim_one_job(db) as job:
            if job is None:
                return 0
            job_id = job.extraction_job_id
        # Use a fresh session for the pipeline so the row-claim transaction
        # doesn't linger.
        pipeline_db = SessionLocal()
        try:
            summary = run_pipeline_for_document(pipeline_db, job_id=job_id)
            logger.info(
                "Pipeline finished: job=%s status=%s cards=%s published=%s",
                summary.job_id,
                summary.status.value,
                summary.cards,
                summary.published,
            )
        finally:
            pipeline_db.close()
        return 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Loop drivers
# ---------------------------------------------------------------------------


_stop_event = threading.Event()


def request_stop() -> None:
    _stop_event.set()


def reset_stop() -> None:
    _stop_event.clear()


def run_forever_sync(poll_interval_seconds: float | None = None) -> None:
    """Blocking loop; used by `python -m app.workers.run`."""
    interval = poll_interval_seconds or settings.WORKER_POLL_INTERVAL_SECONDS

    def _handle(sig, frame):  # noqa: ANN001 — signal API shape
        logger.info("Worker received signal %s; shutting down", sig)
        request_stop()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    logger.info("Pipeline worker started (poll=%.1fs)", interval)
    while not _stop_event.is_set():
        try:
            processed = drain_once()
        except Exception:
            logger.exception("Worker loop error — continuing")
            processed = 0
        if processed == 0:
            _stop_event.wait(interval)
    logger.info("Pipeline worker stopped")


async def run_forever_async(poll_interval_seconds: float | None = None) -> None:
    """Async loop used by the FastAPI lifespan hook.

    Runs `drain_once` in a thread so DB calls don't block the event loop.
    """
    interval = poll_interval_seconds or settings.WORKER_POLL_INTERVAL_SECONDS
    logger.info("In-process pipeline worker started (poll=%.1fs)", interval)
    try:
        while not _stop_event.is_set():
            try:
                processed = await asyncio.to_thread(drain_once)
            except Exception:
                logger.exception("Async worker iteration failed — continuing")
                processed = 0
            if processed == 0:
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
    finally:
        logger.info("In-process pipeline worker exiting")
