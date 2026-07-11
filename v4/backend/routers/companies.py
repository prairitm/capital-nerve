"""Company endpoints over the 7-step DB."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import get_conn
from queries import (
    build_snapshot,
    company_events,
    event_signals,
    find_company,
    latest_event,
    uses_eight_step_metrics,
)
from serializers import (
    company_dict,
    document_dict,
    event_dict,
    metric_value_dict,
    signal_dict,
)

router = APIRouter(tags=["companies"])


@router.get("/companies")
def list_companies(search: str = "", limit: int = Query(default=200, ge=1, le=1000)):
    with get_conn() as conn:
        if search:
            like = f"%{search}%"
            rows = conn.execute(
                """
                SELECT * FROM companies
                WHERE name LIKE ? COLLATE NOCASE OR ticker LIKE ? COLLATE NOCASE
                ORDER BY name
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM companies ORDER BY name LIMIT ?", (limit,)
            ).fetchall()
        return [company_dict(r) for r in rows]


@router.get("/companies/{ticker}")
def company_hub(ticker: str):
    with get_conn() as conn:
        company = find_company(conn, ticker)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        company_id = company["id"]

        events = company_events(conn, company_id)
        # For the snapshot/metrics block, prefer the most recent event that was
        # actually processed (has metric_values). Fall back to latest by date.
        if uses_eight_step_metrics(conn):
            latest = conn.execute(
                """
                SELECT e.* FROM events e
                JOIN metrics m ON m.event_id = e.id
                WHERE e.company_id = ?
                ORDER BY e.event_date DESC, e.id DESC
                LIMIT 1
                """,
                (company_id,),
            ).fetchone() or latest_event(conn, company_id)
        else:
            latest = conn.execute(
                """
                SELECT e.* FROM events e
                JOIN metric_values mv ON mv.event_id = e.id
                WHERE e.company_id = ?
                ORDER BY e.event_date DESC, e.id DESC
                LIMIT 1
                """,
                (company_id,),
            ).fetchone() or latest_event(conn, company_id)

        snapshot: list = []
        latest_metrics: list = []
        latest_period_events: list = []
        period_label = None
        if latest:
            period_label = event_dict(latest)["period_label"]
            if latest["fiscal_year"] is not None and latest["fiscal_quarter"] is not None:
                latest_period_events = conn.execute(
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
                    (company_id, latest["fiscal_year"], latest["fiscal_quarter"]),
                ).fetchall()
            elif latest["event_date"]:
                latest_period_events = conn.execute(
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
                    (company_id, latest["event_date"]),
                ).fetchall()
            if uses_eight_step_metrics(conn):
                metric_rows = conn.execute(
                    """
                    SELECT m.*, p.period_end AS period_end, NULL AS period_start
                    FROM metrics m
                    LEFT JOIN (
                        SELECT event_id, MAX(period_end) AS period_end
                        FROM extracted_values
                        GROUP BY event_id
                    ) p ON p.event_id = m.event_id
                    WHERE m.event_id = ?
                    """,
                    (latest["id"],),
                ).fetchall()
            else:
                metric_rows = conn.execute(
                    """
                    SELECT mv.*, m.metric_code AS metric_code
                    FROM metric_values mv
                    JOIN metrics m ON m.id = mv.metric_id
                    WHERE mv.event_id = ?
                    """,
                    (latest["id"],),
                ).fetchall()
            latest_metrics = [metric_value_dict(r) for r in metric_rows]
            period_end = None
            facts = conn.execute(
                "SELECT period_end FROM extracted_values WHERE event_id = ? AND period_end IS NOT NULL LIMIT 1",
                (latest["id"],),
            ).fetchone()
            if facts:
                period_end = facts["period_end"]
            snapshot = build_snapshot(conn, company_id, period_end)

        signal_rows = conn.execute(
            """
            SELECT * FROM signals
            WHERE company_id = ?
            ORDER BY CASE UPPER(COALESCE(severity, ''))
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 9
            END
            LIMIT 12
            """,
            (company_id,),
        ).fetchall()
        signals = [signal_dict(r) for r in signal_rows]

        doc_rows = conn.execute(
            "SELECT * FROM documents WHERE company_id = ? ORDER BY ingested_at DESC",
            (company_id,),
        ).fetchall()

        return {
            "company": company_dict(company),
            "latest_event_id": latest["id"] if latest else None,
            "latest_period_label": period_label,
            "latest_period_events": [event_dict(e) for e in latest_period_events],
            "financial_snapshot": snapshot,
            "latest_metrics": latest_metrics,
            "signals": signals,
            "timeline": [event_dict(e) for e in events],
            "documents": [document_dict(d) for d in doc_rows],
        }


@router.get("/companies/{ticker}/events")
def list_company_events(ticker: str):
    with get_conn() as conn:
        company = find_company(conn, ticker)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        events = company_events(conn, company["id"])
        return [event_dict(e) for e in events]


@router.get("/companies/{ticker}/signals")
def list_company_signals(ticker: str, limit: int = Query(default=50, ge=1, le=200)):
    with get_conn() as conn:
        company = find_company(conn, ticker)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        rows = conn.execute(
            """
            SELECT * FROM signals
            WHERE company_id = ?
            ORDER BY CASE UPPER(COALESCE(severity, ''))
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 9
            END
            LIMIT ?
            """,
            (company["id"], limit),
        ).fetchall()
        return [signal_dict(r) for r in rows]


@router.get("/companies/{ticker}/trends")
def company_trends(ticker: str, codes: str = ""):
    """Per metric_code, points across quarters (oldest first) for sparklines."""
    with get_conn() as conn:
        company = find_company(conn, ticker)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        requested = [c.strip() for c in codes.split(",") if c.strip()]
        params: list = [company["id"]]
        code_filter = ""
        if requested:
            placeholders = ",".join("?" for _ in requested)
            code_filter = f"AND m.metric_code IN ({placeholders})"
            params.extend(requested)

        if uses_eight_step_metrics(conn):
            rows = conn.execute(
                f"""
                SELECT m.metric_code AS metric_code, m.value AS metric_value,
                       p.period_end AS period_end, m.formula AS formula,
                       m.input_fact_ids AS input_fact_ids, m.unit AS unit
                FROM metrics m
                LEFT JOIN (
                    SELECT event_id, MAX(period_end) AS period_end
                    FROM extracted_values
                    GROUP BY event_id
                ) p ON p.event_id = m.event_id
                WHERE m.company_id = ? {code_filter}
                ORDER BY p.period_end ASC
                """,
                params,
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT m.metric_code AS metric_code, mv.metric_value AS metric_value,
                       mv.period_end AS period_end, mv.calculation_data AS calculation_data
                FROM metric_values mv
                JOIN metrics m ON m.id = mv.metric_id
                WHERE mv.company_id = ? {code_filter}
                ORDER BY mv.period_end ASC
                """,
                params,
            ).fetchall()

        series: dict[str, dict] = {}
        for r in rows:
            code = r["metric_code"]
            point = metric_value_dict(r)
            entry = series.setdefault(
                code,
                {
                    "metric_code": code,
                    "metric_name": point["metric_name"],
                    "unit": point["unit"],
                    "points": [],
                },
            )
            entry["points"].append(
                {
                    "period_end": r["period_end"],
                    "value": r["metric_value"],
                }
            )
        return list(series.values())
