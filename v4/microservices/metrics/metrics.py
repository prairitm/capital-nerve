"""FastAPI service for financial_result_flow.ipynb Step 5 / 7.

Run from this directory:
    uvicorn metrics:app --host 127.0.0.1 --port 8024 --reload
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from metrics_config import settings
from metrics_db import get_conn
from metrics_models import (
    ComputeMetricsRequest,
    ComputeMetricsResponse,
    MetricValueResponse,
    ScopeCountsResponse,
)
from metrics_service import compute_and_persist_metrics

app = FastAPI(title="CapitalNerve Metrics Step Service")

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


@app.post("/metrics/compute", response_model=ComputeMetricsResponse)
def compute_metrics_endpoint(
    symbol: str = Query(..., min_length=1),
    from_date: str = Query(...),
    to_date: str = Query(...),
    company_id: str = Query(...),
    event_id: str = Query(...),
    event_type: str = Query(default="Financial Results"),
    pdf_url: str | None = Query(default=None),
    document_id: str | None = Query(default=None),
    period_quarter: int = Query(..., ge=1, le=4),
    period_fy_start: int = Query(...),
    period_end: str = Query(...),
    period_label: str | None = Query(default=None),
) -> ComputeMetricsResponse:
    payload = ComputeMetricsRequest(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        company_id=company_id,
        event_id=event_id,
        event_type=event_type,
        pdf_url=pdf_url,
        document_id=document_id,
        period_quarter=period_quarter,
        period_fy_start=period_fy_start,
        period_end=period_end,
        period_label=period_label,
    )

    try:
        with get_conn() as conn:
            result = compute_and_persist_metrics(
                conn,
                symbol=payload.symbol,
                company_id=payload.company_id,
                event_id=payload.event_id,
                event_type=payload.event_type,
                period_quarter=payload.period_quarter,
                period_fy_start=payload.period_fy_start,
                period_end=payload.period_end,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    next_service_params = {
        "symbol": payload.symbol,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "company_id": payload.company_id,
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "pdf_url": payload.pdf_url,
        "document_id": payload.document_id,
        "period_quarter": payload.period_quarter,
        "period_fy_start": payload.period_fy_start,
        "period_end": payload.period_end,
        "period_label": payload.period_label,
        "metrics_count": len(result["metrics"]),
    }

    return ComputeMetricsResponse(
        db_path=str(settings.db_path),
        symbol=payload.symbol,
        from_date=payload.from_date,
        to_date=payload.to_date,
        company_id=payload.company_id,
        event_id=payload.event_id,
        event_type=payload.event_type,
        pdf_url=payload.pdf_url,
        document_id=payload.document_id,
        period_quarter=payload.period_quarter,
        period_fy_start=payload.period_fy_start,
        period_end=payload.period_end,
        period_label=payload.period_label,
        metrics_count=len(result["metrics"]),
        scope_counts=ScopeCountsResponse(**result["scope_counts"]),
        metrics=[MetricValueResponse(**metric) for metric in result["metrics"]],
        next_service_params=next_service_params,
    )


if __name__ == "__main__":
    uvicorn.run("metrics:app", host="127.0.0.1", port=8024, reload=True)
