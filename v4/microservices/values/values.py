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
    event_id: str | None = Query(default=None),
    pdf_url: str | None = Query(default=None),
    event_type: str = Query(default="Financial Results"),
    document_type: str | None = Query(default=None),
    local_path: str | None = Query(default=None),
    resolved_documents_json: str | None = Query(default=None),
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
        event_type=event_type,
        document_type=document_type,
        local_path=local_path,
        resolved_documents=resolved_documents_json,
        force_reparse=force_reparse,
        parse_max_workers=parse_max_workers,
        extraction_max_workers=extraction_max_workers,
    )


def _payload_documents(payload: ExtractValuesRequest) -> list[dict[str, Any]]:
    if payload.resolved_documents:
        return [document.dict(exclude_none=True) for document in payload.resolved_documents]
    return [
        {
            "document_type": payload.document_type,
            "event_type": payload.event_type,
            "event_id": payload.event_id,
            "source_url": payload.pdf_url,
            "local_path": payload.local_path,
        }
    ]


def _document_bytes(document: dict[str, Any]) -> bytes:
    local_path = document.get("local_path")
    if local_path:
        with open(local_path, "rb") as handle:
            return handle.read()
    source_url = document.get("source_url")
    if not source_url:
        raise ValueError("resolved document requires source_url or local_path")
    return download_pdf(source_url)


