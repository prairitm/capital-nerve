"""Signal-rule evaluation from financial_result_flow.ipynb Step 6."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from signals_config import settings
from signals_db import bootstrap_schema

OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "IN": lambda a, b: isinstance(b, (list, tuple, set)) and a in b,
    "NOT IN": lambda a, b: isinstance(b, (list, tuple, set)) and a not in b,
    "ABS_GT": lambda a, b: abs(a) > b,
}


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def signal_id(company_id: str, event_id: str, signal_key: str) -> str:
    return hashlib.sha256(f"{company_id}:{event_id}:{signal_key}".encode()).hexdigest()


def load_signals_catalog() -> dict[str, Any]:
    return json.loads((settings.catalog_dir / "signals.json").read_text(encoding="utf-8"))


def load_metrics_by_key(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT m.metric_code, m.name, mv.metric_value, m.unit, m.description, mv.calculation_data
        FROM metric_values mv
        JOIN metrics m ON m.id = mv.metric_id
        WHERE mv.company_id = ? AND mv.event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        calc = {}
        if row["calculation_data"]:
            try:
                calc = json.loads(row["calculation_data"])
            except json.JSONDecodeError:
                calc = {}
        out[row["metric_code"]] = {
            "metric_key": row["metric_code"],
            "name": row["name"],
            "value": float(row["metric_value"]),
            "unit": calc.get("unit", row["unit"]),
            "category": row["description"],
        }
    return out


def load_facts_by_key(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    period_end: str,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT value_code, value_numeric, value_text, unit FROM extracted_values
        WHERE company_id = ? AND period_end = ?
        ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
        """,
        (company_id, period_end),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["value_numeric"] is not None:
            value: Any = float(row["value_numeric"])
        else:
            value = row["value_text"]
        out.setdefault(row["value_code"], {"value": value, "unit": row["unit"]})
    return out


def rule_metric_keys(rule: dict[str, Any]) -> list[str]:
    if "metric_key" in rule:
        return [rule["metric_key"]]
    keys: list[str] = []
    for key in ("all", "any"):
        for child in rule.get(key, []):
            keys.extend(rule_metric_keys(child))
    return keys


def rule_fact_keys(rule: dict[str, Any]) -> list[str]:
    if "fact_key" in rule:
        return [rule["fact_key"]]
    keys: list[str] = []
    for key in ("all", "any"):
        for child in rule.get(key, []):
            keys.extend(rule_fact_keys(child))
    return keys


def format_rule(rule: dict[str, Any]) -> str:
    if "metric_key" in rule:
        return f"{rule['metric_key']} {rule['op']} {rule['value']}"
    if "fact_key" in rule:
        return f"{rule['fact_key']} {rule['op']} {rule['value']}"
    if "all" in rule:
        return " AND ".join(f"({format_rule(child)})" for child in rule["all"])
    if "any" in rule:
        return " OR ".join(f"({format_rule(child)})" for child in rule["any"])
    return ""


def eval_leaf(
    rule: dict[str, Any],
    *,
    metrics_by_key: dict[str, dict[str, Any]],
    facts_by_key: dict[str, dict[str, Any]],
) -> bool:
    if "metric_key" in rule:
        ref = metrics_by_key.get(rule["metric_key"])
    elif "fact_key" in rule:
        ref = facts_by_key.get(rule["fact_key"])
    else:
        raise ValueError(f"Malformed rule leaf: {rule}")
    if ref is None:
        return False
    op = rule["op"].upper() if isinstance(rule["op"], str) else rule["op"]
    if op not in OPS:
        raise ValueError(f"Unsupported rule operator: {rule['op']}")
    return OPS[op](ref["value"], rule["value"])


def eval_rule(
    rule: dict[str, Any],
    *,
    metrics_by_key: dict[str, dict[str, Any]],
    facts_by_key: dict[str, dict[str, Any]],
) -> bool:
    if "all" in rule:
        return all(
            eval_rule(child, metrics_by_key=metrics_by_key, facts_by_key=facts_by_key)
            for child in rule["all"]
        )
    if "any" in rule:
        return any(
            eval_rule(child, metrics_by_key=metrics_by_key, facts_by_key=facts_by_key)
            for child in rule["any"]
        )
    if "metric_key" in rule or "fact_key" in rule:
        return eval_leaf(rule, metrics_by_key=metrics_by_key, facts_by_key=facts_by_key)
    raise ValueError(f"Malformed rule: {rule}")


def evaluate_signal_rules(
    signals_catalog: dict[str, Any],
    *,
    metrics_by_key: dict[str, dict[str, Any]],
    facts_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    fired_signals: list[dict[str, Any]] = []
    for code, spec in signals_catalog.items():
        rule = spec.get("rule")
        if not rule:
            continue
        metric_keys = rule_metric_keys(rule)
        fact_keys = rule_fact_keys(rule)
        if not all(key in metrics_by_key for key in metric_keys):
            continue
        if not all(key in facts_by_key for key in fact_keys):
            continue
        if not eval_rule(rule, metrics_by_key=metrics_by_key, facts_by_key=facts_by_key):
            continue
        trigger_values = {
            key: metrics_by_key[key]["value"]
            for key in metric_keys
            if key in metrics_by_key
        }
        trigger_values.update(
            {key: facts_by_key[key]["value"] for key in fact_keys if key in facts_by_key}
        )
        fired_signals.append(
            {
                "signal_key": code,
                "title": spec.get("name", code),
                "description": spec.get("description", ""),
                "direction": spec.get("direction"),
                "severity": spec.get("severity"),
                "category": spec.get("category"),
                "metric_keys": metric_keys,
                "fact_keys": fact_keys,
                "trigger_values": trigger_values,
                "rule_text": format_rule(rule),
            }
        )
    return fired_signals


def persist_fired_signals(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    fired_signals: list[dict[str, Any]],
) -> None:
    conn.execute(
        "DELETE FROM signals WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for signal in fired_signals:
        conn.execute(
            """
            INSERT INTO signals (
                id, company_id, event_id, signal_type, title, description,
                direction, severity, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id(company_id, event_id, signal["signal_key"]),
                company_id,
                event_id,
                signal["signal_key"],
                signal["title"],
                signal["description"],
                signal["direction"],
                signal["severity"],
                json.dumps(
                    {
                        "metric_keys": signal["metric_keys"],
                        "fact_keys": signal["fact_keys"],
                        "trigger_values": signal["trigger_values"],
                        "rule_text": signal["rule_text"],
                        "category": signal["category"],
                    }
                ),
            ),
        )
    conn.commit()


def evaluate_and_persist_signals(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    company_id: str,
    event_id: str,
    period_end: str,
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    signals_catalog = load_signals_catalog()
    metrics_by_key = load_metrics_by_key(conn, company_id=company_id, event_id=event_id)
    facts_by_key = load_facts_by_key(conn, company_id=company_id, period_end=period_end)
    fired_signals = evaluate_signal_rules(
        signals_catalog,
        metrics_by_key=metrics_by_key,
        facts_by_key=facts_by_key,
    )
    persist_fired_signals(
        conn,
        company_id=company_id,
        event_id=event_id,
        fired_signals=fired_signals,
    )
    return {
        "signals": fired_signals,
        "source_counts": {
            "metrics": len(metrics_by_key),
            "facts": len(facts_by_key),
            "rules": len(signals_catalog),
        },
    }
