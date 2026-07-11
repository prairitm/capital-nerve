"""Alert presentation from financial_result_flow.ipynb Step 7."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from alerts_config import settings
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


def _signals_catalog() -> dict[str, Any]:
    catalog: dict[str, Any] = {}
    for path in (
        settings.catalog_dir / "signals.json",
        settings.catalog_dir / "investor_presentation" / "presentation_signals.json",
        settings.catalog_dir / "earnings-call" / "earnings_call_signals.json",
    ):
        if not path.exists():
            continue
        try:
            catalog.update(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return catalog


def card_confidence(severity: str | None) -> str:
    severity_key = str(severity or "").upper()
    if severity_key in {"CRITICAL", "HIGH"}:
        return "high"
    if severity_key == "MEDIUM":
        return "medium"
    return "low"


def load_alerts(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
) -> list[dict[str, Any]]:
    catalog = _signals_catalog()
    rows = conn.execute(
        """
        SELECT signal_id, signal_code, severity, direction,
               supporting_metric_ids, supporting_fact_ids
        FROM signals WHERE company_id = ? AND event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()
    ordered = sorted(rows, key=lambda row: SEVERITY_ORDER.get(row["severity"], 9))
    alerts: list[dict[str, Any]] = []
    for row in ordered:
        spec = catalog.get(row["signal_code"], {})
        evidence = {
            "metric_ids": [
                item.strip()
                for item in str(row["supporting_metric_ids"] or "").split(",")
                if item.strip()
            ],
            "fact_ids": [
                item.strip()
                for item in str(row["supporting_fact_ids"] or "").split(",")
                if item.strip()
            ],
        }
        alerts.append(
            {
                "signal_type": row["signal_code"],
                "title": spec.get("name", row["signal_code"]),
                "description": spec.get("description"),
                "direction": row["direction"] or spec.get("direction"),
                "severity": row["severity"] or spec.get("severity"),
                "evidence": evidence,
                "trigger_values": {},
            }
        )
    return alerts


def persist_intelligence_cards(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
) -> None:
    catalog = _signals_catalog()
    rows = conn.execute(
        """
        SELECT signal_id, signal_code, severity
        FROM signals WHERE company_id = ? AND event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()
    conn.execute(
        "DELETE FROM intelligence_cards WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for row in rows:
        spec = catalog.get(row["signal_code"], {})
        card_id = hashlib.sha256(
            f"{company_id}:{event_id}:{row['signal_id']}:card".encode()
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO intelligence_cards (
                card_id, company_id, event_id, card_title, signal_id,
                confidence, display_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'published')
            """,
            (
                card_id,
                company_id,
                event_id,
                spec.get("name", row["signal_code"]),
                row["signal_id"],
                card_confidence(row["severity"]),
            ),
        )
    conn.commit()


def load_counts(conn: sqlite3.Connection, *, event_id: str) -> dict[str, int]:
    return {
        "fact_observations": conn.execute(
            "SELECT COUNT(*) c FROM fact_observations WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "resolved_facts": conn.execute(
            "SELECT COUNT(*) c FROM resolved_facts WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "extracted_values": conn.execute(
            "SELECT COUNT(*) c FROM extracted_values WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "metric_values": conn.execute(
            "SELECT COUNT(*) c FROM metrics WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "metrics": conn.execute(
            "SELECT COUNT(*) c FROM metrics WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "signals": conn.execute(
            "SELECT COUNT(*) c FROM signals WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "intelligence_cards": conn.execute(
            "SELECT COUNT(*) c FROM intelligence_cards WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "presentation_segments": conn.execute(
            "SELECT COUNT(*) c FROM presentation_segments WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
        "presentation_inventories": conn.execute(
            "SELECT COUNT(*) c FROM presentation_document_inventory WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"],
    }


def present_alerts(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    company_id: str,
    event_id: str,
    event_type: str = "Financial Results",
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    persist_intelligence_cards(conn, company_id=company_id, event_id=event_id)
    alerts = load_alerts(conn, company_id=company_id, event_id=event_id)
    counts = load_counts(conn, event_id=event_id)
    filing_label = "investor presentation" if event_type == "Investor Presentation" else "filing"
    message = (
        f"No signals triggered for this {filing_label}."
        if not alerts
        else f"{len(alerts)} signal alert(s) triggered for this {filing_label}."
    )
    return {"alerts": alerts, "counts": counts, "message": message}
