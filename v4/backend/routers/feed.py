"""Watchlist-scoped home feed of completed supported filings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app_db import get_app_conn
from catalog import select_display_signals
from db import get_conn
from security import CurrentUser, require_ready_user
from serializers import event_dict, signal_dict


router = APIRouter(tags=["feed"])
SUPPORTED_EVENT_TYPES = (
    "Financial Results",
    "Investor Presentation",
    "Earnings Call Transcript",
)


def _watched_company_ids(user_id: str) -> list[str]:
    with get_app_conn() as conn:
        return [
            row["company_id"]
            for row in conn.execute(
                "SELECT company_id FROM watchlist_companies WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        ]


def _monitor_job_statuses(company_ids: list[str]) -> dict[str, str]:
    if not company_ids:
        return {}
    placeholders = ",".join("?" for _ in company_ids)
    with get_app_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT event_id, canonical_event_id, status
            FROM pipeline_jobs WHERE company_id IN ({placeholders})
            """,
            company_ids,
        ).fetchall()
    statuses: dict[str, str] = {}
    for row in rows:
        statuses[row["event_id"]] = row["status"]
        statuses[row["canonical_event_id"]] = row["status"]
    return statuses


def _company_from_event_row(row) -> dict[str, Any]:
    return {
        "id": row["c_id"],
        "name": row["c_name"],
        "ticker": row["c_ticker"],
        "exchange": row["c_exchange"],
        "sector": row["c_sector"],
        "industry": row["c_industry"],
        "isin": row["c_isin"],
    }


def _document_from_event_row(row) -> dict[str, Any] | None:
    if not row["d_id"]:
        return None
    return {
        "id": row["d_id"],
        "company_id": row["d_company_id"],
        "source_url": row["d_source_url"],
        "title": row["d_title"],
        "document_kind": row["d_document_kind"],
        "file_size": row["d_file_size"],
        "status": row["d_status"],
        "error_message": row["d_error_message"],
        "ingested_at": row["d_ingested_at"],
    }


def _feed_items(user_id: str, limit: int | None, offset: int = 0) -> list[dict[str, Any]]:
    company_ids = _watched_company_ids(user_id)
    if not company_ids:
        return []
    job_statuses = _monitor_job_statuses(company_ids)
    company_placeholders = ",".join("?" for _ in company_ids)
    type_placeholders = ",".join("?" for _ in SUPPORTED_EVENT_TYPES)
    params: list[Any] = [*company_ids, *SUPPORTED_EVENT_TYPES]
    sql = f"""
        SELECT e.*,
               c.id AS c_id, c.name AS c_name, c.ticker AS c_ticker,
               c.exchange AS c_exchange, c.sector AS c_sector,
               c.industry AS c_industry, c.isin AS c_isin,
               d.id AS d_id, d.company_id AS d_company_id,
               d.source_url AS d_source_url, d.title AS d_title,
               d.document_kind AS d_document_kind, d.file_size AS d_file_size,
               d.status AS d_status, d.error_message AS d_error_message,
               d.ingested_at AS d_ingested_at
        FROM events e
        JOIN companies c ON c.id = e.company_id
        LEFT JOIN documents d ON d.id = e.document_id
        WHERE e.company_id IN ({company_placeholders})
          AND e.event_type IN ({type_placeholders})
          AND e.status = 'processed'
          AND e.document_id IS NOT NULL
        ORDER BY e.event_date DESC, e.id DESC
    """
    with get_conn() as conn:
        event_rows = conn.execute(sql, params).fetchall()
        visible_rows = [
            row
            for row in event_rows
            if job_statuses.get(row["id"], "succeeded") == "succeeded"
        ]
        if limit is not None:
            visible_rows = visible_rows[offset:offset + limit]
        if not visible_rows:
            return []
        event_ids = [row["id"] for row in visible_rows]
        signal_placeholders = ",".join("?" for _ in event_ids)
        signal_rows = conn.execute(
            f"SELECT * FROM signals WHERE event_id IN ({signal_placeholders})",
            event_ids,
        ).fetchall()

    signals_by_event: dict[str, list[dict[str, Any]]] = {event_id: [] for event_id in event_ids}
    companies = {row["id"]: _company_from_event_row(row) for row in visible_rows}
    events = {row["id"]: event_dict(row) for row in visible_rows}
    for row in signal_rows:
        payload = signal_dict(row)
        event_id = row["event_id"]
        payload["company"] = companies.get(event_id)
        payload["event"] = events.get(event_id)
        signals_by_event.setdefault(event_id, []).append(payload)

    items: list[dict[str, Any]] = []
    for row in visible_rows:
        event_id = row["id"]
        selected = select_display_signals(
            signals_by_event.get(event_id, []),
            row["event_type"],
        )
        company = companies[event_id]
        event = events[event_id]
        items.append(
            {
                "company": company,
                "event": event,
                "document": _document_from_event_row(row),
                "signals": selected,
                "detail_path": (
                    f"/company/{company['ticker']}/event/{event_id}"
                    if company.get("ticker")
                    else None
                ),
            }
        )
    return items


@router.get("/feed")
def feed(
    limit: int = Query(default=60, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_ready_user),
):
    return _feed_items(user.id, limit, offset)


@router.get("/feed/summary")
def feed_summary(user: CurrentUser = Depends(require_ready_user)):
    items = _feed_items(user.id, None)
    signals = [signal for item in items for signal in item["signals"]]
    summary = {
        "processed_filings": len(items),
        "total_signals": len(signals),
        "total": len(signals),
        "positive": 0,
        "negative": 0,
        "mixed": 0,
        "by_category": {},
        "by_severity": {},
    }
    for signal in signals:
        direction = (signal.get("direction") or "").upper()
        if direction == "POSITIVE":
            summary["positive"] += 1
        elif direction == "NEGATIVE":
            summary["negative"] += 1
        elif direction == "MIXED":
            summary["mixed"] += 1
        category = signal.get("category") or "other"
        summary["by_category"][category] = summary["by_category"].get(category, 0) + 1
        severity = (signal.get("severity") or "").upper() or "UNKNOWN"
        summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1
    return summary
