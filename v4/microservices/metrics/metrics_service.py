"""Metric computation from financial_result_flow.ipynb Step 5."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date, datetime
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
PASS_THROUGH = {
    "%",
    "percent",
    "pct",
    "bps",
    "pp",
    "rs",
    "rs.",
    "inr",
    "x",
    "times",
    "days",
    "count",
    "company_reported",
}


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def metric_value_id(
    company_id: str,
    event_id: str,
    metric_key: str,
    segment: str | None = None,
    geography: str | None = None,
) -> str:
    return hashlib.sha256(
        f"{company_id}:{event_id}:{metric_key}:{segment or ''}:{geography or ''}".encode()
    ).hexdigest()


def fallback_fact_id(company_id: str, event_id: str, fact_key: str) -> str:
    return hashlib.sha256(f"{company_id}:{event_id}:{fact_key}".encode()).hexdigest()


def load_metrics_catalog() -> dict[str, Any]:
    return json.loads((settings.catalog_dir / "metrics.json").read_text(encoding="utf-8"))


def load_presentation_metrics_catalog() -> dict[str, Any]:
    path = settings.catalog_dir / "investor_presentation_metrics.json"
    if not path.exists():
        path = settings.catalog_dir / "investor_presentation" / "presentation_metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_earnings_call_metrics_catalog() -> dict[str, Any]:
    path = settings.catalog_dir / "earnings_call_metrics.json"
    if not path.exists():
        path = settings.catalog_dir / "earnings-call" / "earnings_call_metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
    event_id: str | None = None,
    period_end: str,
    basis: str | None = None,
) -> dict[str, dict[str, Any]]:
    if event_id and basis is None:
        resolved_rows = conn.execute(
            """
            SELECT resolved_fact_id, fact_code, resolved_value, unit,
                   resolution_status, confidence
            FROM resolved_facts
            WHERE company_id = ? AND event_id = ?
            """,
            (company_id, event_id),
        ).fetchall()
        resolved: dict[str, dict[str, Any]] = {}
        for row in resolved_rows:
            if row["resolved_value"] is None or row["resolution_status"] == "conflict_needs_review":
                continue
            resolved.setdefault(
                row["fact_code"],
                {
                    "value": float(row["resolved_value"]),
                    "unit": row["unit"],
                    "resolved_fact_id": row["resolved_fact_id"],
                    "confidence": row["confidence"],
                },
            )
        if resolved:
            return resolved

    basis_filter = " AND basis = ?" if basis else ""
    params: tuple[Any, ...] = (company_id, period_end, basis) if basis else (company_id, period_end)
    rows = conn.execute(
        f"""
        SELECT event_id, value_code, value_numeric, unit FROM extracted_values
        WHERE company_id = ? AND period_end = ?
        {basis_filter}
        ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
        """,
        params,
    ).fetchall()
    pool: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["value_numeric"] is None:
            continue
        pool.setdefault(
            row["value_code"],
            {
                "value": float(row["value_numeric"]),
                "unit": row["unit"],
                "resolved_fact_id": fallback_fact_id(
                    company_id,
                    row["event_id"] or event_id or period_end,
                    row["value_code"],
                ),
            },
        )
    return pool


def _dimension_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row.get("segment") or "", row.get("geography") or "")


def _rows_to_pool(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    pool: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        pool.setdefault(row["fact_key"], []).append(row)
    for fact_rows in pool.values():
        fact_rows.sort(
            key=lambda row: (row.get("period_end") or "", row.get("confidence") or 0),
            reverse=True,
        )
    return pool


def _row_from_db(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "fact_key": row["value_code"],
        "value": float(row["value_numeric"]) if row["value_numeric"] is not None else row["value_text"],
        "numeric_value": float(row["value_numeric"]) if row["value_numeric"] is not None else None,
        "value_text": row["value_text"],
        "unit": row["unit"],
        "basis": row["basis"],
        "segment": row["segment"],
        "geography": row["geography"],
        "product": row["product"] if "product" in row.keys() else None,
        "channel": row["channel"] if "channel" in row.keys() else None,
        "project": row["project"] if "project" in row.keys() else None,
        "customer_type": row["customer_type"] if "customer_type" in row.keys() else None,
        "metric_context": row["metric_context"] if "metric_context" in row.keys() else None,
        "scope_level": row["scope_level"] if "scope_level" in row.keys() else None,
        "scope_name": row["scope_name"] if "scope_name" in row.keys() else None,
        "period_end": row["period_end"],
        "source_text": row["source_text"],
        "confidence": float(row["confidence"] or 0),
    }


def load_presentation_fact_rows(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_end: str,
    scope: str,
    period_quarter: int,
    period_fy_start: int,
) -> dict[str, list[dict[str, Any]]]:
    scope = scope.upper()
    if scope in {"CURRENT", "CUMULATIVE", "YTD", "YTD_CURRENT", "TARGET_PERIOD_ACTUAL"}:
        rows = conn.execute(
            """
            SELECT *
            FROM extracted_values
            WHERE company_id = ? AND period_end = ?
            ORDER BY confidence DESC
            """,
            (company_id, period_end),
        ).fetchall()
    elif scope in {"CURRENT_DISCLOSURE", "CALL", "PREPARED_REMARKS", "Q_AND_A"}:
        rows = conn.execute(
            """
            SELECT *
            FROM extracted_values
            WHERE company_id = ? AND event_id = ?
            ORDER BY confidence DESC
            """,
            (company_id, event_id),
        ).fetchall()
    elif scope in {"CONSOLIDATED_CURRENT", "STANDALONE_CURRENT"}:
        basis = "consolidated" if scope == "CONSOLIDATED_CURRENT" else "standalone"
        rows = conn.execute(
            """
            SELECT *
            FROM extracted_values
            WHERE company_id = ? AND period_end = ? AND lower(basis) = ?
            ORDER BY confidence DESC
            """,
            (company_id, period_end, basis),
        ).fetchall()
    elif scope == "PY":
        rows = conn.execute(
            """
            SELECT *
            FROM extracted_values
            WHERE company_id = ? AND period_end = ?
            ORDER BY confidence DESC
            """,
            (company_id, prior_year_end(period_quarter, period_fy_start)),
        ).fetchall()
    elif scope == "PQ":
        rows = conn.execute(
            """
            SELECT *
            FROM extracted_values
            WHERE company_id = ? AND period_end = ?
            ORDER BY confidence DESC
            """,
            (company_id, prior_quarter_end(period_quarter, period_fy_start)),
        ).fetchall()
    elif scope in {"PREVIOUS_DISCLOSURE", "PREVIOUS_CALL", "ORIGINAL_GUIDANCE"}:
        rows = conn.execute(
            """
            SELECT *
            FROM extracted_values
            WHERE company_id = ? AND period_end < ?
            ORDER BY period_end DESC, confidence DESC
            """,
            (company_id, period_end),
        ).fetchall()
    elif scope == "ROLLING_CALL_WINDOW":
        rows = conn.execute(
            """
            SELECT ev.*
            FROM extracted_values ev
            JOIN events e ON e.id = ev.event_id
            WHERE ev.company_id = ? AND ev.period_end <= ?
              AND lower(e.event_type) IN (
                  'earnings call transcript', 'earnings call', 'concall transcript'
              )
            ORDER BY ev.period_end DESC, ev.confidence DESC
            """,
            (company_id, period_end),
        ).fetchall()
    else:
        rows = []
    return _rows_to_pool([_row_from_db(row) for row in rows])


def crore_scale(unit: Any) -> float | None:
    if not unit:
        return None
    normalized = str(unit).strip().lower()
    if normalized in PASS_THROUGH or "per" in normalized:
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


def input_fact_ids(
    inputs: list[dict[str, Any]],
    *,
    eval_scope: str,
    scope_pools: dict[str, dict[str, dict[str, Any]]],
) -> list[str]:
    ids: list[str] = []
    for inp in inputs:
        if "fact_key" not in inp:
            continue
        absolute_scope = inp.get("scope", "CURRENT").upper()
        pool_scope = eval_scope.upper() if absolute_scope == "CURRENT" else absolute_scope
        detail = scope_pools.get(pool_scope, {}).get(inp["fact_key"])
        if detail and detail.get("resolved_fact_id"):
            ids.append(str(detail["resolved_fact_id"]))
    return sorted(set(ids))


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
                "input_fact_ids": input_fact_ids(
                    spec.get("inputs") or [],
                    eval_scope="CURRENT",
                    scope_pools=scope_pools,
                ),
            }
        )
    return computed_metrics, metrics_by_scope


def _presentation_candidate_rows(
    inp: dict[str, Any],
    *,
    scope_pools: dict[str, dict[str, list[dict[str, Any]]]],
    dim_key: tuple[str, str] | None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    pool_scope = (scope or inp.get("scope", "CURRENT")).upper()
    rows = scope_pools.get(pool_scope, {}).get(inp["fact_key"], [])
    if not dim_key:
        return [row for row in rows if row.get("numeric_value") is not None or row.get("value_text")]
    segment, geography = dim_key
    exact = [row for row in rows if _dimension_key(row) == dim_key]
    if exact:
        return exact
    segment_only = [row for row in rows if segment and (row.get("segment") or "") == segment]
    if segment_only:
        return segment_only
    geography_only = [row for row in rows if geography and (row.get("geography") or "") == geography]
    if geography_only:
        return geography_only
    company_level = [row for row in rows if _dimension_key(row) == ("", "")]
    return company_level or rows


def _numeric_value(row: dict[str, Any], comparable: bool) -> float | None:
    value = row.get("numeric_value")
    if value is None:
        return None
    if comparable:
        scale = crore_scale(row.get("unit"))
        if scale is not None:
            value *= scale
    return float(value)


def _row_value(row: dict[str, Any], comparable: bool = False) -> Any:
    numeric = _numeric_value(row, comparable)
    if numeric is not None:
        return numeric
    value = row.get("value_text")
    if value is None:
        value = row.get("value")
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lower() in {"true", "yes"}:
            return True
        if normalized.lower() in {"false", "no"}:
            return False
        return normalized
    return value


def _parse_dateish(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%B %Y", "%b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def date_diff_days(current_value: Any, previous_value: Any) -> float | None:
    current = _parse_dateish(current_value)
    previous = _parse_dateish(previous_value)
    if current is None or previous is None:
        return None
    return float((current - previous).days)


def resolve_presentation_inputs(
    inputs: list[dict[str, Any]],
    *,
    scope_pools: dict[str, dict[str, list[dict[str, Any]]]],
    dim_key: tuple[str, str] | None = None,
    formula_type: str = "FORMULA",
    period_quarter: int,
) -> dict[str, Any] | None:
    comparable = len(fact_scopes(inputs)) > 1
    resolved: dict[str, Any] = {}
    for inp in inputs:
        if "constant" in inp:
            resolved[inp["var"]] = inp["constant"]
            continue
        if "runtime_parameter" in inp:
            if inp["runtime_parameter"] == "annualization_factor":
                resolved[inp["var"]] = 4.0 / period_quarter
                continue
            return None
        if "fact_key" not in inp:
            return None
        rows = _presentation_candidate_rows(inp, scope_pools=scope_pools, dim_key=dim_key)
        if not rows:
            if inp.get("optional"):
                resolved[inp["var"]] = 0.0
                continue
            return None
        if formula_type == "AGGREGATION" and inp.get("var") != "revenue":
            values = [_numeric_value(row, comparable) for row in rows]
            values = [value for value in values if value is not None]
            if not values:
                return None
            resolved[inp["var"]] = values
        elif formula_type == "DATE":
            resolved[inp["var"]] = rows[0].get("value_text") or rows[0].get("value")
        else:
            value = _numeric_value(rows[0], comparable)
            if value is None:
                return None
            resolved[inp["var"]] = value
    return resolved


def safe_eval_presentation(formula: str, variables: dict[str, Any]) -> float | None:
    def values(value: Any) -> list[Any]:
        if isinstance(value, list):
            return [item for item in value if item is not None]
        return [] if value is None else [value]

    def count_eq(source: Any, expected: Any) -> int:
        target = str(expected).upper()
        return sum(str(item).upper() == target for item in values(source))

    def count_in(source: Any, expected: Any) -> int:
        targets = {str(item).upper() for item in values(expected)}
        return sum(str(item).upper() in targets for item in values(source))

    def count_true(source: Any) -> int:
        return sum(
            item is True
            or (isinstance(item, (int, float)) and item != 0)
            or str(item).strip().lower() in {"true", "yes", "1"}
            for item in values(source)
        )

    def weighted_mean(source: Any) -> float:
        polarity = {
            "POSITIVE": 1.0,
            "NEUTRAL": 0.0,
            "MIXED": 0.0,
            "CAUTIOUS": -0.5,
            "NEGATIVE": -1.0,
        }
        numbers = [
            float(item) if isinstance(item, (int, float)) else polarity.get(str(item).upper())
            for item in values(source)
        ]
        valid = [item for item in numbers if item is not None]
        return sum(valid) / len(valid) if valid else 0.0

    def repeated_count(source: Any) -> int:
        counts: dict[str, int] = {}
        for item in values(source):
            key = str(item).strip().casefold()
            counts[key] = counts.get(key, 0) + 1
        return sum(count > 1 for count in counts.values())

    def top_share(source: Any) -> float:
        items = [str(item).strip().casefold() for item in values(source)]
        if not items:
            return 0.0
        counts = {item: items.count(item) for item in set(items)}
        return max(counts.values()) / len(items) * 100

    def support_rate(primary: Any, secondary: Any) -> float:
        left, right = values(primary), values(secondary)
        total = max(len(left), len(right))
        if not total:
            return 0.0
        supported = max(count_true(left), count_true(right))
        return supported / total * 100

    namespace = {
        "__builtins__": {},
        "min": min,
        "max": max,
        "abs": abs,
        "sum": sum,
        "math": math,
        "average": lambda a, b: (a + b) / 2,
        "sum_by_dimension": lambda values: sum(values) if isinstance(values, list) else values,
        "max_by_dimension": lambda values: max(values) if isinstance(values, list) and values else values,
        "date_diff_days": date_diff_days,
        "count": lambda source: len(values(source)),
        "count_eq": count_eq,
        "count_in": count_in,
        "count_true": count_true,
        "count_distinct": lambda source: len({str(item).strip().casefold() for item in values(source)}),
        "weighted_mean": weighted_mean,
        "repeated_count": repeated_count,
        "top_share": top_share,
        "support_rate": support_rate,
        **variables,
    }
    try:
        result = eval(formula, namespace)
    except (ZeroDivisionError, TypeError, NameError, ValueError, SyntaxError, OverflowError):
        return None
    return float(result) if isinstance(result, (int, float)) else None


def _candidate_dimension_keys(
    spec: dict[str, Any],
    *,
    scope_pools: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[tuple[str, str] | None]:
    if not spec.get("preserve_dimensions"):
        return [None]
    keys: set[tuple[str, str]] = set()
    for inp in spec.get("inputs") or []:
        if "fact_key" not in inp:
            continue
        scope = inp.get("scope", "CURRENT").upper()
        if scope not in {"CURRENT", "CURRENT_DISCLOSURE", "CUMULATIVE", "YTD"}:
            continue
        for row in scope_pools.get(scope, {}).get(inp["fact_key"], []):
            key = _dimension_key(row)
            if key != ("", ""):
                keys.add(key)
    return sorted(keys) if keys else [None]


def compute_presentation_metrics(
    metrics_catalog: dict[str, Any],
    *,
    period_quarter: int,
    scope_pools: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    current_scope_aliases = {
        "CURRENT",
        "CURRENT_DISCLOSURE",
        "CALL",
        "CUMULATIVE",
        "YTD",
        "YTD_CURRENT",
    }
    runtime_params = {
        "annualization_factor": 4.0 / period_quarter,
        "remaining_quarters": float(max(4 - period_quarter, 1)),
    }
    cache: dict[tuple[str, str, tuple[str, str] | None], float | None] = {}
    active: set[tuple[str, str, tuple[str, str] | None]] = set()

    def compute_one(
        code: str,
        *,
        eval_scope: str = "CURRENT",
        dim_key: tuple[str, str] | None = None,
    ) -> float | None:
        cache_key = (code, eval_scope, dim_key)
        if cache_key in cache:
            return cache[cache_key]
        if cache_key in active:
            return None
        spec = metrics_catalog.get(code)
        if not spec or spec.get("enabled") is False:
            cache[cache_key] = None
            return None

        active.add(cache_key)
        formula_type = str(spec.get("formula_type") or "FORMULA").upper()
        inputs_spec = spec.get("inputs") or []
        comparable = len(fact_scopes(inputs_spec)) > 1
        variables: dict[str, Any] = {}
        valid = True
        for inp in inputs_spec:
            var = inp.get("var")
            if not var:
                valid = False
                break
            if "constant" in inp:
                variables[var] = inp["constant"]
                continue
            if "runtime_parameter" in inp:
                value = runtime_params.get(inp["runtime_parameter"])
                if value is None:
                    valid = False
                    break
                variables[var] = value
                continue
            if "metric_key" in inp:
                requested_scope = str(inp.get("scope") or eval_scope).upper()
                if requested_scope == "CURRENT":
                    requested_scope = eval_scope
                value = compute_one(
                    inp["metric_key"],
                    eval_scope=requested_scope,
                    dim_key=dim_key,
                )
                if value is None:
                    valid = False
                    break
                variables[var] = value
                continue
            if "fact_key" not in inp:
                valid = False
                break

            declared_scope = str(inp.get("scope") or "CURRENT").upper()
            actual_scope = declared_scope
            if eval_scope != "CURRENT" and declared_scope in current_scope_aliases:
                actual_scope = eval_scope
            rows = _presentation_candidate_rows(
                inp,
                scope_pools=scope_pools,
                dim_key=dim_key,
                scope=actual_scope,
            )
            if not rows:
                if inp.get("optional"):
                    variables[var] = [] if formula_type in {"AGGREGATION", "SEMANTIC"} else 0.0
                    continue
                valid = False
                break
            if formula_type in {"AGGREGATION", "SEMANTIC"} and var != "revenue":
                row_values = [_row_value(row, comparable) for row in rows]
                variables[var] = [value for value in row_values if value is not None]
            elif formula_type == "DATE":
                variables[var] = _row_value(rows[0])
            else:
                value = _numeric_value(rows[0], comparable)
                if value is None:
                    valid = False
                    break
                variables[var] = value

        value = safe_eval_presentation(spec.get("formula", ""), variables) if valid else None
        active.remove(cache_key)
        cache[cache_key] = value
        return value

    computed_metrics: list[dict[str, Any]] = []
    for code, spec in metrics_catalog.items():
        if spec.get("enabled") is False:
            continue
        inputs_spec = spec.get("inputs") or []
        formula_type = spec.get("formula_type") or "FORMULA"
        for dim_key in _candidate_dimension_keys(spec, scope_pools=scope_pools):
            value = compute_one(code, dim_key=dim_key)
            if value is None:
                continue
            segment, geography = dim_key or ("", "")
            computed_metrics.append(
                {
                    "metric_key": code,
                    "name": spec.get("name", code),
                    "value": round(value, 2),
                    "unit": spec.get("unit"),
                    "category": spec.get("category"),
                    "formula": spec["formula"],
                    "inputs": sorted(set(input_labels(inputs_spec))),
                    "segment": segment or None,
                    "geography": geography or None,
                    "formula_type": formula_type,
                }
            )
    return computed_metrics


def persist_metric_values(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_end: str,
    computed_metrics: list[dict[str, Any]],
) -> None:
    conn.execute(
        "DELETE FROM metrics WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for metric in computed_metrics:
        conn.execute(
            """
            INSERT INTO metrics (
                metric_id, company_id, event_id, metric_code, value,
                unit, input_fact_ids, formula, segment, geography
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric_value_id(
                    company_id,
                    event_id,
                    metric["metric_key"],
                    metric.get("segment"),
                    metric.get("geography"),
                ),
                company_id,
                event_id,
                metric["metric_key"],
                metric["value"],
                metric["unit"],
                ", ".join(metric.get("input_fact_ids") or []),
                metric["formula"],
                metric.get("segment"),
                metric.get("geography"),
            ),
        )
    conn.commit()


