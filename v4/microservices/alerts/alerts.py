"""FastAPI service for financial_result_flow.ipynb Step 7 / 7.

Run from this directory:
    uvicorn alerts:app --host 127.0.0.1 --port 8026 --reload
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from alerts_config import settings
from alerts_db import get_conn
from alerts_models import (
    AlertResponse,
    DbSummaryResponse,
    PresentAlertsRequest,
    PresentAlertsResponse,
)
from alerts_service import present_alerts

app = FastAPI(title="CapitalNerve Alerts Step Service")

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


@app.get("/alerts", response_model=PresentAlertsResponse)
def present_alerts_endpoint(
    symbol: str = Query(..., min_length=1),
    from_date: str = Query(...),
    to_date: str = Query(...),
    company_id: str = Query(...),
    event_id: str = Query(...),
    pdf_url: str | None = Query(default=None),
    document_id: str | None = Query(default=None),
    period_quarter: int = Query(..., ge=1, le=4),
    period_fy_start: int = Query(...),
    period_end: str = Query(...),
    period_label: str | None = Query(default=None),
    metrics_count: int | None = Query(default=None),
    signals_count: int | None = Query(default=None),
) -> PresentAlertsResponse:
    payload = PresentAlertsRequest(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        company_id=company_id,
        event_id=event_id,
        pdf_url=pdf_url,
        document_id=document_id,
        period_quarter=period_quarter,
        period_fy_start=period_fy_start,
        period_end=period_end,
        period_label=period_label,
        metrics_count=metrics_count,
        signals_count=signals_count,
    )

    try:
        with get_conn() as conn:
            result = present_alerts(
                conn,
                symbol=payload.symbol,
                company_id=payload.company_id,
                event_id=payload.event_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    next_service_params = {
        "symbol": payload.symbol,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "company_id": payload.company_id,
        "event_id": payload.event_id,
        "pdf_url": payload.pdf_url,
        "document_id": payload.document_id,
        "period_quarter": payload.period_quarter,
        "period_fy_start": payload.period_fy_start,
        "period_end": payload.period_end,
        "period_label": payload.period_label,
        "metrics_count": payload.metrics_count,
        "signals_count": payload.signals_count,
        "alert_count": len(result["alerts"]),
    }

    return PresentAlertsResponse(
        db_path=str(settings.db_path),
        symbol=payload.symbol,
        from_date=payload.from_date,
        to_date=payload.to_date,
        company_id=payload.company_id,
        event_id=payload.event_id,
        pdf_url=payload.pdf_url,
        document_id=payload.document_id,
        period_quarter=payload.period_quarter,
        period_fy_start=payload.period_fy_start,
        period_end=payload.period_end,
        period_label=payload.period_label,
        metrics_count=payload.metrics_count,
        signals_count=payload.signals_count,
        alert_count=len(result["alerts"]),
        alerts=[AlertResponse(**alert) for alert in result["alerts"]],
        db_summary=DbSummaryResponse(**result["counts"]),
        message=result["message"],
        next_service_params=next_service_params,
    )


if __name__ == "__main__":
    uvicorn.run("alerts:app", host="127.0.0.1", port=8026, reload=True)
