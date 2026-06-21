"""Evaluate catalog metrics and signal rules from stored fact values."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Mapping

from catalog_loader import Catalog, canonical_fact_key, fact_lookup_keys, get_catalog

# Multipliers from stored unit → crore-equivalent for cross-period comparison.
# Ingestion keeps document-faithful values; conversion happens only at metric time.
_UNIT_SCALE_TO_CRORE: dict[str, float] = {
    "crore": 1.0,
    "crores": 1.0,
    "cr": 1.0,
    "cr.": 1.0,
    "inr cr": 1.0,
    "inr_cr": 1.0,
    "inr crore": 1.0,
    "inr crores": 1.0,
    "lakh": 0.01,
    "lakhs": 0.01,
    "lac": 0.01,
    "lacs": 0.01,
    "inr lakh": 0.01,
    "thousand": 1e-5,
    "thousands": 1e-5,
    "k": 1e-5,
    "million": 0.1,
    "millions": 0.1,
    "mn": 0.1,
    "billion": 100.0,
    "billions": 100.0,
    "bn": 100.0,
    "rupees": 1e-7,
    "rupee": 1e-7,
}

_PASS_THROUGH_UNITS = frozenset(
    {"%", "percent", "pct", "bps", "rs", "rs.", "inr", "x", "times", "days", "day"}
)

# Legacy v2 notebook / mapper metric keys kept for backward compatibility.
LEGACY_METRIC_ALIASES: dict[str, str] = {
    "revenue_yoy_pct": "revenue_yoy_growth",
    "revenue_qoq_pct": "revenue_qoq_growth",
    "net_profit_yoy_pct": "pat_growth_yoy",
    "net_profit_qoq_pct": "pat_growth_qoq",
    "ebitda_yoy_pct": "ebitda_growth_yoy",
    "ebitda_qoq_pct": "ebitda_qoq_growth",
    "operating_profit_yoy_pct": "operating_profit_yoy_growth",
    "operating_profit_qoq_pct": "operating_profit_qoq_growth",
}

_SEVERITY_TO_V2 = {
    "CRITICAL": "watch",
    "HIGH": "watch",
    "MEDIUM": "watch",
    "LOW": "info",
}


class FormulaError(ValueError):
    pass


_ALLOWED_FUNCS: dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
}

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def evaluate_formula(formula: str, inputs: Mapping[str, Any]) -> float | None:
    if not formula or not formula.strip():
        raise FormulaError("Empty formula")
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Could not parse formula: {exc}") from exc

    referenced: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"Disallowed node {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise FormulaError("Only min/max/abs calls are allowed")
            if node.keywords:
                raise FormulaError("Keyword arguments are not allowed")
        if isinstance(node, ast.Name):
            referenced.add(node.id)

    resolved: dict[str, float | int | None] = {}
    for name in referenced:
        if name in _ALLOWED_FUNCS:
            continue
        if name not in inputs:
            raise FormulaError(f"Unknown input `{name}`")
        resolved[name] = inputs[name]

    if any(v is None for v in resolved.values()):
        return None

    namespace: dict[str, Any] = {**_ALLOWED_FUNCS, **resolved}
    try:
        result = _eval_node(tree.body, namespace)
    except ZeroDivisionError:
        return None
    if isinstance(result, bool):
        return float(result)
    if isinstance(result, (int, float)):
        return float(result)
    raise FormulaError(f"Non-numeric result: {type(result).__name__}")


def _eval_node(node: ast.AST, ns: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return ns[node.id]
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ns)
        right = _eval_node(node.right, ns)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left**right
        raise FormulaError(f"Unsupported binop {type(node.op).__name__}")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, ns)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand
        raise FormulaError(f"Unsupported unary {type(node.op).__name__}")
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            value = True
            for child in node.values:
                value = _eval_node(child, ns)
                if not value:
                    return value
            return value
        if isinstance(node.op, ast.Or):
            value = False
            for child in node.values:
                value = _eval_node(child, ns)
                if value:
                    return value
            return value
        raise FormulaError(f"Unsupported boolop {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ns)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, ns)
            if isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            else:
                raise FormulaError(f"Unsupported compare {type(op).__name__}")
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _eval_node(node.body, ns) if _eval_node(node.test, ns) else _eval_node(node.orelse, ns)
    if isinstance(node, ast.Call):
        func = _ALLOWED_FUNCS[node.func.id]  # type: ignore[union-attr]
        args = [_eval_node(arg, ns) for arg in node.args]
        return func(*args)
    raise FormulaError(f"Unsupported node {type(node).__name__}")


def _normalize_unit_key(unit: str | None) -> str | None:
    if not unit:
        return None
    return unit.strip().lower()


def crore_equivalent_scale(unit: str | None) -> float | None:
    """Return multiplier to express a stored value in crore-equivalent."""
    key = _normalize_unit_key(unit)
    if not key:
        return None
    if key in _PASS_THROUGH_UNITS:
        return None
    if key in _UNIT_SCALE_TO_CRORE:
        return _UNIT_SCALE_TO_CRORE[key]
    if key.endswith(" cr") or key.endswith(" crore") or key.endswith(" crores"):
        return 1.0
    if "lakh" in key or "lac" in key:
        return 0.01
    return None


def to_crore_equivalent(value: float, unit: str | None) -> float:
    """Convert an amount to crore-equivalent for cross-period math (read-time only)."""
    scale = crore_equivalent_scale(unit)
    if scale is None:
        return value
    return value * scale


@dataclass
class ScopeContext:
    current: dict[str, float]
    prior_year: dict[str, float]
    prior_quarter: dict[str, float]
    current_units: dict[str, str | None] = field(default_factory=dict)
    prior_year_units: dict[str, str | None] = field(default_factory=dict)
    prior_quarter_units: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def from_fact_details(
        cls,
        current: dict[str, dict[str, Any]],
        prior_year: dict[str, dict[str, Any]],
        prior_quarter: dict[str, dict[str, Any]],
    ) -> ScopeContext:
        def _split(
            details: dict[str, dict[str, Any]],
        ) -> tuple[dict[str, float], dict[str, str | None]]:
            values: dict[str, float] = {}
            units: dict[str, str | None] = {}
            for key, detail in details.items():
                values[key] = float(detail["numeric_value"])
                units[key] = detail.get("unit")
            return values, units

        cur_v, cur_u = _split(current)
        py_v, py_u = _split(prior_year)
        pq_v, pq_u = _split(prior_quarter)
        return cls(
            current=cur_v,
            prior_year=py_v,
            prior_quarter=pq_v,
            current_units=cur_u,
            prior_year_units=py_u,
            prior_quarter_units=pq_u,
        )

    def _pool(self, scope: str) -> dict[str, float] | None:
        return {
            "CURRENT": self.current,
            "PY": self.prior_year,
            "PQ": self.prior_quarter,
        }.get(scope.upper())

    def _unit_pool(self, scope: str) -> dict[str, str | None]:
        return {
            "CURRENT": self.current_units,
            "PY": self.prior_year_units,
            "PQ": self.prior_quarter_units,
        }.get(scope.upper(), {})

    def fact_value(self, fact_key: str, scope: str) -> float | None:
        pool = self._pool(scope)
        if pool is None:
            return None
        for key in fact_lookup_keys(fact_key):
            if key in pool:
                return pool[key]
        return None

    def fact_unit(self, fact_key: str, scope: str) -> str | None:
        pool = self._unit_pool(scope)
        for key in fact_lookup_keys(fact_key):
            if key in pool:
                return pool[key]
        return None

    def comparable_fact_value(self, fact_key: str, scope: str) -> float | None:
        """Document-faithful value adjusted to crore-equivalent for formula comparison."""
        value = self.fact_value(fact_key, scope)
        if value is None:
            return None
        return to_crore_equivalent(value, self.fact_unit(fact_key, scope))


def _resolve_metric_inputs(
    ctx: ScopeContext, inputs: list[dict[str, Any]]
) -> dict[str, float | None]:
    """Resolve formula variables, aligning cross-scope amounts via stored units."""
    scopes = {inp["scope"].upper() for inp in inputs}
    use_comparable = len(scopes) > 1
    out: dict[str, float | None] = {}
    for inp in inputs:
        fact_key = inp["fact_key"]
        scope = inp["scope"]
        if use_comparable:
            out[inp["var"]] = ctx.comparable_fact_value(fact_key, scope)
        else:
            out[inp["var"]] = ctx.fact_value(fact_key, scope)
    return out


def catalog_metric_key(metric_key: str) -> str:
    """Map legacy notebook/mapper metric keys to catalog metric codes."""
    return LEGACY_METRIC_ALIASES.get(metric_key, metric_key)


def compute_catalog_metrics(
    ctx: ScopeContext,
    *,
    period_label: str,
    raw_details: dict[str, dict[str, Any]] | None = None,
    catalog: Catalog | None = None,
) -> list[dict[str, Any]]:
    catalog = catalog or get_catalog()
    metrics: list[dict[str, Any]] = []

    if raw_details:
        for storage_key, detail in raw_details.items():
            canonical = canonical_fact_key(storage_key) or storage_key
            metrics.append(
                {
                    "fact_key": canonical,
                    "value": detail["numeric_value"],
                    "unit": detail.get("unit"),
                    "derivation": "raw",
                    "inputs": [canonical],
                    "evidence": detail.get("evidence"),
                    "source_document_id": detail.get("source_document_id"),
                    "period": period_label,
                    "source": "filing",
                }
            )

    computed: dict[str, float] = {}
    for code, spec in catalog.metrics.items():
        inputs_spec = spec.get("inputs") or []
        input_vars = _resolve_metric_inputs(ctx, inputs_spec)
        input_facts = [inp["fact_key"] for inp in inputs_spec]
        try:
            value = evaluate_formula(spec["formula"], input_vars)
        except FormulaError:
            continue
        if value is None:
            continue
        rounded = round(value, 2)
        computed[code] = rounded
        metrics.append(
            {
                "metric_key": code,
                "value": rounded,
                "unit": spec.get("unit"),
                "derivation": "formula",
                "inputs": sorted(set(input_facts)),
                "period": period_label,
                "source": "catalog",
                "formula_evaluated": spec["formula"],
            }
        )

    for legacy_key, canonical in LEGACY_METRIC_ALIASES.items():
        if canonical not in computed:
            continue
        metrics.append(
            {
                "metric_key": legacy_key,
                "value": computed[canonical],
                "unit": catalog.metrics[canonical].get("unit"),
                "derivation": "alias",
                "inputs": [canonical],
                "period": period_label,
                "source": "catalog",
            }
        )

    return metrics


def _rule_metric_keys(rule: dict[str, Any]) -> list[str]:
    if "metric_key" in rule:
        return [rule["metric_key"]]
    keys: list[str] = []
    for key in ("all", "any"):
        if key in rule:
            for child in rule[key]:
                keys.extend(_rule_metric_keys(child))
    return keys


def rule_leaves(rule: dict[str, Any]) -> list[dict[str, Any]]:
    if "metric_key" in rule:
        return [rule]
    leaves: list[dict[str, Any]] = []
    for key in ("all", "any"):
        if key in rule:
            for child in rule[key]:
                leaves.extend(rule_leaves(child))
    return leaves


def format_rule_text(rule: dict[str, Any]) -> str:
    if "metric_key" in rule:
        return f"{rule['metric_key']} {rule['op']} {rule['value']}"
    if "all" in rule:
        return " AND ".join(f"({format_rule_text(child)})" for child in rule["all"])
    if "any" in rule:
        return " OR ".join(f"({format_rule_text(child)})" for child in rule["any"])
    raise ValueError(f"Malformed rule: {rule}")


def _eval_leaf(metric: str, op: str, threshold: float, by_key: dict[str, dict[str, Any]]) -> bool:
    row = by_key.get(metric)
    if row is None:
        return False
    value = row["value"]
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    if op == "!=":
        return value != threshold
    raise ValueError(f"Unsupported operator: {op}")


def _eval_rule(rule: dict[str, Any], by_key: dict[str, dict[str, Any]]) -> bool:
    if "all" in rule:
        return all(_eval_rule(child, by_key) for child in rule["all"])
    if "any" in rule:
        return any(_eval_rule(child, by_key) for child in rule["any"])
    if "metric_key" in rule:
        return _eval_leaf(rule["metric_key"], rule["op"], rule["value"], by_key)
    raise ValueError(f"Malformed rule: {rule}")


def evaluate_catalog_signals(
    metrics: list[dict[str, Any]],
    *,
    catalog: Catalog | None = None,
) -> list[dict[str, Any]]:
    catalog = catalog or get_catalog()
    by_key = {m["metric_key"]: m for m in metrics if "metric_key" in m}
    signals: list[dict[str, Any]] = []

    for code, spec in catalog.signals.items():
        rule = spec.get("rule")
        if not rule:
            continue
        try:
            if not _eval_rule(rule, by_key):
                continue
        except (ValueError, KeyError, TypeError):
            continue

        metric_keys = _rule_metric_keys(rule)
        rationale = spec.get("description", "")
        for mk in metric_keys:
            row = by_key.get(mk)
            if row is not None:
                rationale = f"{rationale} ({mk}={row['value']})"
                break

        signals.append(
            {
                "signal_key": code,
                "severity": _SEVERITY_TO_V2.get(spec.get("severity", "MEDIUM"), "info"),
                "headline": spec.get("name", code),
                "rationale": rationale.strip(),
                "metric_keys": metric_keys,
                "category": spec.get("category"),
                "direction": spec.get("direction"),
                "rule": rule,
                "rule_text": format_rule_text(rule),
            }
        )

    if not signals:
        signals.append(
            {
                "signal_key": "no_material_change",
                "severity": "info",
                "headline": "No material signals this run",
                "rationale": "Catalog rules did not fire",
                "metric_keys": [],
                "category": "general",
                "direction": "NEUTRAL",
            }
        )

    return signals
