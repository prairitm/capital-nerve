"""v4 read-only API over the 7-step SQLite DB.

Run: uvicorn main:app --port 8010 --reload
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import companies, documents, events, feed, signals

app = FastAPI(title="CapitalNerve v4 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(events.router)
app.include_router(signals.router)
app.include_router(feed.router)
app.include_router(documents.router)


@app.get("/health")
def health():
    return {"ok": settings.db_path.exists(), "db_path": str(settings.db_path)}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8010, reload=True)
