"""Idempotent catalog seeder for CapitalNerve.

This is the only seed that runs in production. It writes the **reference
data** the pipeline relies on — line items, metric definitions, signal
definitions, financial periods, and a minimal sector list — and nothing
else. No companies, events, cards, evidence, or users are created here;
those come from real ingestion via ``POST /ingest/upload``.

Run manually with::

    python -m app.seed.seed_catalog

Re-running is safe: every insert is guarded by an existence check, and
metric/signal engine fields are refreshed in place so older databases pick
up new formulas / rules without manual surgery.
"""
from __future__ import annotations

import os
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.enums import (
    PeriodType,
    SeverityLevel,
    SignalDirection,
    StatementType,
    UserType,
)
from app.db.session import SessionLocal
from app.models.facts import FinancialLineItemDefinition
from app.models.intelligence import MetricDefinition, SignalDefinition
from app.models.master import FinancialPeriod, Sector
from app.models.user import AppUser


# ---------------------------------------------------------------------------
# Sectors
# ---------------------------------------------------------------------------

SECTORS = [
    {"sector_name": "Telecom Services", "industry": "Communications Services"},
    {"sector_name": "IT Services", "industry": "Information Technology"},
    {"sector_name": "Pharma & Biotech", "industry": "Healthcare"},
    {"sector_name": "Capital Goods", "industry": "Industrials"},
    {"sector_name": "Financial Services", "industry": "Financials"},
    {"sector_name": "Consumer", "industry": "Consumer"},
    {"sector_name": "Energy", "industry": "Energy"},
    {"sector_name": "Auto & Ancillaries", "industry": "Automobiles"},
    {"sector_name": "Materials", "industry": "Materials"},
    {"sector_name": "Real Estate", "industry": "Real Estate"},
    {"sector_name": "Utilities", "industry": "Utilities"},
]


# ---------------------------------------------------------------------------
# Financial line items
# ---------------------------------------------------------------------------

LINE_ITEMS: list[tuple[str, str, StatementType]] = [
    # ---------------- P&L ----------------
    ("revenue_from_operations", "Revenue from Operations", StatementType.PROFIT_AND_LOSS),
    ("other_income", "Other Income", StatementType.PROFIT_AND_LOSS),
    ("total_income", "Total Income", StatementType.PROFIT_AND_LOSS),
    ("employee_cost", "Employee Benefit Expenses", StatementType.PROFIT_AND_LOSS),
    ("finance_cost", "Finance Costs", StatementType.PROFIT_AND_LOSS),
    ("depreciation", "Depreciation & Amortisation", StatementType.PROFIT_AND_LOSS),
    ("other_expenses", "Other Expenses", StatementType.PROFIT_AND_LOSS),
    ("ebitda", "EBITDA", StatementType.PROFIT_AND_LOSS),
    ("ebitda_margin", "EBITDA Margin", StatementType.PROFIT_AND_LOSS),
    ("ebit", "EBIT", StatementType.PROFIT_AND_LOSS),
    ("pbt", "Profit Before Tax", StatementType.PROFIT_AND_LOSS),
    ("tax_expense", "Tax Expense", StatementType.PROFIT_AND_LOSS),
    ("pat", "Profit After Tax", StatementType.PROFIT_AND_LOSS),
    ("eps_basic", "EPS (Basic)", StatementType.PROFIT_AND_LOSS),
    ("eps_diluted", "EPS (Diluted)", StatementType.PROFIT_AND_LOSS),
    ("exceptional_items", "Exceptional Items", StatementType.PROFIT_AND_LOSS),
    ("cogs", "Cost of Goods Sold", StatementType.PROFIT_AND_LOSS),
    # ---------------- Cash flow ----------------
    ("cfo", "Cash Flow from Operations", StatementType.CASH_FLOW),
    ("capex_ppe", "Capex (PPE)", StatementType.CASH_FLOW),
    ("capex_intangibles", "Capex (Intangibles)", StatementType.CASH_FLOW),
    ("dividend_paid", "Dividends Paid", StatementType.CASH_FLOW),
    ("interest_paid", "Interest Paid", StatementType.CASH_FLOW),
    ("borrowings_raised", "Borrowings Raised", StatementType.CASH_FLOW),
    # ---------------- Balance sheet ----------------
    ("trade_receivables", "Trade Receivables", StatementType.BALANCE_SHEET),
    ("inventory", "Inventory", StatementType.BALANCE_SHEET),
    ("trade_payables", "Trade Payables", StatementType.BALANCE_SHEET),
    ("current_assets", "Current Assets", StatementType.BALANCE_SHEET),
    ("current_liabilities", "Current Liabilities", StatementType.BALANCE_SHEET),
    ("short_term_borrowings", "Short-Term Borrowings", StatementType.BALANCE_SHEET),
    ("long_term_borrowings", "Long-Term Borrowings", StatementType.BALANCE_SHEET),
    ("lease_liabilities", "Lease Liabilities", StatementType.BALANCE_SHEET),
    ("cash_and_equivalents", "Cash & Equivalents", StatementType.BALANCE_SHEET),
    ("current_investments", "Current Investments", StatementType.BALANCE_SHEET),
    ("share_capital", "Share Capital", StatementType.BALANCE_SHEET),
    ("other_equity", "Other Equity", StatementType.BALANCE_SHEET),
    ("shareholders_equity", "Shareholders' Equity", StatementType.BALANCE_SHEET),
    ("total_assets", "Total Assets", StatementType.BALANCE_SHEET),
    ("total_liabilities", "Total Liabilities", StatementType.BALANCE_SHEET),
    # ---------------- Notes / non-statement ----------------
    ("promoter_holding_pct", "Promoter Holding %", StatementType.NOTES),
    ("promoter_pledge_pct", "Promoter Pledge %", StatementType.NOTES),
    ("fii_holding_pct", "FII Holding %", StatementType.NOTES),
    ("dii_holding_pct", "DII Holding %", StatementType.NOTES),
    ("public_holding_pct", "Public Holding %", StatementType.NOTES),
    ("revenue_guidance_lower", "Revenue Guidance (lower)", StatementType.NOTES),
    ("revenue_guidance_upper", "Revenue Guidance (upper)", StatementType.NOTES),
    ("ebitda_margin_guidance_lower", "EBITDA Margin Guidance (lower)", StatementType.NOTES),
    ("ebitda_margin_guidance_upper", "EBITDA Margin Guidance (upper)", StatementType.NOTES),
    ("opening_order_book", "Opening Order Book", StatementType.NOTES),
    ("closing_order_book", "Closing Order Book", StatementType.NOTES),
    ("order_inflow", "Order Inflow", StatementType.NOTES),
    ("executed_orders", "Executed Orders", StatementType.NOTES),
    ("cancelled_orders", "Cancelled Orders", StatementType.NOTES),
    ("top_customer_orders", "Top-Customer Orders", StatementType.NOTES),
    # Concall NLP scores (numeric 0..100) — stored as facts so the metric
    # engine and signal engine treat them identically to financial values.
    ("concall_confidence_score", "Management Confidence Score", StatementType.NOTES),
    ("concall_uncertainty_score", "Management Uncertainty Score", StatementType.NOTES),
    ("concall_evasive_score", "Management Evasive Score", StatementType.NOTES),
    ("concall_demand_score", "Concall Demand Score", StatementType.NOTES),
    ("concall_cost_pressure_score", "Concall Cost-Pressure Score", StatementType.NOTES),
    ("concall_pricing_power_score", "Concall Pricing-Power Score", StatementType.NOTES),
    # Market data — ingested via /v1/market-data, stored as facts on the
    # event's period so valuation metrics stay period-keyed.
    ("share_price_close", "Share Price (Close)", StatementType.NOTES),
    ("avg_volume_20d", "20-day Average Volume", StatementType.NOTES),
    ("volume", "Volume", StatementType.NOTES),
    ("delivery_pct", "Delivery %", StatementType.NOTES),
    ("market_cap", "Market Cap", StatementType.NOTES),
    ("pre_event_close", "Pre-Event Close", StatementType.NOTES),
    ("post_event_close", "Post-Event Close", StatementType.NOTES),
]


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

