"""Event discovery persistence from financial_result_flow.ipynb Step 2."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from event_db import bootstrap_schema


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def event_id_from_source(company_id: str, source_url: str) -> str:
    return hashlib.sha256(f"{company_id}:{source_url}".encode()).hexdigest()


def _event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company_id": row["company_id"],
        "event_type": row["event_type"],
        "event_date": row["event_date"],
        "title": row["title"],
        "source_url": row["source_url"],
        "status": row["status"],
    }


def _backfill_company_from_first_announcement(
    conn: sqlite3.Connection,
    company_id: str,
    symbol: str,
    announcements: list[dict[str, Any]],
) -> None:
    if not announcements:
        return

    first = announcements[0]
    isin = first.get("sm_isin")
    if isin:
        owner = conn.execute("SELECT id FROM companies WHERE isin = ?", (isin,)).fetchone()
        if owner is not None and owner["id"] != company_id:
            isin = None

    conn.execute(
        """
        UPDATE companies
        SET name = COALESCE(?, name), isin = COALESCE(?, isin),
            industry = COALESCE(?, industry)
        WHERE id = ?
        """,
        (
            first.get("sm_name") or symbol,
            isin,
            first.get("smIndustry"),
            company_id,
        ),
    )


def persist_announcements(
    conn: sqlite3.Connection,
    symbol: str,
    announcements: list[dict[str, Any]],
    company_id: str | None = None,
) -> dict[str, Any]:
    company_id = company_id or company_id_for_symbol(symbol)
    bootstrap_schema(conn)
    _backfill_company_from_first_announcement(conn, company_id, symbol, announcements)

    event_ids: list[str] = []
    stored = 0
    for item in announcements:
        source_url = item.get("attchmntFile") or ""
        seed = source_url or f"{item.get('desc')}:{item.get('dt')}"
        event_id = event_id_from_source(company_id, seed)
        conn.execute(
            """
            INSERT OR IGNORE INTO events (
                id, company_id, event_type, event_date, title, source_url, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'discovered')
            """,
            (
                event_id,
                company_id,
                (item.get("desc") or "(missing)").strip(),
                (item.get("sort_date") or "")[:10],
                item.get("attchmntText"),
                source_url or None,
            ),
        )
        event_ids.append(event_id)
        stored += 1
    conn.commit()

    desc_buckets: dict[str, int] = {}
    for item in announcements:
        desc = (item.get("desc") or "(missing)").strip()
        desc_buckets[desc] = desc_buckets.get(desc, 0) + 1

    events = []
    if event_ids:
        placeholders = ",".join("?" for _ in event_ids)
        rows = conn.execute(
            f"""
            SELECT id, company_id, event_type, event_date, title, source_url, status
            FROM events
            WHERE id IN ({placeholders})
            ORDER BY event_date DESC, id
            """,
            event_ids,
        ).fetchall()
        events = [_event_row_to_dict(row) for row in rows]

    return {
        "company_id": company_id,
        "announcements_count": len(announcements),
        "stored_count": stored,
        "desc_buckets": desc_buckets,
        "events": events,
        "first_announcement": announcements[0] if announcements else None,
    }
