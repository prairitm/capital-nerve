"""Read/write values, metric_values, and signals in v3 SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

NO_MATERIAL_SIGNAL = "no_material_change"


def value_id(company_id: str, value_code: str, period_end: str, basis: str) -> str:
    key = f"{company_id}:{value_code}:{period_end}:{basis}"
    return hashlib.sha256(key.encode()).hexdigest()


def metric_value_id(company_id: str, event_id: str, metric_code: str) -> str:
    return hashlib.sha256(f"{company_id}:{event_id}:{metric_code}".encode()).hexdigest()


def signal_id(company_id: str, event_id: str, signal_type: str) -> str:
    return hashlib.sha256(f"{company_id}:{event_id}:{signal_type}".encode()).hexdigest()


def upsert_values(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_start: str | None,
    period_end: str,
    rows: list[dict[str, Any]],
) -> int:
    written = 0
    for row in rows:
        value_code = row["value_code"]
        basis = (row.get("basis") or "consolidated").strip().lower()
        vid = value_id(company_id, value_code, period_end, basis)
        conn.execute(
            """
            INSERT INTO extracted_values (
                id, company_id, event_id, value_code, value_numeric, unit,
                period_type, period_start, period_end, basis,
                source_text, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                event_id = excluded.event_id,
                value_numeric = excluded.value_numeric,
                unit = excluded.unit,
                period_type = excluded.period_type,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                source_text = excluded.source_text,
                confidence = excluded.confidence
            """,
            (
                vid,
                company_id,
                event_id,
                value_code,
                row.get("value_numeric", row.get("numeric_value")),
                row.get("unit"),
                row.get("period_type", "quarter"),
                period_start,
                period_end,
                basis,
                row.get("source_text") or row.get("evidence"),
                row.get("confidence"),
            ),
        )
        written += 1
    return written


def load_fact_details_for_period(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    period_end: str,
    basis: str = "consolidated",
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT value_code, value_numeric, unit, source_text
        FROM extracted_values
        WHERE company_id = ? AND period_end = ? AND basis = ?
        """,
        (company_id, period_end, basis),
    ).fetchall()
    if not rows and basis == "consolidated":
        rows = conn.execute(
            """
            SELECT value_code, value_numeric, unit, source_text
            FROM extracted_values
            WHERE company_id = ? AND period_end = ? AND basis = 'standalone'
            """,
            (company_id, period_end),
        ).fetchall()
    return {
        row["value_code"]: {
            "numeric_value": float(row["value_numeric"]),
            "unit": row["unit"],
            "evidence": row["source_text"],
        }
        for row in rows
        if row["value_numeric"] is not None
    }


def replace_metric_values(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_start: str | None,
    period_end: str,
    metrics: list[dict[str, Any]],
) -> int:
    conn.execute(
        "DELETE FROM metric_values WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    written = 0
    for metric in metrics:
        metric_key = metric.get("metric_key")
        if not metric_key or metric.get("value") is None:
            continue
        row = conn.execute(
            "SELECT id FROM metrics WHERE metric_code = ?",
            (metric_key,),
        ).fetchone()
        if not row:
            continue
        mid = row["id"]
        mvid = metric_value_id(company_id, event_id, metric_key)
        conn.execute(
            """
            INSERT INTO metric_values (
                id, company_id, event_id, metric_id, metric_value,
                period_start, period_end, calculation_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mvid,
                company_id,
                event_id,
                mid,
                float(metric["value"]),
                period_start,
                period_end,
                json.dumps(
                    {
                        "derivation": metric.get("derivation"),
                        "unit": metric.get("unit"),
                        "formula_evaluated": metric.get("formula_evaluated"),
                        "inputs": metric.get("inputs"),
                    }
                ),
            ),
        )
        written += 1
    return written


def replace_signals(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    signals: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> int:
    conn.execute(
        "DELETE FROM signals WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    by_key = {m["metric_key"]: m for m in metrics if m.get("metric_key")}
    written = 0
    for signal in signals:
        signal_key = signal.get("signal_key") or signal.get("signal_type")
        if not signal_key or signal_key == NO_MATERIAL_SIGNAL:
            continue
        metric_keys = signal.get("metric_keys") or []
        trigger = {
            mk: by_key[mk]["value"]
            for mk in metric_keys
            if mk in by_key and by_key[mk].get("value") is not None
        }
        sid = signal_id(company_id, event_id, signal_key)
        conn.execute(
            """
            INSERT INTO signals (
                id, company_id, event_id, signal_type, title, description,
                direction, severity, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                company_id,
                event_id,
                signal_key,
                signal.get("headline") or signal.get("title") or signal_key,
                signal.get("rationale") or signal.get("description") or "",
                signal.get("direction"),
                signal.get("severity"),
                json.dumps(
                    {
                        "metric_keys": metric_keys,
                        "trigger_values": trigger,
                        "rule_text": signal.get("rule_text"),
                        "category": signal.get("category"),
                    }
                ),
            ),
        )
        written += 1
    return written


def set_document_status(
    conn: sqlite3.Connection,
    document_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE documents SET status = ?, error_message = ? WHERE id = ?
        """,
        (status, error_message, document_id),
    )


def set_event_status(
    conn: sqlite3.Connection,
    event_id: str,
    status: str,
    *,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
) -> None:
    conn.execute(
        """
        UPDATE events
        SET status = ?, fiscal_year = COALESCE(?, fiscal_year),
            fiscal_quarter = COALESCE(?, fiscal_quarter)
        WHERE id = ?
        """,
        (status, fiscal_year, fiscal_quarter, event_id),
    )


def load_document_bundle(
    conn: sqlite3.Connection, document_id: str
) -> dict[str, Any] | None:
    doc = conn.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
    if not doc:
        return None
    company = conn.execute(
        "SELECT * FROM companies WHERE id = ?", (doc["company_id"],)
    ).fetchone()
    event = conn.execute(
        """
        SELECT * FROM events
        WHERE document_id = ? AND company_id = ?
        ORDER BY event_date DESC LIMIT 1
        """,
        (document_id, doc["company_id"]),
    ).fetchone()
    return {
        "document": dict(doc),
        "company": dict(company) if company else None,
        "event": dict(event) if event else None,
    }


def document_counts(conn: sqlite3.Connection, document_id: str) -> dict[str, int]:
    event = conn.execute(
        "SELECT id FROM events WHERE document_id = ? LIMIT 1", (document_id,)
    ).fetchone()
    if not event:
        return {"extracted_values": 0, "metric_values": 0, "signals": 0}
    event_id = event["id"]
    values = conn.execute(
        "SELECT COUNT(*) AS c FROM extracted_values WHERE event_id = ?", (event_id,)
    ).fetchone()["c"]
    metrics = conn.execute(
        "SELECT COUNT(*) AS c FROM metric_values WHERE event_id = ?", (event_id,)
    ).fetchone()["c"]
    signals = conn.execute(
        "SELECT COUNT(*) AS c FROM signals WHERE event_id = ?", (event_id,)
    ).fetchone()["c"]
    return {"extracted_values": values, "metric_values": metrics, "signals": signals}