# Each metric definition is a dict keyed by the columns the engine reads:
#   code, name, category, formula, unit, is_pct, is_bps, inputs, deps
# The engine looks up `inputs` via InputResolver (scope CURRENT/PQ/PY/TTM/...)
# and evaluates `formula` via the AST allowlist in `services/pipeline/formula.py`.
def _m(
    code: str,
    name: str,
    category: str,
    formula: str,
    unit: str,
    *,
    is_pct: bool = False,
    is_bps: bool = False,
    inputs: list[dict] | None = None,
    deps: list[str] | None = None,
) -> dict:
    return {
        "code": code,
        "name": name,
        "category": category,
        "formula": formula,
        "unit": unit,
        "is_pct": is_pct,
        "is_bps": is_bps,
        "inputs": inputs or [],
        "deps": deps or [],
    }


def _i(name: str, code: str, scope: str = "CURRENT", *, kind: str = "fact") -> dict:
    return {"name": name, "code": code, "scope": scope, "kind": kind}


METRIC_DEFS: list[dict] = [
    # ---------------- Phase 1 — P&L (Growth, Margin, Profit, Earnings Quality) ----------------
    _m(
        "revenue_yoy_growth", "Revenue YoY Growth", "growth",
        "(revenue - revenue_py) / revenue_py * 100", "%", is_pct=True,
        inputs=[
            _i("revenue", "revenue_from_operations", "CURRENT"),
            _i("revenue_py", "revenue_from_operations", "PY"),
        ],
    ),
    _m(
        "revenue_qoq_growth", "Revenue QoQ Growth", "growth",
        "(revenue - revenue_pq) / revenue_pq * 100", "%", is_pct=True,
        inputs=[
            _i("revenue", "revenue_from_operations", "CURRENT"),
            _i("revenue_pq", "revenue_from_operations", "PQ"),
        ],
    ),
    _m(
        "ebitda_growth_yoy", "EBITDA Growth YoY", "growth",
        "(ebitda - ebitda_py) / ebitda_py * 100", "%", is_pct=True,
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
            _i("ebitda_py", "ebitda", "PY"),
        ],
    ),
    _m(
        "pat_growth_yoy", "PAT Growth YoY", "growth",
        "(pat - pat_py) / pat_py * 100", "%", is_pct=True,
        inputs=[
            _i("pat", "pat", "CURRENT"),
            _i("pat_py", "pat", "PY"),
        ],
    ),
    _m(
        "pat_growth_qoq", "PAT Growth QoQ", "growth",
        "(pat - pat_pq) / pat_pq * 100", "%", is_pct=True,
        inputs=[
            _i("pat", "pat", "CURRENT"),
            _i("pat_pq", "pat", "PQ"),
        ],
    ),
    _m(
        "ebitda_margin", "EBITDA Margin", "margin",
        "ebitda / revenue * 100", "%", is_pct=True,
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
    ),
    _m(
        "ebitda_margin_change_yoy_bps", "EBITDA Margin Change YoY", "margin",
        "(ebitda / revenue - ebitda_py / revenue_py) * 10000", "bps", is_bps=True,
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
            _i("ebitda_py", "ebitda", "PY"),
            _i("revenue_py", "revenue_from_operations", "PY"),
        ],
    ),
    _m(
        "pat_margin", "PAT Margin", "margin",
        "pat / revenue * 100", "%", is_pct=True,
        inputs=[
            _i("pat", "pat", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
    ),
    _m(
        "other_income_to_pbt", "Other Income to PBT", "profit_quality",
        "other_income / pbt * 100", "%", is_pct=True,
        inputs=[
            _i("other_income", "other_income", "CURRENT"),
            _i("pbt", "pbt", "CURRENT"),
        ],
    ),
    _m(
        "exceptional_to_pat", "Exceptional Items / PAT", "earnings_quality",
        "exceptional_items / pat * 100", "%", is_pct=True,
        inputs=[
            _i("exceptional_items", "exceptional_items", "CURRENT"),
            _i("pat", "pat", "CURRENT"),
        ],
    ),
    _m(
        "effective_tax_rate", "Effective Tax Rate", "profit_quality",
        "tax / pbt * 100", "%", is_pct=True,
        inputs=[
            _i("tax", "tax_expense", "CURRENT"),
            _i("pbt", "pbt", "CURRENT"),
        ],
    ),
    _m(
        "finance_cost_burden", "Finance Cost Burden", "expense",
        "finance_cost / ebitda * 100", "%", is_pct=True,
        inputs=[
            _i("finance_cost", "finance_cost", "CURRENT"),
            _i("ebitda", "ebitda", "CURRENT"),
        ],
    ),
    _m(
        "interest_coverage", "Interest Coverage", "debt",
        "(ebitda - depreciation) / finance_cost", "x",
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
            _i("depreciation", "depreciation", "CURRENT"),
            _i("finance_cost", "finance_cost", "CURRENT"),
        ],
    ),
    # ---------------- Phase 2 — Cash flow + Working capital ----------------
    _m(
        "cfo_to_pat", "CFO to PAT", "cash_quality",
        "cfo / pat", "x",
        inputs=[
            _i("cfo", "cfo", "CURRENT"),
            _i("pat", "pat", "CURRENT"),
        ],
    ),
    _m(
        "cash_conversion_ratio", "Cash Conversion Ratio", "cashflow",
        "cfo / pat", "x",
        inputs=[
            _i("cfo", "cfo", "CURRENT"),
            _i("pat", "pat", "CURRENT"),
        ],
    ),
    _m(
        "fcf", "Free Cash Flow", "cashflow",
        "cfo - capex_ppe - capex_intangibles", "crore",
        inputs=[
            _i("cfo", "cfo", "CURRENT"),
            _i("capex_ppe", "capex_ppe", "CURRENT"),
            _i("capex_intangibles", "capex_intangibles", "CURRENT"),
        ],
    ),
    _m(
        "fcf_margin", "FCF Margin", "cashflow",
        "fcf_value / revenue * 100", "%", is_pct=True,
        inputs=[
            _i("fcf_value", "fcf", "CURRENT", kind="metric"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
        deps=["fcf"],
    ),
    _m(
        "receivables_growth_yoy", "Receivables Growth YoY", "working_capital",
        "(rec - rec_py) / rec_py * 100", "%", is_pct=True,
        inputs=[
            _i("rec", "trade_receivables", "CURRENT"),
            _i("rec_py", "trade_receivables", "PY"),
        ],
    ),
    _m(
        "inventory_growth_yoy", "Inventory Growth YoY", "working_capital",
        "(inv - inv_py) / inv_py * 100", "%", is_pct=True,
        inputs=[
            _i("inv", "inventory", "CURRENT"),
            _i("inv_py", "inventory", "PY"),
        ],
    ),
    _m(
        "payables_growth_yoy", "Payables Growth YoY", "working_capital",
        "(pay - pay_py) / pay_py * 100", "%", is_pct=True,
        inputs=[
            _i("pay", "trade_payables", "CURRENT"),
            _i("pay_py", "trade_payables", "PY"),
        ],
    ),
    _m(
        "dso", "Days Sales Outstanding", "working_capital",
        "avg_rec / revenue * 91", "days",
        inputs=[
            _i("avg_rec", "trade_receivables", "AVG_2_OPENING_CLOSING"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
    ),
    _m(
        "dio", "Days Inventory Outstanding", "working_capital",
        "avg_inv / cogs * 91", "days",
        inputs=[
            _i("avg_inv", "inventory", "AVG_2_OPENING_CLOSING"),
            _i("cogs", "cogs", "CURRENT"),
        ],
    ),
    _m(
        "dpo", "Days Payables Outstanding", "working_capital",
        "avg_pay / cogs * 91", "days",
        inputs=[
            _i("avg_pay", "trade_payables", "AVG_2_OPENING_CLOSING"),
            _i("cogs", "cogs", "CURRENT"),
        ],
    ),
    _m(
        "cash_conversion_cycle", "Cash Conversion Cycle", "working_capital",
        "dso_v + dio_v - dpo_v", "days",
        inputs=[
            _i("dso_v", "dso", "CURRENT", kind="metric"),
            _i("dio_v", "dio", "CURRENT", kind="metric"),
            _i("dpo_v", "dpo", "CURRENT", kind="metric"),
        ],
        deps=["dso", "dio", "dpo"],
    ),
    _m(
        "receivables_growth_minus_revenue_growth_bps",
        "Receivables Growth − Revenue Growth (bps)",
        "working_capital",
        "(rec_g - rev_g) * 100", "bps", is_bps=True,
        inputs=[
            _i("rec_g", "receivables_growth_yoy", "CURRENT", kind="metric"),
            _i("rev_g", "revenue_yoy_growth", "CURRENT", kind="metric"),
        ],
        deps=["receivables_growth_yoy", "revenue_yoy_growth"],
    ),
    # ---------------- Phase 3 — Balance sheet (Debt, Solvency) ----------------
    _m(
        "total_debt", "Total Debt", "debt",
        "short + long + lease", "crore",
        inputs=[
            _i("short", "short_term_borrowings", "CURRENT"),
            _i("long", "long_term_borrowings", "CURRENT"),
            _i("lease", "lease_liabilities", "CURRENT"),
        ],
    ),
    _m(
        "net_debt", "Net Debt", "debt",
        "td - cash - inv", "crore",
        inputs=[
            _i("td", "total_debt", "CURRENT", kind="metric"),
            _i("cash", "cash_and_equivalents", "CURRENT"),
            _i("inv", "current_investments", "CURRENT"),
        ],
        deps=["total_debt"],
    ),
    _m(
        "ttm_ebitda", "TTM EBITDA", "debt",
        "ttm", "crore",
        inputs=[_i("ttm", "ebitda", "TTM")],
    ),
    _m(
        "net_debt_to_ebitda", "Net Debt / EBITDA", "debt",
        "nd / ebitda", "x",
        inputs=[
            _i("nd", "net_debt", "CURRENT", kind="metric"),
            _i("ebitda", "ttm_ebitda", "CURRENT", kind="metric"),
        ],
        deps=["net_debt", "ttm_ebitda"],
    ),
    _m(
        "debt_to_equity", "Debt / Equity", "solvency",
        "td / equity", "x",
        inputs=[
            _i("td", "total_debt", "CURRENT", kind="metric"),
            _i("equity", "shareholders_equity", "CURRENT"),
        ],
        deps=["total_debt"],
    ),
    # ---------------- Phase 4a — Market valuation / reaction ----------------
    _m(
        "ttm_eps", "TTM EPS", "valuation",
        "ttm", "Rs",
        inputs=[_i("ttm", "eps_basic", "TTM")],
    ),
    _m(
        "pe_ratio", "P / E", "valuation",
        "price / eps", "x",
        inputs=[
            _i("price", "share_price_close", "CURRENT"),
            _i("eps", "ttm_eps", "CURRENT", kind="metric"),
        ],
        deps=["ttm_eps"],
    ),
    _m(
        "ev_ebitda", "EV / EBITDA", "valuation",
        "(mcap + td - cash) / ebitda", "x",
        inputs=[
            _i("mcap", "market_cap", "CURRENT"),
            _i("td", "total_debt", "CURRENT", kind="metric"),
            _i("cash", "cash_and_equivalents", "CURRENT"),
            _i("ebitda", "ttm_ebitda", "CURRENT", kind="metric"),
        ],
        deps=["total_debt", "ttm_ebitda"],
    ),
    _m(
        "event_price_reaction", "Event Price Reaction", "market_reaction",
        "(post - pre) / pre * 100", "%", is_pct=True,
        inputs=[
            _i("pre", "pre_event_close", "CURRENT"),
            _i("post", "post_event_close", "CURRENT"),
        ],
    ),
    _m(
        "volume_spike", "Volume Spike", "market_reaction",
        "vol / avg_vol", "x",
        inputs=[
            _i("vol", "volume", "CURRENT"),
            _i("avg_vol", "avg_volume_20d", "CURRENT"),
        ],
    ),
    # ---------------- Phase 4b — Shareholding (Governance) ----------------
    _m(
        "promoter_holding_change_qoq_bps", "Promoter Holding Change QoQ", "governance",
        "(now - pq) * 100", "bps", is_bps=True,
        inputs=[
            _i("now", "promoter_holding_pct", "CURRENT"),
            _i("pq", "promoter_holding_pct", "PQ"),
        ],
    ),
    _m(
        "promoter_pledge_pct", "Promoter Pledge %", "governance",
        "p", "%", is_pct=True,
        inputs=[_i("p", "promoter_pledge_pct", "CURRENT")],
    ),
    _m(
        "promoter_pledge_change_bps", "Promoter Pledge Change QoQ", "governance",
        "(now - pq) * 100", "bps", is_bps=True,
        inputs=[
            _i("now", "promoter_pledge_pct", "CURRENT"),
            _i("pq", "promoter_pledge_pct", "PQ"),
        ],
    ),
    _m(
        "fii_holding_change_qoq_bps", "FII Holding Change QoQ", "governance",
        "(now - pq) * 100", "bps", is_bps=True,
        inputs=[
            _i("now", "fii_holding_pct", "CURRENT"),
            _i("pq", "fii_holding_pct", "PQ"),
        ],
    ),
    _m(
        "dii_holding_change_qoq_bps", "DII Holding Change QoQ", "governance",
        "(now - pq) * 100", "bps", is_bps=True,
        inputs=[
            _i("now", "dii_holding_pct", "CURRENT"),
            _i("pq", "dii_holding_pct", "PQ"),
        ],
    ),
    # ---------------- Phase 4c — Guidance ----------------
    _m(
        "revenue_guidance_midpoint", "Revenue Guidance Midpoint", "guidance",
        "(lo + hi) / 2", "crore",
        inputs=[
            _i("lo", "revenue_guidance_lower", "CURRENT"),
            _i("hi", "revenue_guidance_upper", "CURRENT"),
        ],
    ),
    _m(
        "revenue_guidance_revision_pct",
        "Revenue Guidance Revision",
        "guidance",
        "(now - prior) / prior * 100", "%", is_pct=True,
        inputs=[
            _i("now", "revenue_guidance_midpoint", "CURRENT", kind="metric"),
            _i("prior", "revenue_guidance_midpoint", "PQ", kind="metric"),
        ],
        deps=["revenue_guidance_midpoint"],
    ),
    _m(
        "ebitda_margin_guidance_midpoint",
        "EBITDA Margin Guidance Midpoint", "guidance",
        "(lo + hi) / 2", "%", is_pct=True,
        inputs=[
            _i("lo", "ebitda_margin_guidance_lower", "CURRENT"),
            _i("hi", "ebitda_margin_guidance_upper", "CURRENT"),
        ],
    ),
    # ---------------- Phase 4d — Concall tone ----------------
    _m(
        "management_confidence_score", "Management Confidence", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_confidence_score", "CURRENT")],
    ),
    _m(
        "management_uncertainty_score", "Management Uncertainty", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_uncertainty_score", "CURRENT")],
    ),
    _m(
        "management_evasive_score", "Management Evasive", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_evasive_score", "CURRENT")],
    ),
    _m(
        "management_confidence_change_qoq", "Management Confidence Δ QoQ", "management_tone",
        "now - pq", "score",
        inputs=[
            _i("now", "concall_confidence_score", "CURRENT"),
            _i("pq", "concall_confidence_score", "PQ"),
        ],
    ),
    # ---------------- Phase 4e — Order book ----------------
    _m(
        "order_book_growth_yoy", "Order Book Growth YoY", "order_book",
        "(now - py) / py * 100", "%", is_pct=True,
        inputs=[
            _i("now", "closing_order_book", "CURRENT"),
            _i("py", "closing_order_book", "PY"),
        ],
    ),
    _m(
        "book_to_bill", "Book-to-Bill", "order_book",
        "inflow / revenue", "x",
        inputs=[
            _i("inflow", "order_inflow", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
    ),
    _m(
        "order_book_to_revenue", "Order Book / Revenue (x)", "order_book",
        "ob / revenue", "x",
        inputs=[
            _i("ob", "closing_order_book", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
    ),
    _m(
        "order_concentration_pct", "Top-Customer Concentration", "order_book",
        "top / ob * 100", "%", is_pct=True,
        inputs=[
            _i("top", "top_customer_orders", "CURRENT"),
            _i("ob", "closing_order_book", "CURRENT"),
        ],
    ),
    _m(
        "order_cancellation_rate", "Order Cancellation Rate", "order_book",
        "cancelled / inflow * 100", "%", is_pct=True,
        inputs=[
            _i("cancelled", "cancelled_orders", "CURRENT"),
            _i("inflow", "order_inflow", "CURRENT"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

def _s(
    code: str,
    name: str,
    category: str,
    desc: str,
    rule: dict,
    direction: SignalDirection | None,
    severity: SeverityLevel | None,
) -> dict:
    return {
        "code": code,
        "name": name,
        "category": category,
        "desc": desc,
        "rule": rule,
        "direction": direction,
        "severity": severity,
    }


def _leaf(metric: str, op: str, threshold: float | None = None, *, metric_ref: str | None = None) -> dict:
    leaf: dict = {"metric": metric, "operator": op}
    if metric_ref is not None:
        leaf["metric_ref"] = metric_ref
    else:
        leaf["threshold"] = threshold
    return leaf


SIGNAL_DEFS: list[dict] = [
    # ---------------- Phase 1 — P&L ----------------
    _s(
        "weak_profit_quality_other_income", "Weak Profit Quality: Other Income Dependency",
        "profit_quality", "Other income forms a large percentage of PBT.",
        _leaf("other_income_to_pbt", ">", 20),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "margin_compression", "Margin Compression",
        "margin", "EBITDA margin declined materially YoY.",
        _leaf("ebitda_margin_change_yoy_bps", "<", -100),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "margin_expansion", "Margin Expansion",
        "margin", "EBITDA margin expanded YoY.",
        _leaf("ebitda_margin_change_yoy_bps", ">", 100),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_acceleration", "Revenue Growth Acceleration",
        "growth", "Revenue YoY growth above 15%.",
        _leaf("revenue_yoy_growth", ">", 15),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_deceleration", "Revenue Growth Deceleration",
        "growth", "Revenue YoY growth slowed versus the prior trend.",
        _leaf("revenue_yoy_growth", "<", 8),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_contraction", "Revenue Contraction",
        "growth", "Revenue YoY growth turned negative.",
        _leaf("revenue_yoy_growth", "<", 0),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "finance_cost_pressure", "Finance Cost Pressure",
        "expense", "Finance costs absorb a heavy share of EBITDA.",
        _leaf("finance_cost_burden", ">", 25),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "pat_decline_despite_revenue_growth",
        "PAT Down Despite Revenue Growth", "earnings_quality",
        "PAT contracted YoY while revenue grew.",
        {"all": [
            _leaf("pat_growth_yoy", "<", 0),
            _leaf("revenue_yoy_growth", ">", 0),
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "dirty_beat", "Dirty Beat",
        "earnings_quality",
        "PAT growth flattered by other income or exceptional items.",
        {"all": [
            _leaf("pat_growth_yoy", ">", 10),
            {"any": [
                _leaf("other_income_to_pbt", ">", 20),
                _leaf("exceptional_to_pat", ">", 15),
            ]},
        ]},
        SignalDirection.MIXED, SeverityLevel.HIGH,
    ),
    _s(
        "clean_beat", "Clean Beat",
        "earnings_quality",
        "Revenue, EBITDA, and PAT all up YoY with healthy other-income share.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 10),
            _leaf("ebitda_growth_yoy", ">", 10),
            _leaf("pat_growth_yoy", ">", 10),
            _leaf("other_income_to_pbt", "<", 15),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.HIGH,
    ),
    # ---------------- Phase 2 — Cash flow / Working capital ----------------
    _s(
        "low_quality_growth", "Low-Quality Growth",
        "cash_quality",
        "Revenue growing but cash conversion weak or receivables growing far faster than revenue.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 10),
            {"any": [
                _leaf("cfo_to_pat", "<", 0.6),
                _leaf("receivables_growth_minus_revenue_growth_bps", ">", 1500),
            ]},
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "high_quality_growth", "High-Quality Growth",
        "cash_quality",
        "Revenue + margin up, cash conversion strong, receivables tame.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 10),
            _leaf("ebitda_margin_change_yoy_bps", ">", 0),
            _leaf("cfo_to_pat", ">", 0.8),
            _leaf("receivables_growth_minus_revenue_growth_bps", "<", 500),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.HIGH,
    ),
    _s(
        "channel_stuffing_risk", "Channel-Stuffing Risk",
        "earnings_quality",
        "Receivables growing materially faster than revenue.",
        _leaf("receivables_growth_minus_revenue_growth_bps", ">", 2000),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "working_capital_stress", "Working Capital Stress",
        "working_capital",
        "Cash conversion cycle expanded materially.",
        _leaf("cash_conversion_cycle", ">", 90),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "fcf_positive", "FCF Positive",
        "cashflow", "Free cash flow turned positive.",
        _leaf("fcf", ">", 0),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "fcf_negative", "FCF Negative",
        "cashflow", "Free cash flow turned negative this period.",
        _leaf("fcf", "<", 0),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 3 — Debt / Solvency ----------------
    _s(
        "leverage_risk", "Leverage Risk",
        "debt", "Net debt to EBITDA above 3x.",
        _leaf("net_debt_to_ebitda", ">", 3),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "deleveraging", "Deleveraging",
        "debt", "Net debt to EBITDA below 1x — comfortable solvency.",
        _leaf("net_debt_to_ebitda", "<", 1),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "interest_coverage_weakness", "Interest Coverage Weakness",
        "debt", "Interest coverage below 3x.",
        _leaf("interest_coverage", "<", 3),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "interest_coverage_improvement", "Interest Coverage Improvement",
        "debt", "Interest coverage comfortably above 8x.",
        _leaf("interest_coverage", ">", 8),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "debt_funded_growth", "Debt-Funded Growth",
        "debt",
        "Revenue growth + leverage up + interest coverage low.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 10),
            _leaf("net_debt_to_ebitda", ">", 2.5),
            _leaf("interest_coverage", "<", 4),
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    # ---------------- Phase 4a — Market reaction / valuation ----------------
    _s(
        "valuation_rerating", "Valuation Re-rating",
        "valuation", "P/E expanded materially (above 30x).",
        _leaf("pe_ratio", ">", 30),
        SignalDirection.MIXED, SeverityLevel.MEDIUM,
    ),
    _s(
        "valuation_derating", "Valuation De-rating",
        "valuation", "P/E compressed below 10x.",
        _leaf("pe_ratio", "<", 10),
        SignalDirection.MIXED, SeverityLevel.MEDIUM,
    ),
    _s(
        "positive_event_reaction", "Positive Event Reaction",
        "market_reaction", "Stock up >5% in event window.",
        _leaf("event_price_reaction", ">", 5),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "negative_event_reaction", "Negative Event Reaction",
        "market_reaction", "Stock down >5% in event window.",
        _leaf("event_price_reaction", "<", -5),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "volume_confirmation", "Volume Confirmation",
        "market_reaction",
        "Volume spike + positive reaction confirms move.",
        {"all": [
            _leaf("volume_spike", ">", 2),
            _leaf("event_price_reaction", ">", 3),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "speculative_spike", "Speculative Spike",
        "market_reaction",
        "Volume spike but small price move — likely positioning, not conviction.",
        {"all": [
            _leaf("volume_spike", ">", 3),
            _leaf("event_price_reaction", "<", 2),
            _leaf("event_price_reaction", ">", -2),
        ]},
        SignalDirection.MIXED, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 4b — Governance / shareholding ----------------
    _s(
        "promoter_buying", "Promoter Buying",
        "governance", "Promoter holding ticked up QoQ.",
        _leaf("promoter_holding_change_qoq_bps", ">", 50),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "promoter_selling", "Promoter Selling",
        "governance", "Promoter holding fell QoQ.",
        _leaf("promoter_holding_change_qoq_bps", "<", -50),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "pledge_risk", "Promoter Pledge Risk",
        "governance", "Promoter pledge above 25% of holding.",
        _leaf("promoter_pledge_pct", ">", 25),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "pledge_reduction", "Pledge Reduction",
        "governance", "Promoter pledge fell QoQ.",
        _leaf("promoter_pledge_change_bps", "<", -50),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "fii_accumulation", "FII Accumulation",
        "governance", "FII holding rose QoQ.",
        _leaf("fii_holding_change_qoq_bps", ">", 50),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "fii_exit", "FII Exit",
        "governance", "FII holding fell QoQ.",
        _leaf("fii_holding_change_qoq_bps", "<", -50),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "governance_red_flag", "Governance Red Flag",
        "governance",
        "Pledge high and rising or promoter selling materially.",
        {"any": [
            {"all": [
                _leaf("promoter_pledge_pct", ">", 25),
                _leaf("promoter_pledge_change_bps", ">", 100),
            ]},
            _leaf("promoter_holding_change_qoq_bps", "<", -100),
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.CRITICAL,
    ),
    # ---------------- Phase 4c — Guidance ----------------
    _s(
        "guidance_upgrade", "Guidance Upgrade",
        "guidance", "Revenue guidance raised >2%.",
        _leaf("revenue_guidance_revision_pct", ">", 2),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "guidance_downgrade", "Guidance Downgrade",
        "guidance", "Revenue guidance cut >2%.",
        _leaf("revenue_guidance_revision_pct", "<", -2),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    # ---------------- Phase 4d — Management tone ----------------
    _s(
        "management_confidence_improving", "Management Confidence Improving",
        "management_tone",
        "Confidence score rose meaningfully QoQ.",
        _leaf("management_confidence_change_qoq", ">", 10),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "management_confidence_falling", "Management Confidence Falling",
        "management_tone",
        "Confidence score fell QoQ.",
        _leaf("management_confidence_change_qoq", "<", -10),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "high_uncertainty", "High Management Uncertainty",
        "management_tone",
        "Concall language is unusually hedged.",
        _leaf("management_uncertainty_score", ">", 60),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 4e — Order book ----------------
    _s(
        "order_book_growth", "Order Book Growth",
        "order_book", "Order book grew materially YoY.",
        _leaf("order_book_growth_yoy", ">", 20),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "book_to_bill_strength", "Book-to-Bill Strength",
        "order_book", "Book-to-bill above 1.2x.",
        _leaf("book_to_bill", ">", 1.2),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_visibility_strong", "Strong Revenue Visibility",
        "order_book", "Order book covers >2x annualised revenue.",
        _leaf("order_book_to_revenue", ">", 2),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "order_concentration_risk", "Order Concentration Risk",
        "order_book", "Top customer orders > 30% of book.",
        _leaf("order_concentration_pct", ">", 30),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "order_cancellation_risk", "Order Cancellation Risk",
        "order_book", "Cancellation rate above 10% of inflow.",
        _leaf("order_cancellation_rate", ">", 10),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    # ---------------- Manual / fact-driven (no numeric rule) ----------------
    _s(
        "management_caution", "Cautious Management Tone",
        "management",
        "Management commentary cautious on near-term outlook.",
        {},
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "audit_redflag", "Auditor / Notes Red Flag",
        "red_flag",
        "Material item flagged in auditor's report or notes.",
        {},
        SignalDirection.NEGATIVE, SeverityLevel.CRITICAL,
    ),
    # ---------------- Phase 5 — Cross-card composites ----------------
    _s(
        "value_trap", "Value Trap",
        "valuation",
        "Cheap on P/E but earnings quality weak.",
        {"all": [
            _leaf("pe_ratio", "<", 12),
            {"any": [
                _leaf("revenue_yoy_growth", "<", 0),
                _leaf("cfo_to_pat", "<", 0.5),
            ]},
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "rerating_candidate", "Re-rating Candidate",
        "valuation",
        "Cheap valuation + clean operating performance.",
        {"all": [
            _leaf("pe_ratio", "<", 18),
            _leaf("revenue_yoy_growth", ">", 12),
            _leaf("cfo_to_pat", ">", 0.8),
            _leaf("ebitda_margin_change_yoy_bps", ">", 0),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.HIGH,
    ),
    _s(
        "turnaround", "Turnaround",
        "earnings_quality",
        "Margin expansion + PAT growth + improving management tone.",
        {"all": [
            _leaf("ebitda_margin_change_yoy_bps", ">", 100),
            _leaf("pat_growth_yoy", ">", 15),
            _leaf("management_confidence_change_qoq", ">", 5),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.HIGH,
    ),
    _s(
        "narrative_mismatch", "Narrative Mismatch",
        "management_tone",
        "Confident commentary paired with weak metrics.",
        {"all": [
            _leaf("management_confidence_score", ">", 65),
            {"any": [
                _leaf("revenue_yoy_growth", "<", 5),
                _leaf("ebitda_margin_change_yoy_bps", "<", -100),
            ]},
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
]


# ---------------------------------------------------------------------------
# Financial periods (rolling 8 quarters)
# ---------------------------------------------------------------------------

PERIODS = [
    {"fy_year": 2025, "fy_label": "FY2025-26", "quarter": 1, "start": date(2025, 4, 1), "end": date(2025, 6, 30), "display": "Q1 FY2025-26"},
    {"fy_year": 2025, "fy_label": "FY2025-26", "quarter": 2, "start": date(2025, 7, 1), "end": date(2025, 9, 30), "display": "Q2 FY2025-26"},
    {"fy_year": 2025, "fy_label": "FY2025-26", "quarter": 3, "start": date(2025, 10, 1), "end": date(2025, 12, 31), "display": "Q3 FY2025-26"},
    {"fy_year": 2025, "fy_label": "FY2025-26", "quarter": 4, "start": date(2026, 1, 1), "end": date(2026, 3, 31), "display": "Q4 FY2025-26"},
    # Prior year periods for YoY anchors
    {"fy_year": 2024, "fy_label": "FY2024-25", "quarter": 1, "start": date(2024, 4, 1), "end": date(2024, 6, 30), "display": "Q1 FY2024-25"},
    {"fy_year": 2024, "fy_label": "FY2024-25", "quarter": 2, "start": date(2024, 7, 1), "end": date(2024, 9, 30), "display": "Q2 FY2024-25"},
    {"fy_year": 2024, "fy_label": "FY2024-25", "quarter": 3, "start": date(2024, 10, 1), "end": date(2024, 12, 31), "display": "Q3 FY2024-25"},
    {"fy_year": 2024, "fy_label": "FY2024-25", "quarter": 4, "start": date(2025, 1, 1), "end": date(2025, 3, 31), "display": "Q4 FY2024-25"},
]


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------


def upsert_sectors(db: Session) -> dict[str, Sector]:
    out: dict[str, Sector] = {}
    for s in SECTORS:
        existing = db.scalar(select(Sector).where(Sector.sector_name == s["sector_name"]))
        if existing:
            out[s["sector_name"]] = existing
            continue
        sector = Sector(sector_name=s["sector_name"], industry=s["industry"])
        db.add(sector)
        db.flush()
        out[s["sector_name"]] = sector
    db.commit()
    return out


def upsert_periods(db: Session) -> dict[tuple[int, int], FinancialPeriod]:
    out: dict[tuple[int, int], FinancialPeriod] = {}
    for p in PERIODS:
        existing = db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.fy_year == p["fy_year"],
                FinancialPeriod.quarter == p["quarter"],
                FinancialPeriod.period_type == PeriodType.QUARTERLY,
            )
        )
        if existing:
            out[(p["fy_year"], p["quarter"])] = existing
            continue
        fp = FinancialPeriod(
            fy_year=p["fy_year"],
            fy_label=p["fy_label"],
            quarter=p["quarter"],
            period_type=PeriodType.QUARTERLY,
            period_start_date=p["start"],
            period_end_date=p["end"],
            display_label=p["display"],
        )
        db.add(fp)
        db.flush()
        out[(p["fy_year"], p["quarter"])] = fp
    db.commit()
    return out


def upsert_line_items(db: Session) -> dict[str, FinancialLineItemDefinition]:
    out: dict[str, FinancialLineItemDefinition] = {}
    for code, name, stype in LINE_ITEMS:
        existing = db.scalar(
            select(FinancialLineItemDefinition).where(FinancialLineItemDefinition.normalized_code == code)
        )
        if existing:
            out[code] = existing
            continue
        li = FinancialLineItemDefinition(normalized_code=code, display_name=name, statement_type=stype)
        db.add(li)
        db.flush()
        out[code] = li
    db.commit()
    return out


def upsert_metric_defs(db: Session) -> dict[str, MetricDefinition]:
    out: dict[str, MetricDefinition] = {}
    for spec in METRIC_DEFS:
        code = spec["code"]
        existing = db.scalar(select(MetricDefinition).where(MetricDefinition.metric_code == code))
        if existing:
            # Idempotent re-seed: refresh the engine fields so older DBs pick
            # up new inputs/dependencies without manual surgery. Display
            # fields stay sticky to avoid clobbering manual tweaks.
            existing.formula_text = spec["formula"]
            existing.inputs_json = spec["inputs"]
            existing.dependencies_json = spec["deps"]
            existing.metric_category = spec["category"]
            out[code] = existing
            continue
        md = MetricDefinition(
            metric_code=code,
            metric_name=spec["name"],
            metric_category=spec["category"],
            formula_text=spec["formula"],
            unit=spec["unit"],
            is_percentage=spec["is_pct"],
            is_bps=spec["is_bps"],
            inputs_json=spec["inputs"],
            dependencies_json=spec["deps"],
        )
        db.add(md)
        db.flush()
        out[code] = md
    db.commit()
    return out


def upsert_signal_defs(db: Session) -> dict[str, SignalDefinition]:
    out: dict[str, SignalDefinition] = {}
    for spec in SIGNAL_DEFS:
        code = spec["code"]
        existing = db.scalar(select(SignalDefinition).where(SignalDefinition.signal_code == code))
        if existing:
            existing.rule_json = spec["rule"]
            out[code] = existing
            continue
        sd = SignalDefinition(
            signal_code=code,
            signal_name=spec["name"],
            signal_category=spec["category"],
            description=spec["desc"],
            rule_json=spec["rule"],
            default_direction=spec["direction"],
            default_severity=spec["severity"],
        )
        db.add(sd)
        db.flush()
        out[code] = sd
    db.commit()
    return out


def upsert_admin_user(db: Session) -> AppUser | None:
    """Create a single admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars.

    Returns the admin user if env vars are set and creation succeeded, or
    the existing admin if one already exists. Returns ``None`` when the env
    vars are missing — the deployer is expected to run ``POST /auth/signup``
    or set these vars before going live.
    """
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not email or not password:
        return None

    existing = db.scalar(select(AppUser).where(AppUser.email == email))
    if existing:
        return existing

    admin = AppUser(
        email=email,
        full_name=os.environ.get("ADMIN_FULL_NAME", "CapitalNerve Admin"),
        hashed_password=hash_password(password),
        user_type=UserType.ADMIN,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def seed_catalog(db: Session) -> None:
    upsert_sectors(db)
    upsert_periods(db)
    upsert_line_items(db)
    upsert_metric_defs(db)
    upsert_signal_defs(db)
    upsert_admin_user(db)


def main() -> None:
    db = SessionLocal()
    try:
        seed_catalog(db)
        print("Catalog seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
