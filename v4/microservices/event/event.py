"""FastAPI service for financial_result_flow.ipynb Step 2 / 7.

Run from this directory:
    uvicorn event:app --host 127.0.0.1 --port 8021 --reload
"""

from __future__ import annotations

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from event_client import fetch_corporate_announcements
from event_config import settings
from event_db import get_conn
from event_models import DiscoverEventsRequest, DiscoverEventsResponse, EventResponse
from event_service import company_id_for_symbol, persist_announcements

app = FastAPI(title="CapitalNerve Event Step Service")

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


@app.post("/events/discover", response_model=DiscoverEventsResponse)
def discover_events(
    symbol: str = Query(..., min_length=1),
    from_date: str = Query(...),
    to_date: str = Query(...),
    company_id: str | None = Query(default=None),
) -> DiscoverEventsResponse:
    payload = DiscoverEventsRequest(
        symbol=symbol,
        from_date=from_date,
        to_date=to_date,
        company_id=company_id,
    )
    persist_company_id = payload.company_id or company_id_for_symbol(payload.symbol)
    if payload.company_id is not None:
        derived_company_id = company_id_for_symbol(payload.symbol)
        if payload.company_id != derived_company_id:
            raise HTTPException(
                status_code=422,
                detail="company_id does not match the NSE symbol-derived company id",
            )

    try:
        announcements = fetch_corporate_announcements(
            payload.symbol,
            payload.from_date,
            payload.to_date,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"NSE request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    with get_conn() as conn:
        result = persist_announcements(
            conn,
            payload.symbol,
            announcements,
            company_id=persist_company_id,
        )

    next_service_params = {
        "symbol": payload.symbol,
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "company_id": result["company_id"],
    }

    return DiscoverEventsResponse(
        db_path=str(settings.db_path),
        company_id=result["company_id"],
        symbol=payload.symbol,
        from_date=payload.from_date,
        to_date=payload.to_date,
        next_service_params=next_service_params,
        announcements_count=result["announcements_count"],
        stored_count=result["stored_count"],
        desc_buckets=result["desc_buckets"],
        events=[EventResponse(**event) for event in result["events"]],
        first_announcement=result["first_announcement"],
    )


if __name__ == "__main__":
    uvicorn.run("event:app", host="127.0.0.1", port=8021, reload=True)
