"""Export seed-catalog signals to a filterable CSV with fact / pipeline metadata.

Run from ``backend/``::

    python -m app.scripts.export_signals_full

Writes ``seed_catalog_dump/signals_full.csv`` and ``signals_full.README.txt``.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from app.seed.seed_catalog import LINE_ITEMS, METRIC_DEFS, SIGNAL_DEFS

OUT_DIR = Path(__file__).resolve().parents[2] / "seed_catalog_dump"
OUT_CSV = OUT_DIR / "signals_full.csv"
OUT_README = OUT_DIR / "signals_full.README.txt"

METRICS = {m["code"]: m for m in METRIC_DEFS}
LINE_ITEM = {code: (name, st) for code, name, st in LINE_ITEMS}

FACT_DOCS = {
    "revenue_from_operations": "FINANCIAL_RESULT",
    "other_income": "FINANCIAL_RESULT",
    "total_income": "FINANCIAL_RESULT",
    "employee_cost": "FINANCIAL_RESULT",
    "finance_cost": "FINANCIAL_RESULT",
    "depreciation": "FINANCIAL_RESULT",
    "other_expenses": "FINANCIAL_RESULT",
    "cogs": "FINANCIAL_RESULT",
    "exceptional_items": "FINANCIAL_RESULT",
    "ebitda": "FINANCIAL_RESULT",
    "ebitda_margin": "FINANCIAL_RESULT",
    "ebit": "FINANCIAL_RESULT",
    "pbt": "FINANCIAL_RESULT",
    "tax_expense": "FINANCIAL_RESULT",
    "pat": "FINANCIAL_RESULT",
    "eps_basic": "FINANCIAL_RESULT",
    "eps_diluted": "FINANCIAL_RESULT",
    "cfo": "FINANCIAL_RESULT",
    "capex_ppe": "FINANCIAL_RESULT",
    "capex_intangibles": "FINANCIAL_RESULT",
    "dividend_paid": "FINANCIAL_RESULT",
    "interest_paid": "FINANCIAL_RESULT",
    "borrowings_raised": "FINANCIAL_RESULT",
    "trade_receivables": "FINANCIAL_RESULT",
    "inventory": "FINANCIAL_RESULT",
    "trade_payables": "FINANCIAL_RESULT",
    "current_assets": "FINANCIAL_RESULT",
    "current_liabilities": "FINANCIAL_RESULT",
    "short_term_borrowings": "FINANCIAL_RESULT",
    "long_term_borrowings": "FINANCIAL_RESULT",
    "lease_liabilities": "FINANCIAL_RESULT",
    "cash_and_equivalents": "FINANCIAL_RESULT",
    "current_investments": "FINANCIAL_RESULT",
    "share_capital": "FINANCIAL_RESULT",
    "other_equity": "FINANCIAL_RESULT",
    "shareholders_equity": "FINANCIAL_RESULT",
    "total_assets": "FINANCIAL_RESULT",
    "total_liabilities": "FINANCIAL_RESULT",
    "primary_segment_revenue": "FINANCIAL_RESULT",
    "primary_segment_ebit": "FINANCIAL_RESULT",
    "promoter_holding_pct": "SHAREHOLDING_PATTERN",
    "promoter_pledge_pct": "SHAREHOLDING_PATTERN",
    "fii_holding_pct": "SHAREHOLDING_PATTERN",
    "dii_holding_pct": "SHAREHOLDING_PATTERN",
    "public_holding_pct": "SHAREHOLDING_PATTERN",
    "revenue_guidance_lower": "CONCALL|INVESTOR_PRESENTATION|ANNUAL_REPORT|PRESS_RELEASE",
    "revenue_guidance_upper": "CONCALL|INVESTOR_PRESENTATION|ANNUAL_REPORT|PRESS_RELEASE",
    "ebitda_margin_guidance_lower": "CONCALL|INVESTOR_PRESENTATION|ANNUAL_REPORT|PRESS_RELEASE",
    "ebitda_margin_guidance_upper": "CONCALL|INVESTOR_PRESENTATION|ANNUAL_REPORT|PRESS_RELEASE",
    "opening_order_book": "ORDER_BOOK_DOCS",
    "closing_order_book": "ORDER_BOOK_DOCS",
    "order_inflow": "ORDER_BOOK_DOCS",
    "executed_orders": "ORDER_BOOK_DOCS",
    "cancelled_orders": "ORDER_BOOK_DOCS",
    "top_customer_orders": "ORDER_BOOK_DOCS",
    "concall_confidence_score": "CONCALL_TRANSCRIPT",
    "concall_uncertainty_score": "CONCALL_TRANSCRIPT",
    "concall_evasive_score": "CONCALL_TRANSCRIPT",
    "concall_demand_score": "CONCALL_TRANSCRIPT",
    "concall_cost_pressure_score": "CONCALL_TRANSCRIPT",
    "concall_pricing_power_score": "CONCALL_TRANSCRIPT",
    "concall_capex_intent_score": "CONCALL_TRANSCRIPT",
    "concall_margin_tone_score": "CONCALL_TRANSCRIPT",
    "new_order_value": "PRESS_RELEASE",
    "acquisition_value": "PRESS_RELEASE",
    "motion_per_share": "PRESS_RELEASE",
    "new_capacity": "PRESS_RELEASE",
    "existing_capacity": "PRESS_RELEASE",
    "revenue_contribution_pct": "PRESS_RELEASE",
    "tam_market_size": "INVESTOR_PRESENTATION",
    "tam_market_size_prior": "INVESTOR_PRESENTATION",
    "high_margin_revenue_pct": "INVESTOR_PRESENTATION",
    "top_client_revenue_pct": "INVESTOR_PRESENTATION",
    "region_revenue_pct": "INVESTOR_PRESENTATION",
    "capacity_utilization_pct": "INVESTOR_PRESENTATION",
    "management_target_value": "INVESTOR_PRESENTATION",
    "share_price_close": "MARKET_DATA",
    "avg_volume_20d": "MARKET_DATA",
    "volume": "MARKET_DATA",
    "delivery_pct": "MARKET_DATA",
    "market_cap": "MARKET_DATA",
    "pre_event_close": "MARKET_DATA",
    "post_event_close": "MARKET_DATA",
}
ORDER_BOOK = "INVESTOR_PRESENTATION|CONCALL|ANNUAL_REPORT|FINANCIAL_RESULT|PRESS_RELEASE"
for _k, _v in list(FACT_DOCS.items()):
    if _v == "ORDER_BOOK_DOCS":
        FACT_DOCS[_k] = ORDER_BOOK

SCOPE_LABEL = {
    "CURRENT": "Current quarter",
    "PY": "Prior-year same quarter",
    "PQ": "Prior quarter",
    "TTM": "Trailing 4 quarters",
    "TTM_AVG": "TTM average",
    "AVG_2_OPENING_CLOSING": "Avg opening/closing (CY+PY)",
    "PY_PQ": "Two-quarter lag",
}

EXTRACTED_VALUE_FIELDS = (
    "ExtractedValue: normalized_code (= fact_code), raw_label, numeric_value, "
    "unit, statement_type, page_number, source_text"
)

PIPELINE_CHAIN = (
    "ExtractedValue → FinancialStatementFact → CalculatedMetric → GeneratedSignal"
)


def fact_unit(code: str) -> str:
    if code.endswith("_pct") or code.endswith("_score"):
        return "%" if code.endswith("_pct") else "score"
    if code in {
        "eps_basic",
        "eps_diluted",
        "dividend_per_share",
        "share_price_close",
        "pre_event_close",
        "post_event_close",
    }:
        return "Rs"
    if code in {"volume", "avg_volume_20d"}:
        return "shares"
    if code in {"new_capacity", "existing_capacity"}:
        return "unit"
    if code in {"revenue_guidance_lower", "revenue_guidance_upper", "ebitda_margin_guidance_lower", "ebitda_margin_guidance_upper"}:
        return "%"
    return "crore"


def fmt_rule(rule: dict) -> str:
    if not rule:
        return "manual (not auto-fired)"
    if "metric" in rule and "operator" in rule:
        rhs = f"ref:{rule['metric_ref']}" if rule.get("metric_ref") else str(rule.get("threshold"))
        return f"{rule['metric']} {rule['operator']} {rhs}"
    if "all" in rule:
        return " AND ".join(f"({fmt_rule(r)})" for r in rule["all"])
    if "any" in rule:
        return " OR ".join(f"({fmt_rule(r)})" for r in rule["any"])
    if "not" in rule:
        return f"NOT ({fmt_rule(rule['not'])})"
    return json.dumps(rule)


def leaf_metrics(rule: dict) -> set[str]:
    if not rule:
        return set()
    if "all" in rule:
        return set().union(*(leaf_metrics(r) for r in rule["all"]))
    if "any" in rule:
        return set().union(*(leaf_metrics(r) for r in rule["any"]))
    if "not" in rule:
        return leaf_metrics(rule["not"])
    out: set[str] = set()
    if rule.get("metric"):
        out.add(rule["metric"])
    if rule.get("metric_ref"):
        out.add(rule["metric_ref"])
    return out


def expand_metric(metric_code: str, seen: set[str] | None = None) -> list[tuple[str, str, str, str]]:
    """Return (fact_code, scope, via_metric, kind) rows."""
    seen = seen or set()
    if metric_code in seen:
        return []
    seen.add(metric_code)
    spec = METRICS.get(metric_code)
    if not spec:
        return [(metric_code, "?", metric_code, "metric")]
    rows: list[tuple[str, str, str, str]] = []
    for inp in spec["inputs"]:
        kind = (inp.get("kind") or "fact").lower()
        scope = (inp.get("scope") or "CURRENT").upper()
        if kind == "metric":
            rows.extend(expand_metric(inp["code"], seen))
        else:
            rows.append((inp["code"], scope, metric_code, "fact"))
    return rows


def scope_flags(scope: str) -> dict[str, str]:
    flags = {k: "N" for k in ("CY", "PY", "CQ", "TTM", "AVG")}
    if scope == "CURRENT":
        flags["CY"] = "Y"
    elif scope == "PY":
        flags["PY"] = "Y"
    elif scope == "PQ":
        flags["CQ"] = "Y"
    elif scope in ("TTM", "TTM_AVG"):
        flags["TTM"] = "Y"
    elif scope == "AVG_2_OPENING_CLOSING":
        flags["AVG"] = "Y"
        flags["CY"] = "Y"
        flags["PY"] = "Y"
    elif scope == "PY_PQ":
        flags["PY"] = "Y"
        flags["CQ"] = "Y"
    return flags


def line_item_meta(code: str) -> tuple[str, str]:
    if code in LINE_ITEM:
        name, st = LINE_ITEM[code]
        return name, st.value if hasattr(st, "value") else str(st)
    return "", ""


def metric_summary(codes: list[str]) -> str:
    parts = []
    for c in codes:
        m = METRICS.get(c)
        if m:
            parts.append(f"{c} ({m['unit']})")
        else:
            parts.append(c)
    return "|".join(parts)


def build_rows() -> list[dict]:
    rows_out: list[dict] = []
    for sig in SIGNAL_DEFS:
        rule = sig["rule"]
        metrics = sorted(leaf_metrics(rule))
        base = {
            "signal_code": sig["code"],
            "signal_name": sig["name"],
            "category": sig["category"],
            "direction": sig["direction"].value if sig["direction"] else "",
            "severity": sig["severity"].value if sig["severity"] else "",
            "auto_fired": "N" if not rule else "Y",
            "description": sig["desc"],
            "rule": fmt_rule(rule),
            "metrics_used": "|".join(metrics),
            "metrics_with_units": metric_summary(metrics),
            "pipeline_chain": PIPELINE_CHAIN if rule else "",
            "extracted_value_fields": EXTRACTED_VALUE_FIELDS if rule else "",
        }

        if not rule:
            rows_out.append({
                **base,
                "normalized_code": "",
                "fact_code": "",
                "fact_name": "",
                "statement_type": "",
                "fact_unit": "",
                "via_metric": "",
                "metric_name": "",
                "metric_unit": "",
                "engine_scope": "",
                "period_label": "",
                "CY": "",
                "PY": "",
                "CQ": "",
                "TTM": "",
                "AVG": "",
                "documents": "",
            })
            continue

        dep_rows: list[tuple[str, str, str, str]] = []
        for mc in metrics:
            dep_rows.extend(expand_metric(mc))

        seen_keys: set[tuple[str, str, str]] = set()
        for fact_code, scope, via_metric, kind in dep_rows:
            key = (fact_code, scope, via_metric)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fact_name, statement_type = line_item_meta(fact_code)
            mspec = METRICS.get(via_metric, {})
            rows_out.append({
                **base,
                "normalized_code": fact_code,
                "fact_code": fact_code,
                "fact_name": fact_name,
                "statement_type": statement_type,
                "fact_unit": fact_unit(fact_code) if kind == "fact" else "",
                "via_metric": via_metric,
                "metric_name": mspec.get("name", via_metric),
                "metric_unit": mspec.get("unit", ""),
                "engine_scope": scope,
                "period_label": SCOPE_LABEL.get(scope, scope),
                **scope_flags(scope),
                "documents": FACT_DOCS.get(fact_code, "FINANCIAL_RESULT"),
            })
    return rows_out


FIELDNAMES = [
    "signal_code",
    "signal_name",
    "category",
    "direction",
    "severity",
    "auto_fired",
    "description",
    "rule",
    "metrics_used",
    "metrics_with_units",
    "normalized_code",
    "fact_code",
    "fact_name",
    "statement_type",
    "fact_unit",
    "via_metric",
    "metric_name",
    "metric_unit",
    "engine_scope",
    "period_label",
    "CY",
    "PY",
    "CQ",
    "TTM",
    "AVG",
    "documents",
    "extracted_value_fields",
    "pipeline_chain",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    OUT_README.write_text(
        "signals_full.csv — all seed signals exploded by fact + period scope.\n\n"
        "Extracted value linkage:\n"
        "  normalized_code / fact_code = ExtractedValue.normalized_code (LLM or regex extractors)\n"
        "  Normalization writes FinancialStatementFact rows keyed by the same code.\n"
        "  via_metric shows which CalculatedMetric consumes this fact at engine_scope.\n\n"
        "New columns:\n"
        "  fact_name, statement_type, fact_unit — catalog line-item metadata\n"
        "  via_metric, metric_name, metric_unit — calculated metric that reads the fact\n"
        "  extracted_value_fields — ExtractedValue columns populated at ingest\n"
        "  pipeline_chain — full ingest pipeline path to GeneratedSignal\n\n"
        "Period filter columns (Y/N):\n"
        "  CY  = current quarter (engine scope CURRENT)\n"
        "  PY  = prior-year same quarter (engine scope PY)\n"
        "  CQ  = prior quarter (engine scope PQ)\n"
        "  TTM = trailing four quarters\n"
        "  AVG = average of current + prior-year opening/closing\n\n"
        "Regenerate: python -m app.scripts.export_signals_full\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
