"""Watchlist router — per-user company set kept in memory."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import ids, mapper
from ..builder import Catalog
from ..deps import catalog_dep, get_current_user
from ..schemas import WatchlistCompanyRequest
from ..state import User

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def get_watchlist(
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict:
    companies = []
    new_events = negative = positive = red_flags = 0
    for ticker in catalog.tickers():
        if ids.company_id(ticker) not in user.watchlist_company_ids:
            continue
        builts = catalog.built_for_ticker(ticker)
        latest = builts[-1] if builts else None
        signal = catalog.primary_signal(latest) if latest else None
        direction = mapper._direction(signal["signal_key"]) if signal else None
        severity = mapper._severity(signal["severity"]) if signal else None
        if direction == "NEGATIVE":
            negative += 1
        elif direction == "POSITIVE":
            positive += 1
        if signal and signal.get("severity") == "watch":
            red_flags += 1
        companies.append(
            {
                "company": mapper.company_brief(catalog, ticker),
                "latest_signal": direction,
                "latest_card_type": "result_verdict" if latest else None,
                "latest_card_headline": signal["headline"] if signal else None,
                "watch_next": "Track the next quarter for confirmation." if latest else None,
                "severity": severity,
            }
        )
    return {
        "watchlist_id": user.user_id,
        "name": "Default Watchlist",
        "summary": {
            "tracked": len(companies),
            "new_events": new_events,
            "negative_signals": negative,
            "positive_signals": positive,
            "red_flags": red_flags,
        },
        "companies": companies,
    }


@router.post("/companies")
def add_company(
    body: WatchlistCompanyRequest,
    user: User = Depends(get_current_user),
) -> dict:
    user.watchlist_company_ids.add(body.company_id)
    return {"ok": True, "company_id": body.company_id}


@router.delete("/companies/{company_id}")
def remove_company(
    company_id: int,
    user: User = Depends(get_current_user),
) -> dict:
    user.watchlist_company_ids.discard(company_id)
    return {"ok": True, "company_id": company_id}
