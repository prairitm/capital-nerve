import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import admin, alerts, auth, documents, ingest, review, search, watch_items, watchlist
from app.routers.v1 import (
    companies as v1_companies,
    credit as v1_credit,
    events as v1_events,
    intelligence_objects as v1_intelligence_objects,
    market_data as v1_market_data,
    metrics as v1_metrics,
    peers as v1_peers,
    portfolio as v1_portfolio,
    result_brief as v1_result_brief,
    retail as v1_retail,
    sectors as v1_sectors,
    signals as v1_signals,
)
from app.workers.pipeline_worker import request_stop, reset_stop, run_forever_async

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start (and stop) the in-process pipeline worker when configured.

    When `WORKER_INPROCESS=false`, run `python -m app.workers.run` separately.
    """
    worker_task: asyncio.Task | None = None
    if settings.WORKER_INPROCESS:
        reset_stop()
        worker_task = asyncio.create_task(run_forever_async())
        logger.info("Started in-process pipeline worker")
    try:
        yield
    finally:
        if worker_task is not None:
            request_stop()
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    settings.assert_production_ready()

    app = FastAPI(
        title="CapitalNerve API",
        version="0.1.0",
        description="Indian market intelligence layer — companies, events, signals, cards, evidence.",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(watchlist.router)
    app.include_router(watch_items.router)
    app.include_router(alerts.router)
    app.include_router(search.router)
    app.include_router(documents.router)
    app.include_router(ingest.router)
    app.include_router(review.router)
    app.include_router(admin.router)

    # v1 API — companies, events, signals, intelligence objects, plus
    # portfolio / sector / peer / credit / retail / result-brief wedges.
    app.include_router(v1_companies.router)
    app.include_router(v1_events.router)
    app.include_router(v1_signals.router)
    app.include_router(v1_intelligence_objects.router)
    app.include_router(v1_portfolio.router)
    app.include_router(v1_sectors.router)
    app.include_router(v1_peers.router)
    app.include_router(v1_credit.router)
    app.include_router(v1_retail.router)
    app.include_router(v1_result_brief.router)
    app.include_router(v1_market_data.router)
    app.include_router(v1_metrics.router)

    return app


app = create_app()
