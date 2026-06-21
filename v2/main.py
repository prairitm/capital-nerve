"""Capital Nerve v2 serving layer.

A FastAPI app that serves the `v1/frontend` React UI from the v2 SQLite store
(`capital_nerve.db`). It builds intelligence payloads on demand from the stored
metrics and exposes the full v1 HTTP surface the frontend expects.

Run it from the `v2/` directory:

    uvicorn main:app --reload --port 8000

Then start the UI separately:

    cd ../v1/frontend && npm run dev

The Vite dev server proxies `/api/*` to this app on port 8000.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from serve.config import settings
from serve.routers import (
    admin,
    alerts,
    auth,
    documents,
    ingest,
    review,
    search,
    v1,
    watch_items,
    watchlist,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="CapitalNerve v2 Serving API",
        version="0.1.0",
        description="Serving layer over the v2 SQLite store for the v1 frontend.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(v1.router)
    app.include_router(watchlist.router)
    app.include_router(watch_items.router)
    app.include_router(alerts.router)
    app.include_router(search.router)
    app.include_router(documents.router)
    app.include_router(ingest.router)
    app.include_router(admin.router)
    app.include_router(review.router)

    return app


app = create_app()
