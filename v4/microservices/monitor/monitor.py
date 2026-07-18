from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .monitor_config import settings
from .monitor_service import MonitorRuntime


runtime = MonitorRuntime(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    runtime.start()
    try:
        yield
    finally:
        runtime.stop()


app = FastAPI(title="CapitalNerve Watchlist Filing Monitor", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return runtime.health()
