"""Event detail endpoint over the 7-step DB."""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, HTTPException, Query

from app_db import get_app_conn
from config import settings
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


def _event_summary(conn, event_id: str) -> dict | None:
    if not has_table(conn, "event_summaries"):
        return None
    row = conn.execute(
        "SELECT * FROM event_summaries WHERE event_id = ?", (event_id,)
    ).fetchone()
    if row is None:
        return None
    try:
        key_points = json.loads(row["key_points_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        key_points = []
    return {
        "event_id": event_id,
        "document_id": row["document_id"],
        "model": row["model"],
        "headline": row["headline"],
        "summary": row["summary"],
        "key_points": key_points,
        "investor_takeaway": row["investor_takeaway"],
        "generated_at": row["updated_at"],
        "cached": True,
    }


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
            "event_summary": _event_summary(conn, event_id),
        }


@router.post("/events/{event_id}/summary")
def generate_event_summary(event_id: str, force: bool = Query(default=False)):
    with get_conn() as conn:
        event_exists = conn.execute(
            "SELECT 1 FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if event_exists is None:
            raise HTTPException(status_code=404, detail="Event not found")
        if not force:
            cached = _event_summary(conn, event_id)
            if cached is not None:
                return cached

    try:
        response = httpx.post(
            f"{settings.values_service_url}/values/summarize",
            json={"event_id": event_id, "force": force},
            timeout=90,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = "Event summary generation failed"
        try:
            payload = exc.response.json()
            detail = str(payload.get("detail") or detail)
        except (TypeError, ValueError):
            pass
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Event summary service is unavailable",
        ) from exc
    return response.json()
