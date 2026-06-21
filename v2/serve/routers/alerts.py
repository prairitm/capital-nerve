"""Alerts router — derived from recent watch-level signals."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import ids, mapper
from ..builder import Catalog
from ..deps import catalog_dep, get_current_user
from ..state import User, store

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def list_alerts(
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict]:
    alerts: list[dict] = []
    for built in catalog.all_built():
        signal = catalog.primary_signal(built)
        if not signal or signal.get("severity") != "watch":
            continue
        p = built.period
        alert_id = ids.stable_int("alert", p.ticker, p.quarter, p.fy_start_year)
        alerts.append(
            {
                "alert_id": alert_id,
                "alert_title": signal["headline"],
                "alert_message": signal["rationale"],
                "severity": mapper._severity(signal["severity"]),
                "is_read": alert_id in store.read_alerts,
                "created_at": built.filing.ingested_at if built.filing else "",
                "company_name": p.ticker.title(),
                "company_symbol": p.ticker,
                "event_id": ids.event_id(p.ticker, p.quarter, p.fy_start_year),
                "card_id": ids.object_id(p.ticker, p.quarter, p.fy_start_year, "result_verdict"),
            }
        )
    alerts.sort(key=lambda a: a["created_at"], reverse=True)
    return alerts


@router.patch("/{alert_id}/read")
def mark_read(alert_id: int, user: User = Depends(get_current_user)) -> dict:
    store.read_alerts.add(alert_id)
    return {"ok": True, "alert_id": alert_id}
