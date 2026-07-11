"""Home feed + summary. The feed is the Step 7 'alerts' view: recent signals
across all companies, shaped as cards."""

from __future__ import annotations

from fastapi import APIRouter, Query

from db import get_conn
from serializers import event_dict, signal_dict

router = APIRouter(tags=["feed"])


def _signal_rows(conn, limit: int | None = None):
    sql = """
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
        ORDER BY e.event_date DESC,
            CASE UPPER(COALESCE(s.severity, ''))
                WHEN 'CRITICAL' THEN 0
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                ELSE 9
            END
    """
    if limit is not None:
        sql += " LIMIT ?"
        return conn.execute(sql, (limit,)).fetchall()
    return conn.execute(sql).fetchall()


def _company_from_row(r):
    if not r["c_id"]:
        return None
    return {
        "id": r["c_id"],
        "name": r["c_name"],
        "ticker": r["c_ticker"],
        "exchange": r["c_exchange"],
        "sector": r["c_sector"],
        "industry": r["c_industry"],
        "isin": r["c_isin"],
    }


def _event_from_row(r):
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


@router.get("/feed")
def feed(limit: int = Query(default=60, ge=1, le=300)):
    with get_conn() as conn:
        rows = _signal_rows(conn, limit)
        out = []
        for r in rows:
            payload = signal_dict(r, _company_from_row(r))
            payload["event"] = _event_from_row(r)
            out.append(payload)
        return out


@router.get("/feed/summary")
def feed_summary():
    with get_conn() as conn:
        rows = _signal_rows(conn)
        signals = []
        for r in rows:
            payload = signal_dict(r, _company_from_row(r))
            payload["event"] = _event_from_row(r)
            signals.append(payload)

    summary = {
        "total": len(signals),
        "positive": 0,
        "negative": 0,
        "mixed": 0,
        "by_category": {},
        "by_severity": {},
    }
    for s in signals:
        direction = (s.get("direction") or "").upper()
        if direction == "POSITIVE":
            summary["positive"] += 1
        elif direction == "NEGATIVE":
            summary["negative"] += 1
        elif direction == "MIXED":
            summary["mixed"] += 1
        cat = s.get("category") or "other"
        summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
        sev = (s.get("severity") or "").upper() or "UNKNOWN"
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
    return summary
