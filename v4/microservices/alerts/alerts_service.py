"""Alert presentation from financial_result_flow.ipynb Step 7."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from alerts_db import bootstrap_schema

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def _parse_evidence(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    return payload if isinstance(payload, dict) else {"raw": payload}


def load_alerts(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT signal_type, title, description, direction, severity, evidence
        FROM signals WHERE company_id = ? AND event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()
    ordered = sorted(rows, key=lambda row: SEVERITY_ORDER.get(row["severity"], 9))
    alerts: list[dict[str, Any]] = []
    for row in ordered:
        evidence = _parse_evidence(row["evidence"])
        alerts.append(
            {
                "signal_type": row["signal_type"],
                "title": row["title"],
                "description": row["description"],
                "direction": row["direction"],
                "severity": row["severity"],
                "evidence": evidence,
                "trigger_values": evidence.get("trigger_values", {}),
            }
        )
    return alerts


def load_counts(conn: sqlite3.Connection, *, event_id: str) -> dict[str, int]:
    return {
        "extracted_values": conn.execute(
            "SELECT COUNT(*) c FROM extracted_values WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "metric_values": conn.execute(
            "SELECT COUNT(*) c FROM metric_values WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "signals": conn.execute(
            "SELECT COUNT(*) c FROM signals WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
    }


def present_alerts(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    company_id: str,
    event_id: str,
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    alerts = load_alerts(conn, company_id=company_id, event_id=event_id)
    counts = load_counts(conn, event_id=event_id)
    message = (
        "No signals triggered for this filing."
        if not alerts
        else f"{len(alerts)} signal alert(s) triggered for this filing."
    )
    return {"alerts": alerts, "counts": counts, "message": message}
