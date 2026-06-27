"""Metric computation from financial_result_flow.ipynb Step 5."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from metrics_config import settings
from metrics_db import bootstrap_schema
from periods import quarter_end_date

EVAL_SCOPES = ("CURRENT", "PY", "PQ")
UNIT_SCALE = {
    "crore": 1.0,
    "crores": 1.0,
    "cr": 1.0,
    "lakh": 0.01,
    "lakhs": 0.01,
    "lac": 0.01,
    "lacs": 0.01,
    "million": 0.1,
    "mn": 0.1,
    "billion": 100.0,
    "bn": 100.0,
    "thousand": 1e-5,
}
PASS_THROUGH = {"%", "percent", "pct", "bps", "rs", "rs.", "inr", "x", "times", "days"}


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def metric_value_id(company_id: str, event_id: str, metric_key: str) -> str:
    return hashlib.sha256(f"{company_id}:{event_id}:{metric_key}".encode()).hexdigest()


def load_metrics_catalog() -> dict[str, Any]:
    return json.loads((settings.catalog_dir / "metrics.json").read_text(encoding="utf-8"))


def seed_metric_catalog(conn: sqlite3.Connection, metrics_catalog: dict[str, Any]) -> None:
    for code, spec in metrics_catalog.items():
        metric_id = hashlib.sha256(code.encode()).hexdigest()
        formula_payload = json.dumps(
            {
                "formula": spec.get("formula"),
                "inputs": spec.get("inputs") or [],
                "category": spec.get("category"),
            }
        )
        conn.execute(
            """
            INSERT INTO metrics (id, metric_code, name, formula, unit, description)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(metric_code) DO UPDATE SET
                name = excluded.name, formula = excluded.formula,
                unit = excluded.unit, description = excluded.description
            """,
            (
                metric_id,
                code,
                spec.get("name", code),
                formula_payload,
                spec.get("unit"),
                spec.get("category"),
            ),
        )
    conn.commit()


def prior_year_end(period_quarter: int, period_fy_start: int) -> str:
    return quarter_end_date(period_quarter, period_fy_start - 1).isoformat()


def prior_quarter_end(period_quarter: int, period_fy_start: int) -> str:
    if period_quarter == 1:
        quarter, fy_start = 4, period_fy_start - 1
    else:
        quarter, fy_start = period_quarter - 1, period_fy_start
    return quarter_end_date(quarter, fy_start).isoformat()


def load_facts(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    period_end: str,
) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT value_code, value_numeric, unit FROM extracted_values
        WHERE company_id = ? AND period_end = ?
        ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
        """,
        (company_id, period_end),
    ).fetchall()
    pool: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["value_numeric"] is None:
            continue
        pool.setdefault(
            row["value_code"],
            {"value": float(row["value_numeric"]), "unit": row["unit"]},
        )
    return pool


def crore_scale(unit: Any) -> float | None:
    if not unit:
        return None
    normalized = str(unit).strip().lower()
    if normalized in PASS_THROUGH:
        return None
    return UNIT_SCALE.get(normalized)


def fact_scopes(inputs: list[dict[str, Any]]) -> set[str]:
    return {
        inp.get("scope", "CURRENT").upper()
        for inp in inputs
        if "fact_key" in inp
    }


def resolve_inputs(
    inputs: list[dict[str, Any]],
    *,
    eval_scope: str,
    scope_pools: dict[str, dict[str, dict[str, Any]]],
    runtime_params: dict[str, float],
    metrics_by_scope: dict[str, dict[str, float]] | None = None,
) -> dict[str, float] | None:
    metrics_by_scope = metrics_by_scope or {}
    use_comparable = len(fact_scopes(inputs)) > 1
    resolved: dict[str, float] = {}
    for inp in inputs:
        if "runtime_parameter" in inp:
            value = runtime_params.get(inp["runtime_parameter"])
            if value is None:
                return None
            resolved[inp["var"]] = value
            continue

        if "metric_key" in inp:
            ref_scope = inp.get("scope", "CURRENT").upper()
            value = metrics_by_scope.get(ref_scope, {}).get(inp["metric_key"])
            if value is None:
                return None
            resolved[inp["var"]] = value
            continue

        if "fact_key" not in inp:
            return None

        absolute_scope = inp.get("scope", "CURRENT").upper()
        pool_scope = eval_scope.upper() if absolute_scope == "CURRENT" else absolute_scope
        detail = scope_pools.get(pool_scope, {}).get(inp["fact_key"])
        if detail is None:
            if inp.get("optional"):
                resolved[inp["var"]] = 0.0
                continue
            return None

        value = detail["value"]
        if use_comparable:
            scale = crore_scale(detail["unit"])
            if scale is not None:
                value = value * scale
        resolved[inp["var"]] = value
    return resolved


