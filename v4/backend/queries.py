"""Shared SQL lookups used across routers."""

from __future__ import annotations

import sqlite3
from typing import Any

from catalog import metric_meta
from serializers import (
    extracted_value_dict,
    metric_value_dict,
    signal_dict,
)

# Headline facts shown in the financial snapshot, in display order.
SNAPSHOT_FACTS: list[tuple[str, str]] = [
    ("revenue_from_operations", "Revenue"),
    ("ebitda", "EBITDA"),
    ("pbt", "Profit Before Tax"),
    ("pat", "PAT"),
    ("eps_basic", "EPS"),
]


def find_company(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Resolve a company by ticker (case-insensitive), id, or name."""
    row = conn.execute(
        "SELECT * FROM companies WHERE ticker = ? COLLATE NOCASE", (ticker,)
    ).fetchone()
    if row:
        return row
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (ticker,)).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM companies WHERE name = ? COLLATE NOCASE", (ticker,)
    ).fetchone()


def latest_event(conn: sqlite3.Connection, company_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM events
        WHERE company_id = ?
        ORDER BY event_date DESC, id DESC
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()


def company_events(conn: sqlite3.Connection, company_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM events
        WHERE company_id = ?
        ORDER BY event_date DESC, id DESC
        """,
        (company_id,),
    ).fetchall()


def event_signals(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM signals WHERE event_id = ? ORDER BY severity DESC", (event_id,)
    ).fetchall()
    return [signal_dict(r) for r in rows]


def event_metrics(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT mv.*, m.metric_code AS metric_code
        FROM metric_values mv
        JOIN metrics m ON m.id = mv.metric_id
        WHERE mv.event_id = ?
        """,
        (event_id,),
    ).fetchall()
    return [metric_value_dict(r) for r in rows]


def event_facts(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM extracted_values
        WHERE event_id = ?
        ORDER BY value_code
        """,
        (event_id,),
    ).fetchall()
    return [extracted_value_dict(r) for r in rows]


def _prior_year_end(period_end: str | None) -> str | None:
    """Given an ISO quarter-end date, return the same quarter one year prior."""
    if not period_end or len(period_end) < 4:
        return None
    try:
        year = int(period_end[:4])
    except ValueError:
        return None
    return f"{year - 1}{period_end[4:]}"


def _prior_quarter_end(period_end: str | None) -> str | None:
    """Given an ISO quarter-end date, return the immediately preceding quarter-end."""
    if not period_end or len(period_end) < 10:
        return None
    try:
        year = int(period_end[:4])
    except ValueError:
        return None
    md = period_end[5:]
    if md == "03-31":
        return f"{year - 1}-12-31"
    if md == "06-30":
        return f"{year}-03-31"
    if md == "09-30":
        return f"{year}-06-30"
    if md == "12-31":
        return f"{year}-09-30"
    return None


def _event_period_end(conn: sqlite3.Connection, event_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT period_end FROM extracted_values
        WHERE event_id = ? AND period_end IS NOT NULL
        LIMIT 1
        """,
        (event_id,),
    ).fetchone()
    if row and row["period_end"]:
        return row["period_end"]
    row = conn.execute(
        """
        SELECT period_end FROM metric_values
        WHERE event_id = ? AND period_end IS NOT NULL
        LIMIT 1
        """,
        (event_id,),
    ).fetchone()
    return row["period_end"] if row else None


def _load_fact_for_scope(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    fact_key: str,
    scope: str,
    period_end: str | None,
) -> dict[str, Any] | None:
    scope = (scope or "CURRENT").upper()
    if scope == "CURRENT":
        row = conn.execute(
            """
            SELECT ev.*, e.document_id AS document_id
            FROM extracted_values ev
            LEFT JOIN events e ON e.id = ev.event_id
            WHERE ev.event_id = ? AND ev.value_code = ?
            ORDER BY CASE ev.basis WHEN 'consolidated' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (event_id, fact_key),
        ).fetchone()
    else:
        target_end = None
        if scope == "PY":
            target_end = _prior_year_end(period_end)
        elif scope == "PQ":
            target_end = _prior_quarter_end(period_end)
        if not target_end:
            return None
        row = conn.execute(
            """
            SELECT ev.*, e.document_id AS document_id
            FROM extracted_values ev
            LEFT JOIN events e ON e.id = ev.event_id
            WHERE ev.company_id = ? AND ev.period_end = ? AND ev.value_code = ?
            ORDER BY CASE ev.basis WHEN 'consolidated' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (company_id, target_end, fact_key),
        ).fetchone()

    if not row or row["value_numeric"] is None:
        return None

    fact = extracted_value_dict(row)
    fact["scope"] = scope
    fact["fact_key"] = fact_key
    fact["document_id"] = row["document_id"]
    return fact


_SCOPE_ORDER = {"CURRENT": 0, "PY": 1, "PQ": 2}


def signal_input_facts(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    metric_keys: list[str],
) -> list[dict[str, Any]]:
    """Resolve catalog metric inputs to extracted facts with source provenance."""
    if not metric_keys:
        return []

    seen: set[tuple[str, str]] = set()
    ordered_keys: list[tuple[str, str]] = []
    for metric_key in metric_keys:
        for inp in metric_meta(metric_key).get("inputs") or []:
            fact_key = inp.get("fact_key")
            scope = (inp.get("scope") or "CURRENT").upper()
            if not fact_key:
                continue
            pair = (fact_key, scope)
            if pair in seen:
                continue
            seen.add(pair)
            ordered_keys.append(pair)

    if not ordered_keys:
        return []

    period_end = _event_period_end(conn, event_id)
    facts: list[dict[str, Any]] = []
    for fact_key, scope in sorted(
        ordered_keys, key=lambda p: (_SCOPE_ORDER.get(p[1], 9), p[0])
    ):
        fact = _load_fact_for_scope(
            conn,
            company_id=company_id,
            event_id=event_id,
            fact_key=fact_key,
            scope=scope,
            period_end=period_end,
        )
        if fact:
            facts.append(fact)
    return facts


def build_snapshot(
    conn: sqlite3.Connection,
    company_id: str,
    period_end: str | None,
) -> list[dict[str, Any]]:
    """Current vs prior-year headline facts (crore amounts / EPS)."""
    if not period_end:
        return []

    def load(pe: str) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT value_code, value_numeric, unit FROM extracted_values
            WHERE company_id = ? AND period_end = ?
            ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
            """,
            (company_id, pe),
        ).fetchall()
        pool: dict[str, dict[str, Any]] = {}
        for r in rows:
            if r["value_numeric"] is None:
                continue
            pool.setdefault(
                r["value_code"],
                {"value": float(r["value_numeric"]), "unit": r["unit"]},
            )
        return pool

    current = load(period_end)
    py_end = _prior_year_end(period_end)
    prior = load(py_end) if py_end else {}

    snapshot: list[dict[str, Any]] = []
    for code, label in SNAPSHOT_FACTS:
        cur = current.get(code)
        if cur is None:
            continue
        prev = prior.get(code)
        cur_v = cur["value"]
        prev_v = prev["value"] if prev else None
        yoy = None
        if prev_v not in (None, 0):
            yoy = (cur_v - prev_v) / abs(prev_v) * 100
        snapshot.append(
            {
                "code": code,
                "metric": label,
                "current_value": cur_v,
                "previous_value": prev_v,
                "yoy_change_pct": yoy,
                "unit": cur["unit"],
            }
        )
    return snapshot
