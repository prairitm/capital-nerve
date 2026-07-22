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


def dimension_signal_id(
    company_id: str,
    event_id: str,
    signal_key: str,
    segment: str | None = None,
    geography: str | None = None,
) -> str:
    return hashlib.sha256(
        f"{company_id}:{event_id}:{signal_key}:{segment or ''}:{geography or ''}".encode()
    ).hexdigest()


def load_signals_catalog() -> dict[str, Any]:
    return json.loads((settings.catalog_dir / "signals.json").read_text(encoding="utf-8"))


def load_presentation_signals_catalog() -> dict[str, Any]:
    path = settings.catalog_dir / "investor_presentation_signals.json"
    if not path.exists():
        path = settings.catalog_dir / "investor_presentation" / "presentation_signals.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_earnings_call_signals_catalog() -> dict[str, Any]:
    path = settings.catalog_dir / "earnings_call_signals.json"
    if not path.exists():
        path = settings.catalog_dir / "earnings-call" / "earnings_call_signals.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_metrics_by_key(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT metric_id, metric_code, value, unit, input_fact_ids, formula
        FROM metrics
        WHERE company_id = ? AND event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[row["metric_code"]] = {
            "metric_id": row["metric_id"],
            "metric_key": row["metric_code"],
            "value": float(row["value"]),
            "unit": row["unit"],
            "input_fact_ids": [
                item.strip()
                for item in str(row["input_fact_ids"] or "").split(",")
                if item.strip()
            ],
            "formula": row["formula"],
        }
    return out


def load_facts_by_key(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_end: str,
) -> dict[str, dict[str, Any]]:
    resolved_rows = conn.execute(
        """
        SELECT resolved_fact_id, fact_code, resolved_value, unit,
               resolution_status, confidence, basis
        FROM resolved_facts
        WHERE company_id = ? AND event_id = ?
        ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
        """,
        (company_id, event_id),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in resolved_rows:
        if row["resolved_value"] is None or row["resolution_status"] != "resolved":
            continue
        out.setdefault(
            row["fact_code"],
            {
                "resolved_fact_id": row["resolved_fact_id"],
                "value": float(row["resolved_value"]),
                "unit": row["unit"],
                "confidence": row["confidence"],
            },
        )
    if out:
        return out

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
        out.setdefault(
            row["value_code"],
            {
                "resolved_fact_id": hashlib.sha256(
                    f"{company_id}:{event_id}:{row['value_code']}".encode()
                ).hexdigest(),
                "value": value,
                "unit": row["unit"],
            },
        )
    return out


def _dim_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row.get("segment") or "", row.get("geography") or "")


def load_presentation_metrics_by_key(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT metric_id, metric_code, value, unit, formula, segment, geography
        FROM metrics
        WHERE company_id = ? AND event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row["metric_code"], []).append(
            {
                "metric_key": row["metric_code"],
                "metric_id": row["metric_id"],
                "name": row["metric_code"],
                "value": float(row["value"]),
                "unit": row["unit"],
                "category": None,
                "segment": row["segment"],
                "geography": row["geography"],
            }
        )
    return out


