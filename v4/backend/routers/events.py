"""Event detail endpoint over the 7-step DB."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app_db import get_app_conn
from db import get_conn
from catalog import quarter_synthesis_config
from queries import (
    build_snapshot,
    event_fact_periods,
    event_facts,
    event_metrics,
    event_signals,
    has_table,
    quarter_document_sections,
)
from serializers import company_dict, event_dict

router = APIRouter(tags=["events"])


def _intelligence_status(conn, event_id: str) -> dict:
    """Describe whether review/recomputation can still change event intelligence."""
    if not has_table(conn, "resolved_facts"):
        return {
            "state": "ready",
            "pending_facts": 0,
            "verified_facts": 0,
        }

    verified_facts = conn.execute(
        """
        SELECT COUNT(*) AS count FROM resolved_facts
        WHERE event_id = ? AND resolution_status = 'resolved'
        """,
        (event_id,),
    ).fetchone()["count"]
    pending_rows = conn.execute(
        """
        SELECT resolved_fact_id FROM resolved_facts
        WHERE event_id = ? AND resolution_status = 'review_required'
        """,
        (event_id,),
    ).fetchall()
    pending_ids = {row["resolved_fact_id"] for row in pending_rows}

    # A rejected candidate is settled and intentionally excluded from intelligence.
    # Open or approved-but-not-applied candidates can still change metrics/signals.
    rejected_ids: set[str] = set()
    if pending_ids:
        placeholders = ",".join("?" for _ in pending_ids)
        with get_app_conn() as app_conn:
            decisions = app_conn.execute(
                f"""
                SELECT resolved_fact_id FROM fact_review_decisions
                WHERE resolved_fact_id IN ({placeholders}) AND decision = 'rejected'
                """,
                sorted(pending_ids),
            ).fetchall()
        rejected_ids = {row["resolved_fact_id"] for row in decisions}

    pending_facts = len(pending_ids - rejected_ids)
    recompute_pending = 0
    if has_table(conn, "fact_review_reconciliations"):
        recompute_pending = conn.execute(
            """
            SELECT COUNT(*) AS count FROM fact_review_reconciliations
            WHERE event_id = ? AND recompute_status <> 'succeeded'
            """,
            (event_id,),
        ).fetchone()["count"]

    return {
        "state": "processing" if pending_facts or recompute_pending else "ready",
        "pending_facts": pending_facts,
        "verified_facts": verified_facts,
    }


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
            "intelligence_status": _intelligence_status(conn, event_id),
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
