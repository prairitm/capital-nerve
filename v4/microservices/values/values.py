"""FastAPI service for financial_result_flow.ipynb Step 4 / 7.

Run from this directory:
    uvicorn values:app --host 127.0.0.1 --port 8023 --reload
"""

from __future__ import annotations

import logging
from threading import Lock
import time
from typing import Any
from uuid import uuid4

import requests
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from values_client import download_pdf
from values_config import settings
from values_db import get_conn
from values_models import (
    ExtractedValueResponse,
    ExtractValuesJobStartResponse,
    ExtractValuesJobStatusResponse,
    ExtractValuesRequest,
    ExtractValuesResponse,
    ReportingPeriodResponse,
)
from values_service import extract_and_persist_values

app = FastAPI(title="CapitalNerve Values Step Service")
logger = logging.getLogger("uvicorn.error")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {"ok": True, "db_path": str(settings.db_path)}


def _build_payload(
    symbol: str = Query(..., min_length=1),
    from_date: str = Query(...),
    to_date: str = Query(...),
    company_id: str = Query(...),
    event_id: str = Query(...),
    pdf_url: str = Query(...),
    force_reparse: bool = Query(default=False),
    parse_max_workers: int | None = Query(default=None, ge=1),
    extraction_max_workers: int | None = Query(default=None, ge=1),
) -> ExtractValuesRequest:
    return ExtractValuesRequest(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        company_id=company_id,
        event_id=event_id,
        pdf_url=pdf_url,
        force_reparse=force_reparse,
        parse_max_workers=parse_max_workers,
        extraction_max_workers=extraction_max_workers,
    )


def _extract_values_payload(payload: ExtractValuesRequest, *, route_name: str) -> ExtractValuesResponse:
    try:
        started = time.monotonic()
        logger.info(
            "Received %s symbol=%s event_id=%s force_reparse=%s",
            route_name,
            payload.symbol,
            payload.event_id,
            payload.force_reparse,
        )
        pdf_bytes = download_pdf(payload.pdf_url)
        logger.info(
            "Downloaded values PDF: %s bytes in %.1fs",
            len(pdf_bytes),
            time.monotonic() - started,
        )
        with get_conn() as conn:
            result = extract_and_persist_values(
                conn,
                symbol=payload.symbol,
                company_id=payload.company_id,
                event_id=payload.event_id,
                pdf_url=payload.pdf_url,
                pdf_bytes=pdf_bytes,
                force_reparse=payload.force_reparse,
                parse_max_workers=payload.parse_max_workers,
                extraction_max_workers=payload.extraction_max_workers,
            )
        logger.info(
            "Completed %s symbol=%s event_id=%s in %.1fs",
            route_name,
            payload.symbol,
            payload.event_id,
            time.monotonic() - started,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"PDF download failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    reporting_period = result["reporting_period"]
    next_service_params = {
        "symbol": payload.symbol,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "company_id": payload.company_id,
        "event_id": payload.event_id,
        "pdf_url": payload.pdf_url,
        "document_id": result["document_id"],
        "period_quarter": reporting_period["quarter"],
        "period_fy_start": reporting_period["fy_start_year"],
        "period_end": reporting_period["quarter_end"],
        "period_label": reporting_period["label"],
    }

    return ExtractValuesResponse(
        db_path=str(settings.db_path),
        symbol=payload.symbol,
        from_date=payload.from_date,
        to_date=payload.to_date,
        company_id=payload.company_id,
        event_id=payload.event_id,
        pdf_url=payload.pdf_url,
        document_id=result["document_id"],
        storage_path=result["storage_path"],
        markdown_length=result["markdown_length"],
        reporting_period=ReportingPeriodResponse(**reporting_period),
        extracted_count=len(result["values"]),
        values=[ExtractedValueResponse(**row) for row in result["values"]],
        next_service_params=next_service_params,
    )


@app.post("/values/extract", response_model=ExtractValuesResponse)
def extract_values(payload: ExtractValuesRequest = Depends(_build_payload)) -> ExtractValuesResponse:
    return _extract_values_payload(payload, route_name="/values/extract")


def _set_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        job = _jobs.setdefault(job_id, {"job_id": job_id})
        job.update(updates)


def _run_extract_values_job(job_id: str, payload: ExtractValuesRequest) -> None:
    _set_job(job_id, status="running")
    try:
        result = _extract_values_payload(payload, route_name=f"/values/extract/jobs/{job_id}")
    except HTTPException as exc:
        _set_job(job_id, status="failed", error=str(exc.detail))
    except Exception as exc:
        logger.exception("Values extraction job %s failed", job_id)
        _set_job(job_id, status="failed", error=str(exc))
    else:
        _set_job(job_id, status="succeeded", result=result)


@app.post("/values/extract/jobs", response_model=ExtractValuesJobStartResponse)
def start_extract_values_job(
    background_tasks: BackgroundTasks,
    payload: ExtractValuesRequest = Depends(_build_payload),
) -> ExtractValuesJobStartResponse:
    job_id = uuid4().hex
    _set_job(job_id, status="queued", result=None, error=None)
    background_tasks.add_task(_run_extract_values_job, job_id, payload)
    logger.info("Queued values extraction job %s for %s", job_id, payload.symbol)
    return ExtractValuesJobStartResponse(
        job_id=job_id,
        status="queued",
        status_url=f"/values/extract/jobs/{job_id}",
    )


@app.get("/values/extract/jobs/{job_id}", response_model=ExtractValuesJobStatusResponse)
def get_extract_values_job(job_id: str) -> ExtractValuesJobStatusResponse:
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        raise HTTPException(status_code=404, detail="values extraction job not found")
    return ExtractValuesJobStatusResponse(**job)


if __name__ == "__main__":
    uvicorn.run("values:app", host="127.0.0.1", port=8023, reload=True)
