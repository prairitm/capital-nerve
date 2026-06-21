"""Map v2 built metrics/cards into the JSON shapes the v1 frontend expects.

Every function returns plain dicts that mirror an interface in
`v1/frontend/src/api/types.ts`. Keeping the projection in one module makes the
v2 -> v1 contract auditable in a single place.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ids
from .builder import PREFERRED_BASIS, BuiltPeriod, Catalog, Filing, Period

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from catalog_loader import fact_meta_for_mapper, metric_meta_for_mapper, signal_categories, signal_directions  # noqa: E402
from catalog_engine import get_catalog, to_crore_equivalent  # noqa: E402

# --------------------------------------------------------------------- maps

# Legacy computed metric_key aliases -> (v1 metric_code, display name, unit)
_BASE_METRIC_META: dict[str, tuple[str, str, str]] = {
    "ebitda_margin": ("ebitda_margin", "EBITDA Margin", "%"),
    "revenue_yoy_pct": ("revenue_yoy_growth", "Revenue YoY", "%"),
    "revenue_yoy_growth": ("revenue_yoy_growth", "Revenue YoY", "%"),
    "ebitda_yoy_pct": ("ebitda_growth_yoy", "EBITDA YoY", "%"),
    "ebitda_growth_yoy": ("ebitda_growth_yoy", "EBITDA YoY", "%"),
    "net_profit_yoy_pct": ("pat_growth_yoy", "PAT YoY", "%"),
    "pat_growth_yoy": ("pat_growth_yoy", "PAT YoY", "%"),
    "revenue_qoq_pct": ("revenue_qoq_growth", "Revenue QoQ", "%"),
    "revenue_qoq_growth": ("revenue_qoq_growth", "Revenue QoQ", "%"),
    "ebitda_qoq_pct": ("ebitda_qoq_growth", "EBITDA QoQ", "%"),
    "net_profit_qoq_pct": ("pat_growth_qoq", "PAT QoQ", "%"),
    "operating_profit_qoq_pct": ("operating_profit_qoq_growth", "Operating Profit QoQ", "%"),
}

METRIC_META: dict[str, tuple[str, str, str]] = {
    **_BASE_METRIC_META,
    **fact_meta_for_mapper(),
    **metric_meta_for_mapper(),
}

CODE_TO_KEY: dict[str, str] = {meta[0]: key for key, meta in METRIC_META.items()}

_CATALOG_DIRECTIONS = signal_directions()
POSITIVE_SIGNALS = {k for k, v in _CATALOG_DIRECTIONS.items() if v == "POSITIVE"}
NEGATIVE_SIGNALS = {k for k, v in _CATALOG_DIRECTIONS.items() if v == "NEGATIVE"}

SIGNAL_CATEGORY: dict[str, str] = {
    **signal_categories(),
    "no_material_change": "general",
}

SUGGESTED_ACTIONS: dict[str, list[str]] = {
    "growth": ["Compare with peer growth", "Check segment mix"],
    "profitability": ["Compare CFO vs PAT", "Review evidence"],
    "operating": ["Check operating leverage", "Inspect cost breakdown"],
    "margin": ["Compare with peer margin", "Inspect cost breakdown"],
    "cash_quality": ["Compare CFO vs PAT", "Review receivables trend"],
    "earnings_quality": ["Inspect other income and exceptionals", "Review evidence"],
    "debt": ["Compare leverage with peers", "Check interest coverage"],
    "expense": ["Inspect cost breakdown", "Compare with peer margin"],
    "profit_quality": ["Review other income sources", "Check PBT bridge"],
    "general": ["Open event detail", "Review metrics"],
}

SNAPSHOT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("revenue_from_operations", "Revenue", "Cr"),
    ("ebitda", "EBITDA", "Cr"),
    ("ebitda_margin", "EBITDA Margin", "%"),
    ("pat", "PAT", "Cr"),
    ("eps_basic", "EPS", "Rs"),
)

DEFAULT_TREND_CODES = ("revenue_from_operations", "ebitda_margin", "pat")

_QUARTER_EVENT_TYPE = "QUARTERLY_RESULT"
_DOC_TYPE = "FINANCIAL_RESULT"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _severity(v2_severity: str | None = None, *, signal: dict[str, Any] | None = None) -> str:
    if signal is not None:
        key = signal.get("signal_key")
        if key:
            catalog_sev = get_catalog().signals.get(key, {}).get("severity")
            if catalog_sev in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                return catalog_sev
        v2_severity = signal.get("severity") or v2_severity
    return {"watch": "MEDIUM", "info": "LOW"}.get(v2_severity or "", "LOW")


def _direction(signal_key: str | None, signal: dict[str, Any] | None = None) -> str:
    if signal and signal.get("direction"):
        return signal["direction"]
    if signal_key in POSITIVE_SIGNALS:
        return "POSITIVE"
    if signal_key in NEGATIVE_SIGNALS:
        return "NEGATIVE"
    return "NEUTRAL"


def _row_key(m: dict[str, Any]) -> str:
    if m.get("derivation") == "raw":
        return m["fact_key"]
    return m["metric_key"]


def _by_key(metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in metrics:
        rk = _row_key(m)
        out[rk] = m
        meta = METRIC_META.get(rk)
        if meta and meta[0] not in out:
            out[meta[0]] = m
    return out


# ------------------------------------------------------------------ briefs

def company_brief(catalog: Catalog, ticker: str) -> dict[str, Any]:
    sector = "Financials" if ticker.upper() in {"AXISBANK"} else "Diversified"
    return {
        "company_id": ids.company_id(ticker),
        "company_name": ticker.title(),
        "short_name": ticker,
        "nse_symbol": ticker,
        "bse_code": None,
        "sector_name": sector,
        "industry": None,
        "market_cap_cr": None,
        "last_price": None,
    }


def period_brief(period: Period) -> dict[str, Any]:
    return {
        "period_id": ids.period_id(period.ticker, period.quarter, period.fy_start_year),
        "display_label": period.label,
        "fy_label": period.fy_label,
        "quarter": period.quarter,
        "period_end_date": period.quarter_end,
    }


def document_brief(filing: Filing) -> dict[str, Any]:
    return {
        "document_id": ids.document_id(filing.document_id),
        "document_type": _DOC_TYPE,
        "document_title": filing.title or f"{filing.ticker} filing",
        "document_date": filing.quarter_end,
        "extraction_confidence": 0.9,
        "values_extracted": None,
        "cards_generated": 1,
    }


def _format_number(value: float, fraction_digits: int = 0) -> str:
    return f"{value:,.{fraction_digits}f}"


def _format_cr_display(value: float) -> str:
    if abs(value) >= 100000:
        return f"{value / 100000:,.2f} L"
    return f"{_format_number(value, 2)} Cr"


def _format_pct_display(value: float, fraction_digits: int = 1) -> str:
    return f"{value:.{fraction_digits}f}%"


def _metric_value_display(value: float, unit: str) -> str:
    if unit == "%":
        return _format_pct_display(value)
    if unit in ("Cr", "crore"):
        return _format_cr_display(value)
    if unit == "Rs":
        return f"Rs {_format_number(value, 2)}"
    if unit:
        return f"{_format_number(value, 2)} {unit}"
    return _format_number(value, 2)


def trigger_metric_brief(
    built: BuiltPeriod, signal: dict[str, Any] | None
) -> dict[str, Any] | None:
    by_key = _by_key(built.metrics)
    metric_key = None
    if signal and signal.get("metric_keys"):
        metric_key = signal["metric_keys"][0]
    if metric_key is None:
        # Fall back to the largest raw metric so the feed row still shows data.
        raw = [m for m in built.card_metrics if m.get("derivation") == "raw"]
        if raw:
            metric_key = raw[0]["fact_key"]
    if metric_key is None or metric_key not in by_key:
        return None

    m = by_key[metric_key]
    code, name, unit = METRIC_META.get(metric_key, (metric_key, metric_key, ""))
    value = m["value"]
    value_display = _metric_value_display(float(value), unit)
    return {
        "code": code,
        "name": name,
        "value_display": value_display,
        "unit": unit,
        "metric_kind": "financial",
        "comparison_type": m.get("derivation"),
        "formula_text": m.get("formula_evaluated"),
        "source_page": None,
        "validation_status": "validated",
        "validation_reason": None,
        "confidence_band": "high",
        "confidence_score": 88.0,
    }


def _headline(built: BuiltPeriod, signal: dict[str, Any] | None) -> str:
    if signal:
        return signal["headline"]
    return f"{built.period.label} results"


def intelligence_object_brief(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    signal = catalog.primary_signal(built)
    p = built.period
    filing = built.filing
    direction = _direction(signal["signal_key"] if signal else None, signal)
    severity = _severity(signal=signal) if signal else "LOW"
    subtitle = (
        (_signal_description(signal["signal_key"]) if signal else None)
        or (_clean_rationale(signal["rationale"]) if signal else "Quarterly result processed")
    )
    return {
        "intelligence_object_id": ids.object_id(p.ticker, p.quarter, p.fy_start_year, "result_verdict"),
        "object_type": "result_verdict",
        "title": _headline(built, signal),
        "subtitle": subtitle,
        "status": direction,
        "importance_score": 80 if direction != "NEUTRAL" else 50,
        "severity": severity,
        "confidence": "HIGH",
        "confidence_score": 88.0,
        "time_horizon": "next_quarter",
        "company": company_brief(catalog, p.ticker),
        "period": period_brief(p),
        "event_id": ids.event_id(p.ticker, p.quarter, p.fy_start_year),
        "event_type": _QUARTER_EVENT_TYPE,
        "event_title": f"{p.label} Results",
        "event_date": p.quarter_end,
        "signal_id": ids.signal_id(p.ticker, p.quarter, p.fy_start_year, signal["signal_key"])
        if signal
        else None,
        "primary_metric": (signal["metric_keys"][0] if signal and signal.get("metric_keys") else None),
        "trigger_metric": trigger_metric_brief(built, signal),
        "investor_relevance": ["earnings", "verdict"],
        "source_label": filing.title if filing else "filing",
        "document_id": ids.document_id(filing.document_id) if filing else None,
        "created_at": filing.ingested_at if filing else _now(),
    }


# --------------------------------------------------------------- full object

def _evidence_items(catalog: Catalog, built: BuiltPeriod) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for i, m in enumerate(built.metrics):
        if m.get("derivation") != "raw" or not m.get("evidence"):
            continue
        doc = m.get("source_document_id")
        code, name, _ = METRIC_META.get(m["fact_key"], (m["fact_key"], m["fact_key"], ""))
        items.append(
            {
                "card_evidence_id": ids.stable_int("ev", built.period.ticker, built.period.quarter, built.period.fy_start_year, m["fact_key"]),
                "document_id": ids.document_id(doc) if doc else None,
                "evidence_type": "extracted_value",
                "evidence_label": name,
                "evidence_value": str(m["value"]),
                "source_text": m["evidence"],
                "page_number": None,
                "calculation_text": None,
                "confidence_score": 90.0,
            }
        )
    return items


def _metric_comparisons(built: BuiltPeriod) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in built.metrics:
        if m.get("derivation") not in ("yoy", "qoq"):
            continue
        growth_key = m["metric_key"]
        code, name, unit = METRIC_META.get(growth_key, (growth_key, growth_key, "%"))
        growth_value = m["value"]
        rows.append(
            {
                "metric_code": code,
                "metric_name": name,
                "current_value": growth_value,
                "previous_value": None,
                "change_percent": growth_value,
                "change_bps": None,
                "unit": unit,
                "comparison_type": m["derivation"],
            }
        )
    return rows


def _op_label(op: str) -> str:
    return {">": "above", ">=": "at or above", "<": "below", "<=": "at or below"}.get(op, op)


def _human_rule_formula(rule: dict[str, Any]) -> str | None:
    if not rule:
        return None
    if "metric_key" in rule:
        mk = str(rule["metric_key"])
        op = str(rule["op"])
        threshold = rule["value"]
        _, name, unit = METRIC_META.get(mk, (mk, mk.replace("_", " ").title(), ""))
        thresh_display = _metric_value_display(float(threshold), unit) if unit else str(threshold)
        return f"{name} {op} {thresh_display}"
    if "all" in rule:
        parts = [_human_rule_formula(child) for child in rule["all"]]
        joined = " AND ".join(p for p in parts if p)
        return joined or None
    if "any" in rule:
        parts = [_human_rule_formula(child) for child in rule["any"]]
        joined = " OR ".join(p for p in parts if p)
        return joined or None
    return None


def _compare_metric(value: float, op: str, threshold: float) -> bool:
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
    return False


def _find_leaf_in_catalog_rule(rule: dict[str, Any], metric_key: str) -> dict[str, Any] | None:
    if rule.get("metric_key") == metric_key:
        return rule
    for branch in ("all", "any"):
        if branch in rule:
            for child in rule[branch]:
                found = _find_leaf_in_catalog_rule(child, metric_key)
                if found:
                    return found
    return None


def _collect_catalog_rule_metric_keys(rule: dict[str, Any]) -> list[str]:
    from catalog_engine import _rule_metric_keys

    return _rule_metric_keys(rule)


def _build_rule_leaves(
    metric_keys: list[str],
    comparisons: list[dict[str, Any]],
    by_key: dict[str, dict[str, Any]],
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    by_code = {row["metric_code"]: row for row in comparisons}

    keys: list[str] = []
    for mk in metric_keys:
        if mk not in keys:
            keys.append(mk)
    for mk in _collect_catalog_rule_metric_keys(rule):
        if mk not in keys:
            keys.append(mk)

    leaves: list[dict[str, Any]] = []
    for mk in keys:
        code, default_name, default_unit = METRIC_META.get(mk, (mk, mk.replace("_", " ").title(), ""))
        comp = by_code.get(code)
        leaf_rule = _find_leaf_in_catalog_rule(rule, mk)

        op = (leaf_rule or {}).get("op")
        threshold = (leaf_rule or {}).get("value")

        value: float | None = None
        unit = default_unit
        mrow = by_key.get(mk)
        if mrow is not None and mrow.get("value") is not None:
            value = float(mrow["value"])
            unit = METRIC_META.get(mk, ("", "", ""))[2] or unit
        elif comp and comp.get("current_value") is not None:
            value = float(comp["current_value"])
            unit = str(comp.get("unit") or unit)

        passed: bool | None = None
        if value is not None and op and threshold is not None:
            passed = _compare_metric(value, str(op), float(threshold))

        rule_text: str | None = None
        if op and threshold is not None:
            rule_text = f"Requires {_op_label(str(op))} {threshold}"

        leaves.append(
            {
                "metric_code": code,
                "metric_name": comp["metric_name"] if comp else default_name,
                "current_value": value,
                "unit": unit,
                "operator": op,
                "threshold": threshold,
                "passed": passed,
                "rule_text": rule_text,
            }
        )
    return leaves


def _clean_rationale(text: str) -> str:
    return re.sub(r"\s*\([^)]+\)\s*$", "", text).strip()


def _signal_description(signal_key: str) -> str | None:
    spec = get_catalog().signals.get(signal_key, {})
    description = spec.get("description")
    return str(description).strip() if description else None


def _trigger_metric_row(
    comparisons: list[dict[str, Any]],
    metric_key: str | None,
) -> dict[str, Any] | None:
    if metric_key:
        code = METRIC_META.get(metric_key, (metric_key, "", ""))[0]
        for row in comparisons:
            if row["metric_code"] == code:
                return row
    return comparisons[0] if comparisons else None


def _calculation_chain(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any] | None:
    signal = catalog.primary_signal(built)
    if signal is None:
        return None
    by_key = _by_key(built.metrics)
    metric_key = signal["metric_keys"][0] if signal.get("metric_keys") else None
    metric_block = None
    fired_value = None
    if metric_key and metric_key in by_key:
        m = by_key[metric_key]
        fired_value = m["value"]
        code, name, unit = METRIC_META.get(metric_key, (metric_key, metric_key, ""))
        inputs = []
        for d in m.get("input_details", []):
            ik = d.get("metric_key")
            icode, _, iunit = METRIC_META.get(ik, (ik, ik, ""))
            inputs.append(
                {
                    "formula_name": d.get("role", "input"),
                    "code": icode,
                    "scope": "CURRENT" if d.get("role") == "current" else "PRIOR",
                    "kind": "metric",
                    "value": d.get("value"),
                    "unit": iunit,
                    "document_id": None,
                    "page_number": None,
                    "source_text": None,
                }
            )
        metric_block = {
            "code": code,
            "name": name,
            "formula_text": m.get("formula_evaluated"),
            "value": m["value"],
            "unit": unit,
            "inputs": inputs,
            "is_quarantined": False,
            "quarantine_reason": None,
        }
    return {
        "signal": {
            "code": signal["signal_key"].upper(),
            "name": signal["headline"],
            "category": SIGNAL_CATEGORY.get(signal["signal_key"], "general"),
            "rule_text": signal["rationale"],
            "direction": _direction(signal["signal_key"], signal),
            "severity": _severity(signal=signal),
            "fired_value": fired_value,
            "fired_unit": "%" if metric_key and metric_key.endswith("pct") else None,
            "threshold": None,
            "operator": None,
            "metric_ref": metric_key,
        },
        "metric": metric_block,
    }


def _io_metric_row(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": METRIC_META.get(_row_key(m), (_row_key(m), _row_key(m), ""))[1],
        "value": m["value"],
        "unit": METRIC_META.get(_row_key(m), ("", "", ""))[2] or m.get("unit"),
        "source_kind": "extracted" if m.get("derivation") == "raw" else "computed",
    }


def _io_metrics(built: BuiltPeriod) -> list[dict[str, Any]]:
    """All accepted filing facts plus catalog-derived metrics for the IO detail view."""
    raw = [m for m in built.metrics if m.get("derivation") == "raw"]
    computed = [m for m in built.metrics if m.get("derivation") != "raw"]
    raw.sort(key=lambda m: abs(float(m.get("value", 0))), reverse=True)
    computed.sort(key=lambda m: _row_key(m))
    return [_io_metric_row(m) for m in raw + computed]


def intelligence_object(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    brief = intelligence_object_brief(catalog, built)
    signal = catalog.primary_signal(built)
    p = built.period
    category = SIGNAL_CATEGORY.get(signal["signal_key"], "general") if signal else "general"

    io_metrics = _io_metrics(built)

    description = _signal_description(signal["signal_key"]) if signal else None
    rationale = _clean_rationale(signal["rationale"]) if signal else "Quarterly result processed without material signals."

    return {
        **brief,
        "insight": description or rationale,
        "investor_question": None,
        "watch_next": "Track the next quarter for confirmation.",
        "event": event_brief(catalog, built),
        "signal": signal_brief(catalog, built, signal) if signal else None,
        "metrics": io_metrics,
        "metric_comparisons": _metric_comparisons(built),
        "trend_sparklines": company_trends(catalog, p.ticker, list(DEFAULT_TREND_CODES), 8),
        "concern_heatmap": [],
        "calculation": {},
        "calculation_chain": _calculation_chain(catalog, built),
        "evidence": _evidence_items(catalog, built),
        "display": {
            "layout": "summary_hero",
            "primary_metric": brief["primary_metric"],
            "chart_type": "revenue_trend",
            "cta": "Open event detail",
            "surfaces": ["feed", "drawer"],
        },
        "suggested_actions": SUGGESTED_ACTIONS.get(category, SUGGESTED_ACTIONS["general"]),
        "event_main_issue": signal["headline"] if signal else None,
        "event_summary": brief["subtitle"],
    }


# --------------------------------------------------------------- snapshot

def financial_snapshot(catalog: Catalog, built: BuiltPeriod) -> list[dict[str, Any]]:
    p = built.period
    by_key = _by_key(built.metrics)
    prior_details = catalog.store.load_fact_details(
        p.ticker, p.quarter, p.fy_start_year - 1, built.basis_used
    )

    def prior_display_value(code: str) -> float | None:
        detail = prior_details.get(code)
        if detail is None:
            return None
        return float(detail["numeric_value"])

    def prior_comparable_value(code: str) -> float | None:
        detail = prior_details.get(code)
        if detail is None:
            return None
        return to_crore_equivalent(float(detail["numeric_value"]), detail.get("unit"))

    rows: list[dict[str, Any]] = []
    for code, name, unit in SNAPSHOT_ROWS:
        current_row = by_key.get(code)
        current = current_row["value"] if current_row is not None else None
        if code == "ebitda_margin":
            ebitda = prior_display_value("ebitda")
            revenue = prior_display_value("revenue_from_operations")
            previous = (
                round(ebitda / revenue * 100, 2)
                if ebitda is not None and revenue
                else None
            )
        else:
            previous = prior_display_value(code)
        yoy_pct: float | None = None
        yoy_bps: float | None = None
        if current is not None and previous is not None:
            if unit == "%":
                yoy_bps = round((current - previous) * 100, 1)
            elif previous != 0:
                current_cmp = to_crore_equivalent(
                    float(current),
                    current_row.get("unit") if current_row else None,
                )
                prior_cmp = prior_comparable_value(code)
                if prior_cmp is not None and prior_cmp != 0:
                    yoy_pct = round((current_cmp - prior_cmp) / prior_cmp * 100, 2)
        rows.append(
            {
                "metric": name,
                "code": code,
                "current_value": current,
                "previous_value": previous,
                "yoy_change_pct": yoy_pct,
                "yoy_change_bps": yoy_bps,
                "unit": unit,
            }
        )
    return rows


# ----------------------------------------------------------------- trends

def _raw_trend_points(catalog: Catalog, ticker: str, fact_key: str, n: int) -> list[dict[str, Any]]:
    return catalog.store.get_trend_alias_aware(ticker, fact_key, PREFERRED_BASIS, n=n)


def company_trends(
    catalog: Catalog, ticker: str, codes: list[str], quarters: int
) -> list[dict[str, Any]]:
    trends: list[dict[str, Any]] = []
    for code in codes:
        name = METRIC_META.get(CODE_TO_KEY.get(code, code), (code, code, ""))[1]
        unit = METRIC_META.get(CODE_TO_KEY.get(code, code), ("", "", "Cr"))[2]
        if code == "ebitda_margin":
            points = _margin_trend_points(catalog, ticker, quarters)
        else:
            key = CODE_TO_KEY.get(code, code)
            series = _raw_trend_points(catalog, ticker, key, quarters)
            points = [
                {
                    "period_label": pt["label"],
                    "period_end_date": pt["quarter_end"],
                    "value": pt["value"],
                    "anomaly_flag": False,
                }
                for pt in series
            ]
        if not points:
            continue
        trends.append(
            {
                "metric_code": code,
                "metric_name": name,
                "unit": unit,
                "points": points,
                "band": None,
            }
        )
    return trends


def _margin_trend_points(catalog: Catalog, ticker: str, n: int) -> list[dict[str, Any]]:
    revenue = {pt["quarter_end"]: pt for pt in _raw_trend_points(catalog, ticker, "revenue_from_operations", n)}
    ebitda = {pt["quarter_end"]: pt for pt in _raw_trend_points(catalog, ticker, "ebitda", n)}
    points: list[dict[str, Any]] = []
    for qe in sorted(set(revenue) & set(ebitda)):
        rev = revenue[qe]["value"]
        if not rev:
            continue
        points.append(
            {
                "period_label": revenue[qe]["label"],
                "period_end_date": qe,
                "value": round(ebitda[qe]["value"] / rev * 100, 2),
                "anomaly_flag": False,
            }
        )
    return points


# ----------------------------------------------------------------- events

def event_brief(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    p = built.period
    signal = catalog.primary_signal(built)
    filing = built.filing
    return {
        "event_id": ids.event_id(p.ticker, p.quarter, p.fy_start_year),
        "event_type": _QUARTER_EVENT_TYPE,
        "event_title": f"{p.label} Results",
        "event_date": p.quarter_end,
        "company": company_brief(catalog, p.ticker),
        "period": period_brief(p),
        "source_exchange": None,
        "consolidation": built.basis_used,
        "overall_signal": _direction(signal["signal_key"], signal) if signal else "NEUTRAL",
        "overall_severity": _severity(signal=signal) if signal else "LOW",
        "overall_confidence": 88.0,
        "summary_text": _headline(built, signal),
        "document_id": ids.document_id(filing.document_id) if filing else None,
    }


def timeline_event(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    p = built.period
    signal = catalog.primary_signal(built)
    return {
        "event_id": ids.event_id(p.ticker, p.quarter, p.fy_start_year),
        "event_type": _QUARTER_EVENT_TYPE,
        "event_title": f"{p.label} Results",
        "event_date": p.quarter_end,
        "overall_signal": _direction(signal["signal_key"], signal) if signal else "NEUTRAL",
        "overall_severity": _severity(signal=signal) if signal else "LOW",
        "summary_text": _headline(built, signal),
        "period": period_brief(p),
    }


def card_brief(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    brief = intelligence_object_brief(catalog, built)
    return {
        "card_id": brief["intelligence_object_id"],
        "signal_id": brief["signal_id"],
        "card_type": brief["object_type"],
        "headline": brief["title"],
        "one_line_summary": brief["subtitle"],
        "signal_direction": brief["status"],
        "severity": brief["severity"],
        "confidence_score": brief["confidence_score"],
        "confidence_level": brief["confidence"],
        "card_priority": brief["importance_score"],
        "company": brief["company"],
        "period": brief["period"],
        "event_id": brief["event_id"],
        "event_type": brief["event_type"],
        "event_title": brief["event_title"],
        "event_date": brief["event_date"],
        "metrics_json": [],
        "watch_next": None,
        "source_label": brief["source_label"],
        "document_id": brief["document_id"],
        "created_at": brief["created_at"],
        "trigger_metric": brief["trigger_metric"],
    }


def event_detail(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    base = event_brief(catalog, built)
    filing = built.filing
    signal = catalog.primary_signal(built)
    raw_facts = [
        {
            "line_item_code": METRIC_META.get(m["fact_key"], (m["fact_key"], "", ""))[0],
            "line_item_name": METRIC_META.get(m["fact_key"], ("", m["fact_key"], ""))[1],
            "value": m["value"],
            "unit": METRIC_META.get(m["fact_key"], ("", "", "Cr"))[2],
            "period_value_type": "QUARTER",
            "consolidation": built.basis_used,
        }
        for m in built.metrics
        if m.get("derivation") == "raw"
    ]
    return {
        **base,
        "main_issue": signal["headline"] if signal else None,
        "watch_next": "Track the next quarter for confirmation.",
        "audit_status": "unaudited",
        "raw_facts": raw_facts,
        "documents": [document_brief(filing)] if filing else [],
        "metric_snapshot": {_row_key(m): m["value"] for m in built.metrics},
        "cards": [card_brief(catalog, built)],
        "signals": [signal_brief(catalog, built, s) for s in built.signals],
        "financial_snapshot": financial_snapshot(catalog, built),
        "related_events": [
            timeline_event(catalog, b)
            for b in catalog.built_for_ticker(built.period.ticker)
            if b.period.quarter_end != built.period.quarter_end
        ],
        "concern_heatmap": [],
        "concall_facts": [],
        "ingestion_status": {
            "published_card_count": 1,
            "unpublished_card_count": 0,
            "published_signal_count": len(built.signals),
            "unpublished_signal_count": 0,
            "document_count": 1 if filing else 0,
            "values_extracted_total": len(raw_facts),
        },
        "analyst_summary": None,
        "signal_diagnostics": None,
    }


# ---------------------------------------------------------------- signals

def signal_brief(
    catalog: Catalog, built: BuiltPeriod, signal: dict[str, Any] | None
) -> dict[str, Any]:
    p = built.period
    signal = signal or {"signal_key": "no_material_change", "severity": "info", "headline": "No material change", "rationale": "Threshold rules did not fire", "metric_keys": []}
    return {
        "signal_id": ids.signal_id(p.ticker, p.quarter, p.fy_start_year, signal["signal_key"]),
        "signal_code": signal["signal_key"].upper(),
        "signal_name": signal["headline"],
        "signal_category": SIGNAL_CATEGORY.get(signal["signal_key"], "general"),
        "direction": _direction(signal["signal_key"], signal),
        "severity": _severity(signal=signal),
        "confidence_score": 88.0,
        "signal_score": 70.0,
        "headline": signal["headline"],
        "explanation": _signal_description(signal["signal_key"]) or _clean_rationale(signal["rationale"]),
        "company": company_brief(catalog, p.ticker),
        "period": period_brief(p),
        "event_id": ids.event_id(p.ticker, p.quarter, p.fy_start_year),
        "document_id": ids.document_id(built.filing.document_id) if built.filing else None,
        "created_at": built.filing.ingested_at if built.filing else _now(),
    }


def signal_detail(
    catalog: Catalog, built: BuiltPeriod, signal: dict[str, Any]
) -> dict[str, Any]:
    brief = signal_brief(catalog, built, signal)
    by_key = _by_key(built.metrics)
    metric_key = signal["metric_keys"][0] if signal.get("metric_keys") else None
    primary = None
    trigger = None
    if metric_key and metric_key in by_key:
        m = by_key[metric_key]
        code, name, unit = METRIC_META.get(metric_key, (metric_key, metric_key, ""))
        primary = {"metric_code": code, "metric_name": name, "value": m["value"], "unit": unit}
    comparisons = _metric_comparisons(built)
    trigger = _trigger_metric_row(comparisons, metric_key)
    rule_json = signal.get("rule") or {}
    machine_rule = signal.get("rule_text") or ""
    if not machine_rule and rule_json:
        from catalog_engine import format_rule_text

        machine_rule = format_rule_text(rule_json)
    rule_leaves = _build_rule_leaves(
        signal.get("metric_keys", []),
        comparisons,
        by_key,
        rule_json,
    ) if rule_json else []
    summary = _signal_description(signal["signal_key"]) or _clean_rationale(signal["rationale"])
    rule_formula = _human_rule_formula(rule_json) if rule_json else None
    return {
        **brief,
        "description": signal["rationale"],
        "rule_text": machine_rule or signal["rationale"],
        "rule_formula": rule_formula,
        "rule_summary": summary,
        "rule_json": rule_json,
        "rule_metric_codes": [METRIC_META.get(k, (k, "", ""))[0] for k in signal.get("metric_keys", [])],
        "rule_leaves": rule_leaves,
        "calculation": None,
        "primary_metric": primary,
        "trigger_metric": trigger,
        "metric_refs": signal.get("metric_keys", []),
        "evidence_refs": [],
        "metric_comparisons": comparisons,
        "trend_sparklines": company_trends(catalog, built.period.ticker, list(DEFAULT_TREND_CODES), 8),
        "related_cards": [card_brief(catalog, built)],
        "related_signals": [
            {
                "signal_id": ids.signal_id(built.period.ticker, built.period.quarter, built.period.fy_start_year, s["signal_key"]),
                "signal_code": s["signal_key"].upper(),
                "signal_name": s["headline"],
                "signal_category": SIGNAL_CATEGORY.get(s["signal_key"], "general"),
                "direction": _direction(s["signal_key"], s),
                "severity": _severity(signal=s),
                "confidence_score": 88.0,
                "signal_score": 70.0,
                "headline": s["headline"],
            }
            for s in built.signals
            if s["signal_key"] != signal["signal_key"]
        ],
        "evidence": _evidence_items(catalog, built),
        "event": {
            "event_id": brief["event_id"],
            "event_type": _QUARTER_EVENT_TYPE,
            "event_title": f"{built.period.label} Results",
            "event_date": built.period.quarter_end,
            "summary_text": signal["headline"],
            "main_issue": signal["headline"],
            "watch_next": "Track the next quarter for confirmation.",
            "overall_signal": _direction(signal["signal_key"], signal),
            "overall_severity": _severity(signal=signal),
            "overall_confidence": 88.0,
        },
        "document": document_brief(built.filing) if built.filing else None,
    }


# --------------------------------------------------------------- aggregate

def _has_material_signals(built: BuiltPeriod) -> bool:
    return any(s.get("signal_key") != "no_material_change" for s in built.signals)


def company_detail(catalog: Catalog, ticker: str, watchlist_status: bool) -> dict[str, Any]:
    builts = catalog.built_for_ticker(ticker)
    latest = builts[-1] if builts else None
    badges = _company_badges(catalog, latest) if latest else []
    top_objects = [
        intelligence_object_brief(catalog, b)
        for b in reversed(builts)
        if _has_material_signals(b)
    ]
    latest_signal = catalog.primary_signal(latest) if latest else None
    return {
        "company": company_brief(catalog, ticker),
        "watchlist_status": watchlist_status,
        "badges": badges,
        "latest_event_id": ids.event_id(latest.period.ticker, latest.period.quarter, latest.period.fy_start_year) if latest else None,
        "latest_period": period_brief(latest.period) if latest else None,
        "latest_summary": _headline(latest, latest_signal) if latest else None,
        "main_issue": latest_signal["headline"] if latest_signal else None,
        "watch_next": "Track the next quarter for confirmation." if latest else None,
        "top_objects": top_objects,
        "financial_snapshot": financial_snapshot(catalog, latest) if latest else [],
        "trends": company_trends(catalog, ticker, list(DEFAULT_TREND_CODES), 8),
        "timeline": [timeline_event(catalog, b) for b in reversed(builts)],
        "documents": [document_brief(f) for f in reversed(catalog.filings_for(ticker))],
    }


def _company_badges(catalog: Catalog, built: BuiltPeriod) -> list[dict[str, Any]]:
    by_key = _by_key(built.metrics)
    badges: list[dict[str, Any]] = []
    yoy = by_key.get("revenue_yoy_pct")
    if yoy:
        tone = "positive" if yoy["value"] >= 0 else "negative"
        badges.append(
            {"label": "Growth", "value": f"{_format_pct_display(float(yoy['value']))} YoY", "tone": tone}
        )
    margin = by_key.get("ebitda_margin")
    if margin:
        badges.append(
            {"label": "Margins", "value": _format_pct_display(float(margin["value"])), "tone": "neutral"}
        )
    pat = by_key.get("pat")
    if pat:
        badges.append(
            {"label": "Profit Quality", "value": _format_cr_display(float(pat["value"])), "tone": "neutral"}
        )
    return badges


def feed_summary(catalog: Catalog, builts: list[BuiltPeriod]) -> dict[str, Any]:
    positive = negative = margins = red_flags = 0
    for b in builts:
        for s in b.signals:
            st = s["signal_key"]
            if st in POSITIVE_SIGNALS:
                positive += 1
            elif st in NEGATIVE_SIGNALS:
                negative += 1
            if st == "margin_pressure":
                margins += 1
            if s.get("severity") == "watch":
                red_flags += 1
    return {
        "results_processed": len(builts),
        "positive_signals": positive,
        "negative_signals": negative,
        "margin_warnings": margins,
        "red_flags": red_flags,
        "guidance_updates": 0,
        "verdicts": len(builts),
        "growth": positive,
        "margins": margins,
        "risks": red_flags,
    }


def reproducibility(catalog: Catalog, built: BuiltPeriod) -> dict[str, Any]:
    brief = intelligence_object_brief(catalog, built)
    signal = catalog.primary_signal(built)
    chain = _calculation_chain(catalog, built)
    metric_block = chain["metric"] if chain else None
    inputs = []
    for m in built.metrics:
        if m.get("derivation") != "raw":
            continue
        code, name, unit = METRIC_META.get(m["fact_key"], (m["fact_key"], m["fact_key"], ""))
        inputs.append(
            {
                "name": name,
                "code": code,
                "scope": "CURRENT",
                "kind": "fact",
                "value": m["value"],
                "unit": unit,
                "extracted_value_id": None,
                "page_number": None,
                "source_text": m.get("evidence"),
                "confidence_score": 90.0,
            }
        )
    nodes = [
        {
            "id": f"card-{brief['intelligence_object_id']}",
            "kind": "intelligence_card",
            "label": brief["title"],
            "detail": brief["subtitle"],
            "page_number": None,
            "document_id": brief["document_id"],
            "confidence_score": 88.0,
            "validation_status": "validated",
        }
    ]
    return {
        "card": {
            "card_id": brief["intelligence_object_id"],
            "card_type": brief["object_type"],
            "headline": brief["title"],
            "one_line_summary": brief["subtitle"],
            "direction": brief["status"],
            "severity": brief["severity"],
            "confidence_score": 88.0,
            "is_published": True,
        },
        "signal": {
            "signal_id": brief["signal_id"],
            "code": signal["signal_key"].upper() if signal else None,
            "name": signal["headline"] if signal else None,
            "category": SIGNAL_CATEGORY.get(signal["signal_key"], "general") if signal else None,
            "rule_text": signal["rationale"] if signal else None,
            "direction": brief["status"],
            "severity": brief["severity"],
            "confidence_score": 88.0,
            "fired_value": chain["signal"]["fired_value"] if chain else None,
            "threshold": None,
            "operator": None,
            "explanation": signal["rationale"] if signal else None,
        }
        if signal
        else None,
        "metric": {
            "metric_id": None,
            "code": metric_block["code"] if metric_block else None,
            "name": metric_block["name"] if metric_block else None,
            "metric_kind": "financial",
            "formula_text": metric_block["formula_text"] if metric_block else None,
            "unit": metric_block["unit"] if metric_block else None,
            "value": metric_block["value"] if metric_block else None,
            "validation_min": None,
            "validation_max": None,
            "is_quarantined": False,
            "quarantine_reason": None,
            "anomaly_flag": False,
            "anomaly_reason": None,
            "confidence_score": 88.0,
            "inputs": inputs,
        }
        if metric_block
        else None,
        "audit_trail": {
            "extraction_job_id": None,
            "prompt_version": None,
            "parser_version": "v2-notebook",
            "model_name": "gpt-4o-mini",
            "provider_used": "openai",
            "llm_temperature": 0.0,
            "llm_seed": None,
            "request_hash": built.filing.sha256 if built.filing else None,
            "completed_at": built.filing.ingested_at if built.filing else None,
            "reprocess_timestamp": None,
        },
        "lineage": {"nodes": nodes, "edges": []},
        "exported_at": _now(),
    }
