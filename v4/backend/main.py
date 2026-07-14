"""v4 read-only API over the 7-step SQLite DB.

Run: uvicorn main:app --port 8010 --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_db import migrate_app_db
from config import settings
from routers import admin, auth, companies, documents, events, feed, signals, watchlist
from security import bootstrap_admin, require_ready_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_app_db()
    bootstrap_admin()
    yield


app = FastAPI(title="CapitalNerve v4 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

protected = [Depends(require_ready_user)]
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(watchlist.router)
app.include_router(companies.router, dependencies=protected)
app.include_router(events.router, dependencies=protected)
app.include_router(signals.router, dependencies=protected)
app.include_router(feed.router, dependencies=protected)
app.include_router(documents.router, dependencies=protected)


@app.get("/health")
def health():
    return {
        "ok": settings.db_path.exists() and settings.app_db_path.exists(),
        "analytics_db": settings.db_path.exists(),
        "app_db": settings.app_db_path.exists(),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8010, reload=True)