def load_presentation_facts_by_key(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    period_end: str,
) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT value_code, value_numeric, value_text, unit, segment, geography
        FROM extracted_values
        WHERE company_id = ? AND period_end = ?
        ORDER BY confidence DESC
        """,
        (company_id, period_end),
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        value: Any = float(row["value_numeric"]) if row["value_numeric"] is not None else row["value_text"]
        out.setdefault(row["value_code"], []).append(
            {
                "fact_key": row["value_code"],
                "value": value,
                "unit": row["unit"],
                "segment": row["segment"],
                "geography": row["geography"],
            }
        )
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
        if spec.get("enabled") is False:
            continue
        rule = spec.get("rule")
        if not rule:
            continue
        metric_keys = rule_metric_keys(rule)
        fact_keys = rule_fact_keys(rule)
        if not metric_keys and not fact_keys:
            continue
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
        supporting_metric_ids = [
            metrics_by_key[key]["metric_id"]
            for key in metric_keys
            if key in metrics_by_key and metrics_by_key[key].get("metric_id")
        ]
        supporting_fact_ids = {
            facts_by_key[key]["resolved_fact_id"]
            for key in fact_keys
            if key in facts_by_key and facts_by_key[key].get("resolved_fact_id")
        }
        for key in metric_keys:
            supporting_fact_ids.update(metrics_by_key.get(key, {}).get("input_fact_ids") or [])
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
                "supporting_metric_ids": supporting_metric_ids,
                "supporting_fact_ids": sorted(supporting_fact_ids),
                "trigger_values": trigger_values,
                "rule_text": format_rule(rule),
            }
        )
    return fired_signals


def presentation_rule_metric_keys(rule: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    if "metric_key" in rule:
        keys.append(rule["metric_key"])
    if "compare_metric_key" in rule:
        keys.append(rule["compare_metric_key"])
    for key in ("all", "any"):
        for child in rule.get(key, []):
            keys.extend(presentation_rule_metric_keys(child))
    return keys


def presentation_rule_fact_keys(rule: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    if "fact_key" in rule:
        keys.append(rule["fact_key"])
    if "compare_fact_key" in rule:
        keys.append(rule["compare_fact_key"])
    for key in ("all", "any"):
        for child in rule.get(key, []):
            keys.extend(presentation_rule_fact_keys(child))
    return keys


def _refs_for_key(
    pool: dict[str, list[dict[str, Any]]],
    key: str,
    dim_key: tuple[str, str] | None,
) -> list[dict[str, Any]]:
    rows = pool.get(key, [])
    if not dim_key:
        company = [row for row in rows if _dim_key(row) == ("", "")]
        return company or rows
    exact = [row for row in rows if _dim_key(row) == dim_key]
    if exact:
        return exact
    segment, geography = dim_key
    segment_only = [row for row in rows if segment and (row.get("segment") or "") == segment]
    if segment_only:
        return segment_only
    geography_only = [row for row in rows if geography and (row.get("geography") or "") == geography]
    if geography_only:
        return geography_only
    company = [row for row in rows if _dim_key(row) == ("", "")]
    return company or rows


def eval_presentation_leaf(
    rule: dict[str, Any],
    *,
    metrics_by_key: dict[str, list[dict[str, Any]]],
    facts_by_key: dict[str, list[dict[str, Any]]],
    dim_key: tuple[str, str] | None = None,
) -> bool:
    if "metric_key" in rule:
        refs = _refs_for_key(metrics_by_key, rule["metric_key"], dim_key)
    elif "fact_key" in rule:
        refs = _refs_for_key(facts_by_key, rule["fact_key"], dim_key)
    else:
        raise ValueError(f"Malformed rule leaf: {rule}")
    if not refs:
        return False
    left = refs[0]["value"]
    if "compare_metric_key" in rule:
        compare_refs = _refs_for_key(metrics_by_key, rule["compare_metric_key"], dim_key)
        if not compare_refs:
            return False
        right = compare_refs[0]["value"]
    elif "compare_fact_key" in rule:
        compare_refs = _refs_for_key(facts_by_key, rule["compare_fact_key"], dim_key)
        if not compare_refs:
            return False
        right = compare_refs[0]["value"]
    else:
        right = rule.get("value")
    op = rule["op"].upper() if isinstance(rule["op"], str) else rule["op"]
    if op not in OPS:
        raise ValueError(f"Unsupported rule operator: {rule['op']}")
    try:
        return bool(OPS[op](left, right))
    except TypeError:
        return False


def eval_presentation_rule(
    rule: dict[str, Any],
    *,
    metrics_by_key: dict[str, list[dict[str, Any]]],
    facts_by_key: dict[str, list[dict[str, Any]]],
    dim_key: tuple[str, str] | None = None,
) -> bool:
    if "all" in rule:
        return all(
            eval_presentation_rule(
                child,
                metrics_by_key=metrics_by_key,
                facts_by_key=facts_by_key,
                dim_key=dim_key,
            )
            for child in rule["all"]
        )
    if "any" in rule:
        return any(
            eval_presentation_rule(
                child,
                metrics_by_key=metrics_by_key,
                facts_by_key=facts_by_key,
                dim_key=dim_key,
            )
            for child in rule["any"]
        )
    if "metric_key" in rule or "fact_key" in rule:
        return eval_presentation_leaf(
            rule,
            metrics_by_key=metrics_by_key,
            facts_by_key=facts_by_key,
            dim_key=dim_key,
        )
    if "semantic_match" in rule:
        text_parts: list[str] = []
        for key in facts_by_key:
            for ref in _refs_for_key(facts_by_key, key, dim_key):
                if ref.get("value") is not None:
                    text_parts.append(str(ref["value"]))
        haystack = " ".join(text_parts).casefold()
        for phrase in rule.get("semantic_match") or []:
            terms = [term for term in str(phrase).casefold().replace("-", " ").split() if term]
            if terms and all(term in haystack for term in terms):
                return True
        return False
    raise ValueError(f"Malformed rule: {rule}")


def format_presentation_rule(rule: dict[str, Any]) -> str:
    if "metric_key" in rule:
        rhs = rule.get("compare_metric_key", rule.get("value"))
        return f"{rule['metric_key']} {rule['op']} {rhs}"
    if "fact_key" in rule:
        rhs = rule.get("compare_fact_key", rule.get("value"))
        return f"{rule['fact_key']} {rule['op']} {rhs}"
    if "all" in rule:
        return " AND ".join(f"({format_presentation_rule(child)})" for child in rule["all"])
    if "any" in rule:
        return " OR ".join(f"({format_presentation_rule(child)})" for child in rule["any"])
    if "semantic_match" in rule:
        return "semantic match: " + ", ".join(rule.get("semantic_match") or [])
    return ""


def rule_has_semantic_match(rule: dict[str, Any]) -> bool:
    if "semantic_match" in rule:
        return True
    return any(
        rule_has_semantic_match(child)
        for group in ("all", "any")
        for child in rule.get(group, [])
    )


def _candidate_dims(
    metric_keys: list[str],
    fact_keys: list[str],
    *,
    metrics_by_key: dict[str, list[dict[str, Any]]],
    facts_by_key: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, str] | None]:
    keys: set[tuple[str, str]] = set()
    for key in metric_keys:
        for row in metrics_by_key.get(key, []):
            dim = _dim_key(row)
            if dim != ("", ""):
                keys.add(dim)
    for key in fact_keys:
        for row in facts_by_key.get(key, []):
            dim = _dim_key(row)
            if dim != ("", ""):
                keys.add(dim)
    return sorted(keys) + [None] if keys else [None]


def evaluate_presentation_signal_rules(
    signals_catalog: dict[str, Any],
    *,
    metrics_by_key: dict[str, list[dict[str, Any]]],
    facts_by_key: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    fired_signals: list[dict[str, Any]] = []
    for code, spec in signals_catalog.items():
        if spec.get("enabled") is False:
            continue
        rule = spec.get("rule")
        if not rule:
            continue
        metric_keys = sorted(set(presentation_rule_metric_keys(rule)))
        fact_keys = sorted(set(presentation_rule_fact_keys(rule)))
        if not metric_keys and not fact_keys and not rule_has_semantic_match(rule):
            continue
        if not all(key in metrics_by_key for key in metric_keys):
            continue
        if not all(key in facts_by_key for key in fact_keys):
            continue
        fired = False
        fired_dim: tuple[str, str] | None = None
        for dim_key in _candidate_dims(
            metric_keys,
            fact_keys,
            metrics_by_key=metrics_by_key,
            facts_by_key=facts_by_key,
        ):
            if eval_presentation_rule(
                rule,
                metrics_by_key=metrics_by_key,
                facts_by_key=facts_by_key,
                dim_key=dim_key,
            ):
                fired = True
                fired_dim = dim_key
                break
        if not fired:
            continue
        trigger_values = {}
        for key in metric_keys:
            refs = _refs_for_key(metrics_by_key, key, fired_dim)
            if refs:
                trigger_values[key] = refs[0]["value"]
        for key in fact_keys:
            refs = _refs_for_key(facts_by_key, key, fired_dim)
            if refs:
                trigger_values[key] = refs[0]["value"]
        segment, geography = fired_dim or ("", "")
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
                "rule_text": format_presentation_rule(rule),
                "segment": segment or None,
                "geography": geography or None,
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
    # Cards reference signals without ON DELETE CASCADE. Remove this derived
    # presentation layer before replacing the event's signals.
    conn.execute(
        "DELETE FROM intelligence_cards WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    conn.execute(
        "DELETE FROM signals WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for signal in fired_signals:
        conn.execute(
            """
            INSERT INTO signals (
                signal_id, company_id, event_id, signal_code, severity,
                direction, supporting_metric_ids, supporting_fact_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dimension_signal_id(
                    company_id,
                    event_id,
                    signal["signal_key"],
                    signal.get("segment"),
                    signal.get("geography"),
                ),
                company_id,
                event_id,
                signal["signal_key"],
                signal["severity"],
                signal["direction"],
                ", ".join(signal.get("supporting_metric_ids") or []),
                ", ".join(signal.get("supporting_fact_ids") or []),
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
    event_type: str = "Financial Results",
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    if event_type in {"Investor Presentation", "Earnings Call Transcript"}:
        signals_catalog = (
            load_presentation_signals_catalog()
            if event_type == "Investor Presentation"
            else load_earnings_call_signals_catalog()
        )
        metrics_by_key = load_presentation_metrics_by_key(
            conn,
            company_id=company_id,
            event_id=event_id,
        )
        facts_by_key = load_presentation_facts_by_key(
            conn,
            company_id=company_id,
            period_end=period_end,
        )
        fired_signals = evaluate_presentation_signal_rules(
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
                "metrics": sum(len(rows) for rows in metrics_by_key.values()),
                "facts": sum(len(rows) for rows in facts_by_key.values()),
                "rules": len(signals_catalog),
            },
        }

    signals_catalog = load_signals_catalog()

    metrics_by_key = load_metrics_by_key(conn, company_id=company_id, event_id=event_id)
    facts_by_key = load_facts_by_key(
        conn,
        company_id=company_id,
        event_id=event_id,
        period_end=period_end,
    )
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
