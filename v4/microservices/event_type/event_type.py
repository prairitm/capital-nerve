"""FastAPI service for financial_result_flow.ipynb Step 3 / 7.

Run from this directory:
    uvicorn event_type:app --host 127.0.0.1 --port 8022 --reload
"""

from __future__ import annotations

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from event_type_client import create_nse_session, fetch_corporate_announcements
from event_type_config import settings
from event_type_db import get_conn
from event_type_models import (
    CandidateResponse,
    DocumentRequest,
    ResolveEventTypeRequest,
    ResolveEventTypeResponse,
    ResolvedDocumentResponse,
)
from event_type_service import resolve_event_type

app = FastAPI(title="CapitalNerve Event Type Step Service")

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


@app.post("/event-type/resolve", response_model=ResolveEventTypeResponse)
def resolve_financial_result_event_type(
    symbol: str = Query(..., min_length=1),
    from_date: str = Query(...),
    to_date: str = Query(...),
    company_id: str = Query(...),
    event_type: str = Query(default="Financial Results"),
    documents_json: str | None = Query(default=None),
) -> ResolveEventTypeResponse:
    payload = ResolveEventTypeRequest(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        company_id=company_id,
        event_type=event_type,
        documents=documents_json,
    )

    try:
        session = create_nse_session()
        announcements = fetch_corporate_announcements(
            session,
            payload.symbol,
            payload.from_date,
            payload.to_date,
        )
        with get_conn() as conn:
            result = resolve_event_type(
                conn,
                session=session,
                symbol=payload.symbol,
                from_date=payload.from_date,
                to_date=payload.to_date,
                company_id=payload.company_id,
                announcements=announcements,
                event_type=payload.event_type,
                documents=[
                    document.dict(exclude_none=True)
                    for document in (payload.documents or [])
                ] or None,
            )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"NSE request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    next_service_params = {
        "symbol": payload.symbol,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "company_id": payload.company_id,
        "event_id": result["event_id"],
        "event_type": payload.event_type,
        "pdf_url": result["chosen_source_url"],
        "resolved_documents": result.get("resolved_documents") or [],
    }

    return ResolveEventTypeResponse(
        db_path=str(settings.db_path),
        symbol=payload.symbol,
        from_date=payload.from_date,
        to_date=payload.to_date,
        company_id=payload.company_id,
        event_type=payload.event_type,
        event_id=result["event_id"],
        chosen_source_url=result["chosen_source_url"],
        chosen_title=result["chosen_title"],
        chosen_sort_date=result["chosen_sort_date"],
        announcements_count=result["announcements_count"],
        financial_results_count=result["financial_results_count"],
        period_markers=result["period_markers"],
        classification=result["classification"],
        recovery_needed=result["recovery_needed"],
        rejected_url=result["rejected_url"],
        candidates=[CandidateResponse(**item) for item in result["candidates"]],
        resolved_documents=[
            ResolvedDocumentResponse(**item)
            for item in (result.get("resolved_documents") or [])
        ],
        next_service_params=next_service_params,
    )


if __name__ == "__main__":
    uvicorn.run("event_type:app", host="127.0.0.1", port=8022, reload=True)