def _extract_values_payload(
    payload: ExtractValuesRequest,
    *,
    route_name: str,
    progress_callback: Any | None = None,
) -> ExtractValuesResponse:
    def progress(phase: str, message: str, **extra: Any) -> None:
        update = {
            "phase": phase,
            "message": message,
            "route": route_name,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            **extra,
        }
        logger.info(
            "VALUES route progress phase=%s elapsed=%.1fs %s",
            phase,
            update["elapsed_seconds"],
            message,
        )
        if progress_callback is not None:
            progress_callback(update)

    try:
        started = time.monotonic()
        logger.info(
            "Received %s symbol=%s event_id=%s force_reparse=%s",
            route_name,
            payload.symbol,
            payload.event_id,
            payload.force_reparse,
        )
        documents = _payload_documents(payload)
        progress(
            "queued_documents",
            "Prepared Step 4 document queue",
            symbol=payload.symbol,
            document_count=len(documents),
            event_ids=[document.get("event_id") for document in documents],
            document_types=[document.get("document_type") for document in documents],
        )
        document_results: list[dict[str, Any]] = []
        with get_conn() as conn:
            for index, document in enumerate(documents, start=1):
                progress(
                    "load_document",
                    f"Loading document {index}/{len(documents)}",
                    document_index=index,
                    document_count=len(documents),
                    event_id=document.get("event_id"),
                    document_type=document.get("document_type"),
                    source_url=document.get("source_url"),
                    local_path=document.get("local_path"),
                )
                load_started = time.monotonic()
                pdf_bytes = _document_bytes(document)
                logger.info(
                    "Loaded values document %s: %s bytes in %.1fs",
                    document.get("document_type"),
                    len(pdf_bytes),
                    time.monotonic() - started,
                )
                progress(
                    "document_loaded",
                    f"Loaded document {index}/{len(documents)}",
                    document_index=index,
                    document_count=len(documents),
                    bytes=len(pdf_bytes),
                    load_elapsed_seconds=round(time.monotonic() - load_started, 1),
                )
                progress(
                    "extract_document",
                    f"Starting extraction for document {index}/{len(documents)}",
                    document_index=index,
                    document_count=len(documents),
                    event_id=document.get("event_id"),
                    document_type=document.get("document_type"),
                )
                result = extract_and_persist_values(
                    conn,
                    symbol=payload.symbol,
                    company_id=payload.company_id,
                    event_id=document["event_id"],
                    pdf_url=document.get("source_url"),
                    pdf_bytes=pdf_bytes,
                    event_type=document.get("event_type") or payload.event_type,
                    document_type=document.get("document_type") or payload.document_type,
                    local_path=document.get("local_path"),
                    force_reparse=payload.force_reparse,
                    parse_max_workers=payload.parse_max_workers,
                    extraction_max_workers=payload.extraction_max_workers,
                    progress_callback=progress_callback,
                )
                document_results.append(
                    {
                        **result,
                        "event_id": document["event_id"],
                        "event_type": document.get("event_type") or payload.event_type,
                        "document_type": document.get("document_type") or payload.document_type,
                        "source_url": document.get("source_url"),
                        "local_path": document.get("local_path"),
                    }
                )
                progress(
                    "document_complete",
                    f"Completed document {index}/{len(documents)}",
                    document_index=index,
                    document_count=len(documents),
                    event_id=document.get("event_id"),
                    document_id=result.get("document_id"),
                    extracted_count=len(result.get("values") or []),
                )
        result = document_results[0]
        logger.info(
            "Completed %s symbol=%s event_id=%s in %.1fs",
            route_name,
            payload.symbol,
            payload.event_id,
            time.monotonic() - started,
        )
        progress(
            "complete",
            "Step 4 request completed",
            document_count=len(document_results),
            primary_document_id=result.get("document_id"),
            extracted_count=len(result.get("values") or []),
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
        "event_id": result["event_id"],
        "pdf_url": result.get("source_url"),
        "event_type": result["event_type"],
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
        event_id=result["event_id"],
        pdf_url=result.get("source_url"),
        event_type=result["event_type"],
        document_id=result["document_id"],
        storage_path=result["storage_path"],
        markdown_length=result["markdown_length"],
        reporting_period=ReportingPeriodResponse(**reporting_period),
        extracted_count=len(result["values"]),
        values=[ExtractedValueResponse(**row) for row in result["values"]],
        document_results=document_results,
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
    started = time.monotonic()

    def update_progress(progress: dict[str, Any]) -> None:
        _set_job(
            job_id,
            progress={
                "job_id": job_id,
                "job_elapsed_seconds": round(time.monotonic() - started, 1),
                **progress,
            },
        )

    _set_job(
        job_id,
        status="running",
        progress={
            "job_id": job_id,
            "phase": "running",
            "message": "Values extraction job started",
            "job_elapsed_seconds": 0,
        },
    )
    try:
        result = _extract_values_payload(
            payload,
            route_name=f"/values/extract/jobs/{job_id}",
            progress_callback=update_progress,
        )
    except HTTPException as exc:
        _set_job(
            job_id,
            status="failed",
            error=str(exc.detail),
            progress={
                "job_id": job_id,
                "phase": "failed",
                "message": str(exc.detail),
                "job_elapsed_seconds": round(time.monotonic() - started, 1),
            },
        )
    except Exception as exc:
        logger.exception("Values extraction job %s failed", job_id)
        _set_job(
            job_id,
            status="failed",
            error=str(exc),
            progress={
                "job_id": job_id,
                "phase": "failed",
                "message": str(exc),
                "job_elapsed_seconds": round(time.monotonic() - started, 1),
            },
        )
    else:
        _set_job(
            job_id,
            status="succeeded",
            result=result,
            progress={
                "job_id": job_id,
                "phase": "succeeded",
                "message": "Values extraction job succeeded",
                "job_elapsed_seconds": round(time.monotonic() - started, 1),
                "extracted_count": result.extracted_count,
                "document_id": result.document_id,
            },
        )


@app.post("/values/extract/jobs", response_model=ExtractValuesJobStartResponse)
def start_extract_values_job(
    background_tasks: BackgroundTasks,
    payload: ExtractValuesRequest = Depends(_build_payload),
) -> ExtractValuesJobStartResponse:
    job_id = uuid4().hex
    _set_job(
        job_id,
        status="queued",
        result=None,
        error=None,
        progress={
            "job_id": job_id,
            "phase": "queued",
            "message": "Values extraction job queued",
            "job_elapsed_seconds": 0,
        },
    )
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
