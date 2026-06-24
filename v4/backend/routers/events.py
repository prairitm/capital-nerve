"""Event detail endpoint over the 7-step DB."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db import get_conn
from queries import build_snapshot, event_facts, event_metrics, event_signals
from serializers import company_dict, event_dict

router = APIRouter(tags=["events"])


@router.get("/events/{event_id}")
def event_detail(event_id: str):
    with get_conn() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (event["company_id"],)
        ).fetchone()

        facts = event_facts(conn, event_id)
        metrics = event_metrics(conn, event_id)
        signals = event_signals(conn, event_id)

        period_end = next(
            (f["period_end"] for f in facts if f.get("period_end")), None
        )
        snapshot = build_snapshot(conn, event["company_id"], period_end)

        return {
            "event": event_dict(event),
            "company": company_dict(company) if company else None,
            "facts": facts,
            "metrics": metrics,
            "signals": signals,
            "financial_snapshot": snapshot,
        }
