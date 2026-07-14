"""Signal feed + detail endpoints over the 7-step DB."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from catalog import select_display_signals, signal_categories, signal_meta
from db import get_conn
from queries import signal_input_facts, table_columns, uses_eight_step_metrics
from serializers import company_dict, event_dict, metric_value_dict, signal_dict

router = APIRouter(tags=["signals"])


@router.get("/signals")
def list_signals(
    category: str = "",
    severity: str = "",
    direction: str = "",
    limit: int = Query(default=100, ge=1, le=500),
):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.*, c.id AS c_id, c.name AS c_name, c.ticker AS c_ticker,
                   c.exchange AS c_exchange, c.sector AS c_sector,
                   c.industry AS c_industry, c.isin AS c_isin,
                   e.id AS e_id, e.company_id AS e_company_id,
                   e.event_type AS e_event_type, e.event_date AS e_event_date,
                   e.fiscal_year AS e_fiscal_year, e.fiscal_quarter AS e_fiscal_quarter,
                   e.title AS e_title, e.source_url AS e_source_url,
                   e.document_id AS e_document_id, e.status AS e_status
            FROM signals s
            LEFT JOIN companies c ON c.id = s.company_id
            LEFT JOIN events e ON e.id = s.event_id
            ORDER BY CASE UPPER(COALESCE(s.severity, ''))
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 9
            END
            """
        ).fetchall()

        grouped: dict[str, list[dict]] = {}
        event_types: dict[str, str | None] = {}
        event_order: list[str] = []
        for r in rows:
            company = None
            if r["c_id"]:
                company = _company_row(r)
            sig = signal_dict(r, company)
            sig["event"] = _event_row(r)
            event_key = r["e_id"] or sig["id"]
            if event_key not in grouped:
                grouped[event_key] = []
                event_types[event_key] = r["e_event_type"]
                event_order.append(event_key)
            grouped[event_key].append(sig)

        out: list[dict] = []
        primary_signals = [
            signal
            for event_key in event_order
            for signal in select_display_signals(grouped[event_key], event_types[event_key])
        ]
        for sig in primary_signals:
            if severity and (sig["severity"] or "").upper() != severity.upper():
                continue
            if direction and (sig["direction"] or "").upper() != direction.upper():
                continue
            if category and (sig["category"] or "") != category:
                continue
            out.append(sig)
            if len(out) >= limit:
                break
        return out


@router.get("/signals/categories")
def list_signal_categories():
    return signal_categories()


@router.get("/signals/{signal_id}")
def signal_detail(signal_id: str):
    with get_conn() as conn:
        signal_cols = table_columns(conn, "signals")
        id_column = "signal_id" if "signal_id" in signal_cols else "id"
        row = conn.execute(f"SELECT * FROM signals WHERE {id_column} = ?", (signal_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")

        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (row["company_id"],)
        ).fetchone()
        sig = signal_dict(row, company)

        meta = signal_meta(sig["signal_type"])
        evidence = sig["evidence"] or {}
        metric_keys = evidence.get("metric_keys") or []
        metric_ids = evidence.get("metric_ids") or []

        referenced_metrics: list[dict] = []
        event = None
        if row["event_id"]:
            event_row = conn.execute(
                "SELECT * FROM events WHERE id = ?", (row["event_id"],)
            ).fetchone()
            event = event_dict(event_row) if event_row else None
            if uses_eight_step_metrics(conn) and metric_ids:
                placeholders = ",".join("?" for _ in metric_ids)
                metric_rows = conn.execute(
                    f"""
                    SELECT m.*, p.period_end AS period_end, NULL AS period_start
                    FROM metrics m
                    LEFT JOIN (
                        SELECT event_id, MAX(period_end) AS period_end
                        FROM extracted_values
                        GROUP BY event_id
                    ) p ON p.event_id = m.event_id
                    WHERE m.event_id = ? AND m.metric_id IN ({placeholders})
                    """,
                    [row["event_id"], *metric_ids],
                ).fetchall()
                referenced_metrics = [metric_value_dict(r) for r in metric_rows]
                if not metric_keys:
                    metric_keys = [r["metric_code"] for r in metric_rows]
            elif metric_keys:
                placeholders = ",".join("?" for _ in metric_keys)
                metric_rows = conn.execute(
                    f"""
                    SELECT mv.*, m.metric_code AS metric_code
                    FROM metric_values mv
                    JOIN metrics m ON m.id = mv.metric_id
                    WHERE mv.event_id = ? AND m.metric_code IN ({placeholders})
                    """,
                    [row["event_id"], *metric_keys],
                ).fetchall()
                referenced_metrics = [metric_value_dict(r) for r in metric_rows]

        input_facts: list[dict] = []
        if row["event_id"] and metric_keys:
            input_facts = signal_input_facts(
                conn,
                company_id=row["company_id"],
                event_id=row["event_id"],
                metric_keys=metric_keys,
            )

        return {
            **sig,
            "rule": meta.get("rule"),
            "rule_text": evidence.get("rule_text"),
            "trigger_values": evidence.get("trigger_values") or {},
            "metric_keys": metric_keys,
            "referenced_metrics": referenced_metrics,
            "input_facts": input_facts,
            "event": event,
        }


def _company_row(r):
    """Reconstruct a company-shaped mapping from a prefixed join row."""
    return {
        "id": r["c_id"],
        "name": r["c_name"],
        "ticker": r["c_ticker"],
        "exchange": r["c_exchange"],
        "sector": r["c_sector"],
        "industry": r["c_industry"],
        "isin": r["c_isin"],
    }


def _event_row(r):
    if not r["e_id"]:
        return None
    return event_dict(
        {
            "id": r["e_id"],
            "company_id": r["e_company_id"],
            "event_type": r["e_event_type"],
            "event_date": r["e_event_date"],
            "fiscal_year": r["e_fiscal_year"],
            "fiscal_quarter": r["e_fiscal_quarter"],
            "title": r["e_title"],
            "source_url": r["e_source_url"],
            "document_id": r["e_document_id"],
            "status": r["e_status"],
        }
    )