def compute_presentation_coverage_metrics(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    period_end: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT value_code, fact_type, scope_level, segment, confidence
        FROM extracted_values
        WHERE company_id = ? AND event_id = ? AND period_end = ?
        """,
        (company_id, event_id, period_end),
    ).fetchall()
    if not rows:
        return []

    scope_counts: dict[str, int] = {}
    segments: set[str] = set()
    guidance_fact_keys = {
        "revenue_growth_guidance",
        "margin_guidance",
        "management_outlook",
        "segment_outlook",
    }
    guidance_count = 0
    confidence_values: list[float] = []

    for row in rows:
        scope_level = row["scope_level"] or "unknown"
        scope_counts[scope_level] = scope_counts.get(scope_level, 0) + 1
        if row["segment"]:
            segments.add(row["segment"])
        if row["fact_type"] == "guidance" or row["value_code"] in guidance_fact_keys:
            guidance_count += 1
        confidence_values.append(float(row["confidence"] or 0.0))

    average_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    )

    def metric(
        metric_key: str,
        name: str,
        value: float,
        unit: str,
        category: str,
        formula: str,
    ) -> dict[str, Any]:
        return {
            "metric_key": metric_key,
            "name": name,
            "value": round(float(value), 4),
            "unit": unit,
            "category": category,
            "formula": formula,
            "inputs": [],
            "input_fact_ids": [],
        }

    return [
        metric(
            "presentation_fact_count",
            "Presentation Fact Count",
            len(rows),
            "count",
            "coverage",
            "count(scoped_presentation_facts)",
        ),
        metric(
            "presentation_segment_count",
            "Detected Segment Count",
            len(segments),
            "count",
            "coverage",
            "count(distinct segment)",
        ),
        metric(
            "presentation_segment_fact_count",
            "Segment Scoped Fact Count",
            scope_counts.get("segment", 0),
            "count",
            "coverage",
            "count(facts where scope_level='segment')",
        ),
        metric(
            "presentation_company_fact_count",
            "Company Scoped Fact Count",
            scope_counts.get("company", 0),
            "count",
            "coverage",
            "count(facts where scope_level='company')",
        ),
        metric(
            "presentation_unknown_scope_fact_count",
            "Unknown Scope Fact Count",
            scope_counts.get("unknown", 0),
            "count",
            "quality",
            "count(facts where scope_level='unknown')",
        ),
        metric(
            "presentation_average_confidence",
            "Average Presentation Extraction Confidence",
            average_confidence,
            "score",
            "quality",
            "avg(fact.confidence)",
        ),
        metric(
            "presentation_guidance_fact_count",
            "Guidance Fact Count",
            guidance_count,
            "count",
            "content",
            "count(guidance facts)",
        ),
    ]


def compute_and_persist_metrics(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    company_id: str,
    event_id: str,
    period_quarter: int,
    period_fy_start: int,
    period_end: str,
    event_type: str = "Financial Results",
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    if event_type in {"Investor Presentation", "Earnings Call Transcript"}:
        event_catalog = (
            load_presentation_metrics_catalog()
            if event_type == "Investor Presentation"
            else load_earnings_call_metrics_catalog()
        )
        # Event catalogs extend the financial catalog. Event definitions win
        # for shared codes because they use document-specific source facts.
        metrics_catalog = dict(load_metrics_catalog())
        metrics_catalog.update(event_catalog)
        scopes = {
            str(inp.get("scope") or "CURRENT").upper()
            for spec in metrics_catalog.values()
            for inp in spec.get("inputs") or []
            if "fact_key" in inp
        }
        scopes.update({"CURRENT", "PY", "PQ"})
        scope_pools = {
            scope: load_presentation_fact_rows(
                conn,
                company_id=company_id,
                event_id=event_id,
                period_end=period_end,
                scope=scope,
                period_quarter=period_quarter,
                period_fy_start=period_fy_start,
            )
            for scope in scopes
        }
        computed_metrics = compute_presentation_metrics(
            metrics_catalog,
            period_quarter=period_quarter,
            scope_pools=scope_pools,
        )
        if event_type == "Investor Presentation":
            computed_metrics.extend(
                compute_presentation_coverage_metrics(
                    conn,
                    company_id=company_id,
                    event_id=event_id,
                    period_end=period_end,
                )
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
            "metrics_by_scope": {},
            "scope_counts": {
                "current_facts": sum(len(rows) for rows in scope_pools["CURRENT"].values()),
                "prior_year_facts": sum(len(rows) for rows in scope_pools["PY"].values()),
                "prior_quarter_facts": sum(len(rows) for rows in scope_pools["PQ"].values()),
            },
        }

    metrics_catalog = load_metrics_catalog()

    facts_current = load_facts(
        conn,
        company_id=company_id,
        event_id=event_id,
        period_end=period_end,
    )
    facts_py = load_facts(
        conn,
        company_id=company_id,
        event_id=None,
        period_end=prior_year_end(period_quarter, period_fy_start),
    )
    facts_pq = load_facts(
        conn,
        company_id=company_id,
        event_id=None,
        period_end=prior_quarter_end(period_quarter, period_fy_start),
    )
    facts_consolidated = load_facts(
        conn,
        company_id=company_id,
        period_end=period_end,
        basis="consolidated",
    )
    facts_standalone = load_facts(
        conn,
        company_id=company_id,
        period_end=period_end,
        basis="standalone",
    )
    scope_pools = {
        "CURRENT": facts_current,
        "PY": facts_py,
        "PQ": facts_pq,
        "CONSOLIDATED_CURRENT": facts_consolidated,
        "STANDALONE_CURRENT": facts_standalone,
    }

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
