"""FastAPI service for financial_result_flow.ipynb Step 4 / 7.

Run from this directory:
    uvicorn values:app --host 127.0.0.1 --port 8023 --reload
"""

from __future__ import annotations

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from values_client import download_pdf
from values_config import settings
from values_db import get_conn
from values_models import (
    ExtractedValueResponse,
    ExtractValuesRequest,
    ExtractValuesResponse,
    ReportingPeriodResponse,
)
from values_service import extract_and_persist_values

app = FastAPI(title="CapitalNerve Values Step Service")

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


@app.post("/values/extract", response_model=ExtractValuesResponse)
def extract_values(
    symbol: str = Query(..., min_length=1),
    from_date: str = Query(...),
    to_date: str = Query(...),
    company_id: str = Query(...),
    event_id: str = Query(...),
    pdf_url: str = Query(...),
    force_reparse: bool = Query(default=False),
) -> ExtractValuesResponse:
    payload = ExtractValuesRequest(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        company_id=company_id,
        event_id=event_id,
        pdf_url=pdf_url,
        force_reparse=force_reparse,
    )

    try:
        pdf_bytes = download_pdf(payload.pdf_url)
        with get_conn() as conn:
            result = extract_and_persist_values(
                conn,
                symbol=payload.symbol,
                company_id=payload.company_id,
                event_id=payload.event_id,
                pdf_url=payload.pdf_url,
                pdf_bytes=pdf_bytes,
                force_reparse=payload.force_reparse,
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


if __name__ == "__main__":
    uvicorn.run("values:app", host="127.0.0.1", port=8023, reload=True)
