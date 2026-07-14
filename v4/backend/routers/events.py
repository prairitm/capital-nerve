"""Event detail endpoint over the 7-step DB."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import get_conn
from catalog import quarter_synthesis_config
from queries import (
    build_snapshot,
    event_fact_periods,
    event_facts,
    event_metrics,
    event_signals,
    quarter_document_sections,
)
from serializers import company_dict, event_dict

router = APIRouter(tags=["events"])


@router.get("/events/{event_id}")
def event_detail(event_id: str, period_end: str | None = Query(default=None)):
    with get_conn() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (event["company_id"],)
        ).fetchone()

        fact_periods = event_fact_periods(conn, event_id)
        valid_period_ends = {p["period_end"] for p in fact_periods}
        if period_end and period_end not in valid_period_ends:
            raise HTTPException(status_code=404, detail="Fact period not found for event")

        selected_period_end = period_end or next(
            (
                p["period_end"]
                for p in fact_periods
                if p.get("is_current_event_period")
            ),
            None,
        )
        facts = event_facts(conn, event_id, period_end=selected_period_end)
        metrics = event_metrics(conn, event_id)
        signals = event_signals(conn, event_id)
        if event["fiscal_year"] is not None and event["fiscal_quarter"] is not None:
            related_events = conn.execute(
                """
                SELECT * FROM events
                WHERE company_id = ?
                  AND fiscal_year = ?
                  AND fiscal_quarter = ?
                  AND document_id IS NOT NULL
                  AND COALESCE(status, '') = 'processed'
                ORDER BY CASE LOWER(COALESCE(event_type, ''))
                    WHEN 'quarterly_result' THEN 0
                    WHEN 'quarterly result' THEN 0
                    WHEN 'financial_result' THEN 0
                    WHEN 'financial results' THEN 0
                    WHEN 'investor presentation' THEN 1
                    ELSE 9
                END, event_date DESC, id DESC
                """,
                (event["company_id"], event["fiscal_year"], event["fiscal_quarter"]),
            ).fetchall()
        elif event["event_date"]:
            related_events = conn.execute(
                """
                SELECT * FROM events
                WHERE company_id = ?
                  AND event_date = ?
                  AND document_id IS NOT NULL
                  AND COALESCE(status, '') = 'processed'
                ORDER BY CASE LOWER(COALESCE(event_type, ''))
                    WHEN 'quarterly_result' THEN 0
                    WHEN 'quarterly result' THEN 0
                    WHEN 'financial_result' THEN 0
                    WHEN 'financial results' THEN 0
                    WHEN 'investor presentation' THEN 1
                    ELSE 9
                END, id DESC
                """,
                (event["company_id"], event["event_date"]),
            ).fetchall()
        else:
            related_events = [event] if event["document_id"] else []

        snapshot = build_snapshot(conn, event["company_id"], selected_period_end)
        document_sections = quarter_document_sections(conn, event)

        return {
            "event": event_dict(event),
            "company": company_dict(company) if company else None,
            "facts": facts,
            "fact_periods": fact_periods,
            "selected_fact_period_end": selected_period_end,
            "metrics": metrics,
            "signals": signals,
            "financial_snapshot": snapshot,
            "related_events": [event_dict(e) for e in related_events],
            "document_sections": document_sections,
            "quarter_display": quarter_synthesis_config(),
        }