def safe_eval(formula: str, variables: dict[str, float]) -> float | None:
    namespace = {
        "__builtins__": {},
        "min": min,
        "max": max,
        "abs": abs,
        "average": lambda a, b: (a + b) / 2,
        **variables,
    }
    try:
        result = eval(formula, namespace)
    except (ZeroDivisionError, TypeError, NameError):
        return None
    return float(result) if isinstance(result, (int, float)) else None


def input_labels(inputs: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for inp in inputs:
        if "fact_key" in inp:
            labels.append(inp["fact_key"])
        elif "metric_key" in inp:
            labels.append(inp["metric_key"])
    return labels


def compute_metrics(
    metrics_catalog: dict[str, Any],
    *,
    period_quarter: int,
    scope_pools: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    runtime_params = {"annualization_factor": 4.0 / period_quarter}
    metrics_by_scope: dict[str, dict[str, float]] = {scope: {} for scope in EVAL_SCOPES}

    while True:
        progress = False
        for code, spec in metrics_catalog.items():
            inputs_spec = spec.get("inputs") or []
            for eval_scope in EVAL_SCOPES:
                if code in metrics_by_scope[eval_scope]:
                    continue
                variables = resolve_inputs(
                    inputs_spec,
                    eval_scope=eval_scope,
                    scope_pools=scope_pools,
                    runtime_params=runtime_params,
                    metrics_by_scope=metrics_by_scope,
                )
                if variables is None:
                    continue
                value = safe_eval(spec["formula"], variables)
                if value is None:
                    continue
                metrics_by_scope[eval_scope][code] = round(value, 2)
                progress = True
        if not progress:
            break

    computed_metrics: list[dict[str, Any]] = []
    for code, spec in metrics_catalog.items():
        value = metrics_by_scope["CURRENT"].get(code)
        if value is None:
            continue
        computed_metrics.append(
            {
                "metric_key": code,
                "name": spec.get("name", code),
                "value": value,
                "unit": spec.get("unit"),
                "category": spec.get("category"),
                "formula": spec["formula"],
                "inputs": sorted(set(input_labels(spec.get("inputs") or []))),
            }
        )
    return computed_metrics, metrics_by_scope


def persist_metric_values(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_end: str,
    computed_metrics: list[dict[str, Any]],
) -> None:
    conn.execute(
        "DELETE FROM metric_values WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for metric in computed_metrics:
        metric_row = conn.execute(
            "SELECT id FROM metrics WHERE metric_code = ?",
            (metric["metric_key"],),
        ).fetchone()
        if not metric_row:
            continue
        conn.execute(
            """
            INSERT INTO metric_values (
                id, company_id, event_id, metric_id, metric_value,
                period_start, period_end, calculation_data
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                metric_value_id(company_id, event_id, metric["metric_key"]),
                company_id,
                event_id,
                metric_row["id"],
                metric["value"],
                period_end,
                json.dumps(
                    {
                        "unit": metric["unit"],
                        "formula": metric["formula"],
                        "inputs": metric["inputs"],
                    }
                ),
            ),
        )
    conn.commit()


def compute_and_persist_metrics(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    company_id: str,
    event_id: str,
    period_quarter: int,
    period_fy_start: int,
    period_end: str,
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    metrics_catalog = load_metrics_catalog()
    seed_metric_catalog(conn, metrics_catalog)

    facts_current = load_facts(conn, company_id=company_id, period_end=period_end)
    facts_py = load_facts(
        conn,
        company_id=company_id,
        period_end=prior_year_end(period_quarter, period_fy_start),
    )
    facts_pq = load_facts(
        conn,
        company_id=company_id,
        period_end=prior_quarter_end(period_quarter, period_fy_start),
    )
    scope_pools = {"CURRENT": facts_current, "PY": facts_py, "PQ": facts_pq}

    computed_metrics, metrics_by_scope = compute_metrics(
        metrics_catalog,
        period_quarter=period_quarter,
        scope_pools=scope_pools,
    )
    persist_metric_values(
        conn,
        company_id=company_id,
        event_id=event_id,
        period_end=period_end,
        computed_metrics=computed_metrics,
    )

    return {
        "metrics": computed_metrics,
        "metrics_by_scope": metrics_by_scope,
        "scope_counts": {
            "current_facts": len(facts_current),
            "prior_year_facts": len(facts_py),
            "prior_quarter_facts": len(facts_pq),
        },
    }
