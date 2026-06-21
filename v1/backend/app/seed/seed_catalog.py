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
    ("concall_capex_intent_score", "Concall Capex Intent Score", StatementType.NOTES),
    ("concall_margin_tone_score", "Concall Margin Tone Score", StatementType.NOTES),
    # Press release / investor deck / segment rollup
    ("dividend_per_share", "Dividend Per Share", StatementType.NOTES),
    ("new_order_value", "New Order Value", StatementType.NOTES),
    ("acquisition_value", "Acquisition Value", StatementType.NOTES),
    ("revenue_contribution_pct", "Revenue Contribution %", StatementType.NOTES),
    ("new_capacity", "New Capacity", StatementType.NOTES),
    ("existing_capacity", "Existing Capacity", StatementType.NOTES),
    ("capacity_utilization_pct", "Capacity Utilization %", StatementType.NOTES),
    ("tam_market_size", "TAM / Market Size", StatementType.NOTES),
    ("tam_market_size_prior", "Prior TAM / Market Size", StatementType.NOTES),
    ("high_margin_revenue_pct", "High-Margin Revenue %", StatementType.NOTES),
    ("top_client_revenue_pct", "Top Client Revenue %", StatementType.NOTES),
    ("region_revenue_pct", "Region Revenue %", StatementType.NOTES),
    ("management_target_value", "Management Target Value", StatementType.NOTES),
    ("primary_segment_revenue", "Primary Segment Revenue", StatementType.SEGMENT),
    ("primary_segment_ebit", "Primary Segment EBIT", StatementType.SEGMENT),
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
    bounds: tuple[float | None, float | None] | None = None,
    kind: str = "financial",
) -> dict:
    """Build a metric-definition row for the seed.

    ``bounds`` is the plausible (min, max) range for the computed value. The
    metrics stage quarantines results outside this range so margins above
    100 % or growth above 500 % never reach the signals/cards layer. Either
    endpoint can be ``None`` for one-sided bounds. ``None`` overall means no
    bound is enforced (e.g. raw absolute values like ``fcf`` in crore).

    ``kind`` is the product-level ontology badge used by the feed:
    ``"financial"`` (derived from facts), ``"model_score"`` (concall lexicon
    scores), or ``"composite"`` (reads from other CalculatedMetric rows).
    """
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
        "bounds": bounds,
        "kind": kind,
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
        bounds=(-100.0, 500.0),
    ),
    _m(
        "revenue_qoq_growth", "Revenue QoQ Growth", "growth",
        "(revenue - revenue_pq) / revenue_pq * 100", "%", is_pct=True,
        inputs=[
            _i("revenue", "revenue_from_operations", "CURRENT"),
            _i("revenue_pq", "revenue_from_operations", "PQ"),
        ],
        # Tightened so seasonal swings stay flagged for review instead of
        # publishing. Anything outside ±80% is treated as a comparator /
        # column-tag mismatch (e.g. YTD column mis-aligned with PQ).
        bounds=(-80.0, 80.0),
    ),
    _m(
        # True acceleration: how much the YoY growth rate itself changed
        # versus the prior quarter's YoY rate. Expressed in percentage
        # points so it stays distinct from the underlying YoY % and the QoQ %.
        "revenue_yoy_growth_acceleration_pp",
        "Revenue YoY Growth Acceleration",
        "growth",
        "now - prior", "pp",
        inputs=[
            _i("now", "revenue_yoy_growth", "CURRENT", kind="metric"),
            _i("prior", "revenue_yoy_growth", "PQ", kind="metric"),
        ],
        deps=["revenue_yoy_growth"],
        bounds=(-100.0, 100.0),
        kind="composite",
    ),
    _m(
        "ebitda_growth_yoy", "EBITDA Growth YoY", "growth",
        "(ebitda - ebitda_py) / ebitda_py * 100", "%", is_pct=True,
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
            _i("ebitda_py", "ebitda", "PY"),
        ],
        bounds=(-500.0, 1000.0),
    ),
    _m(
        "pat_growth_yoy", "PAT Growth YoY", "growth",
        "(pat - pat_py) / pat_py * 100", "%", is_pct=True,
        inputs=[
            _i("pat", "pat", "CURRENT"),
            _i("pat_py", "pat", "PY"),
        ],
        bounds=(-500.0, 1000.0),
    ),
    _m(
        "pat_growth_qoq", "PAT Growth QoQ", "growth",
        "(pat - pat_pq) / pat_pq * 100", "%", is_pct=True,
        inputs=[
            _i("pat", "pat", "CURRENT"),
            _i("pat_pq", "pat", "PQ"),
        ],
        # PAT QoQ can swing on small bases (tax, exceptionals), but >300%
        # in either direction is almost always a column-tag mismatch.
        bounds=(-300.0, 300.0),
    ),
    _m(
        "eps_growth_yoy", "EPS Growth YoY", "growth",
        "(eps - eps_py) / eps_py * 100", "%", is_pct=True,
        inputs=[
            _i("eps", "eps_basic", "CURRENT"),
            _i("eps_py", "eps_basic", "PY"),
        ],
        bounds=(-500.0, 1000.0),
    ),
    _m(
        "ebitda_margin", "EBITDA Margin", "margin",
        "ebitda / revenue * 100", "%", is_pct=True,
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
        bounds=(-50.0, 100.0),
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
        bounds=(-10000.0, 10000.0),
    ),
    _m(
        "pat_margin", "PAT Margin", "margin",
        "pat / revenue * 100", "%", is_pct=True,
        inputs=[
            _i("pat", "pat", "CURRENT"),
            _i("revenue", "revenue_from_operations", "CURRENT"),
        ],
        bounds=(-50.0, 100.0),
    ),
    _m(
        "other_income_to_pbt", "Other Income to PBT", "profit_quality",
        "other_income / pbt * 100", "%", is_pct=True,
        inputs=[
            _i("other_income", "other_income", "CURRENT"),
            _i("pbt", "pbt", "CURRENT"),
        ],
        bounds=(-200.0, 200.0),
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
        bounds=(-100.0, 100.0),
    ),
    _m(
        "finance_cost_burden", "Finance Cost Burden", "expense",
        "finance_cost / ebitda * 100", "%", is_pct=True,
        inputs=[
            _i("finance_cost", "finance_cost", "CURRENT"),
            _i("ebitda", "ebitda", "CURRENT"),
        ],
        bounds=(-200.0, 200.0),
    ),
    _m(
        "interest_coverage", "Interest Coverage", "debt",
        "ebitda / finance_cost", "x",
        inputs=[
            _i("ebitda", "ebitda", "CURRENT"),
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
        bounds=(-20.0, 20.0),
    ),
    _m(
        "cash_conversion_ratio", "Cash Conversion Ratio", "cashflow",
        "cfo / pat", "x",
        inputs=[
            _i("cfo", "cfo", "CURRENT"),
            _i("pat", "pat", "CURRENT"),
        ],
        bounds=(-20.0, 20.0),
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
        bounds=(-100.0, 100.0),
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
        kind="model_score",
    ),
    _m(
        "management_uncertainty_score", "Management Uncertainty", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_uncertainty_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "management_evasive_score", "Management Evasive", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_evasive_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "concall_demand_score", "Concall Demand Score", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_demand_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "concall_cost_pressure_score", "Concall Cost Pressure Score", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_cost_pressure_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "concall_pricing_power_score", "Concall Pricing Power Score", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_pricing_power_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "management_confidence_change_qoq", "Management Confidence Δ QoQ", "management_tone",
        "now - pq", "score",
        inputs=[
            _i("now", "concall_confidence_score", "CURRENT"),
            _i("pq", "concall_confidence_score", "PQ"),
        ],
        kind="model_score",
    ),
    _m(
        "concall_demand_change_qoq", "Concall Demand Tone Δ QoQ", "management_tone",
        "now - pq", "score",
        inputs=[
            _i("now", "concall_demand_score", "CURRENT"),
            _i("pq", "concall_demand_score", "PQ"),
        ],
        kind="model_score",
    ),
    _m(
        "concall_pricing_power_change_qoq", "Pricing Power Tone Δ QoQ", "management_tone",
        "now - pq", "score",
        inputs=[
            _i("now", "concall_pricing_power_score", "CURRENT"),
            _i("pq", "concall_pricing_power_score", "PQ"),
        ],
        kind="model_score",
    ),
    _m(
        "concall_cost_pressure_change_qoq", "Cost Pressure Δ QoQ", "management_tone",
        "now - pq", "score",
        inputs=[
            _i("now", "concall_cost_pressure_score", "CURRENT"),
            _i("pq", "concall_cost_pressure_score", "PQ"),
        ],
        kind="model_score",
    ),
    _m(
        "concall_capex_intent_score", "Capex Intent Score (Concall)", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_capex_intent_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "concall_margin_tone_score", "Margin Tone Score (Concall)", "management_tone",
        "s", "score",
        inputs=[_i("s", "concall_margin_tone_score", "CURRENT")],
        kind="model_score",
    ),
    _m(
        "capacity_utilization_change", "Capacity Utilization Change", "operations",
        "now - py", "pp",
        inputs=[
            _i("now", "capacity_utilization_pct", "CURRENT"),
            _i("py", "capacity_utilization_pct", "PY"),
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
    _m(
        "order_inflow_growth_yoy", "Order Inflow Growth YoY", "order_book",
        "(now - py) / py * 100", "%", is_pct=True,
        inputs=[
            _i("now", "order_inflow", "CURRENT"),
            _i("py", "order_inflow", "PY"),
        ],
    ),
    _m(
        "order_inflow_growth_qoq", "Order Inflow Growth QoQ", "order_book",
        "(now - pq) / pq * 100", "%", is_pct=True,
        inputs=[
            _i("now", "order_inflow", "CURRENT"),
            _i("pq", "order_inflow", "PQ"),
        ],
    ),
    _m(
        "order_book_growth_qoq", "Order Book Growth QoQ", "order_book",
        "(now - pq) / pq * 100", "%", is_pct=True,
        inputs=[
            _i("now", "closing_order_book", "CURRENT"),
            _i("pq", "closing_order_book", "PQ"),
        ],
    ),
    # ---------------- Phase 4f — Segments (primary segment rollup) ----------------
    _m(
        "primary_segment_revenue_growth_yoy", "Primary Segment Revenue Growth YoY", "segment",
        "(rev - rev_py) / rev_py * 100", "%", is_pct=True,
        inputs=[
            _i("rev", "primary_segment_revenue", "CURRENT"),
            _i("rev_py", "primary_segment_revenue", "PY"),
        ],
        bounds=(-100.0, 500.0),
    ),
    _m(
        "primary_segment_margin", "Primary Segment Margin", "segment",
        "ebit / rev * 100", "%", is_pct=True,
        inputs=[
            _i("ebit", "primary_segment_ebit", "CURRENT"),
            _i("rev", "primary_segment_revenue", "CURRENT"),
        ],
        bounds=(-100.0, 100.0),
    ),
    # ---------------- Phase 4g — Press release / deck ----------------
    _m(
        "ttm_revenue", "TTM Revenue", "growth",
        "ttm", "crore",
        inputs=[_i("ttm", "revenue_from_operations", "TTM")],
    ),
    _m(
        "new_order_to_ttm_revenue", "New Order / TTM Revenue", "order_book",
        "order_val / ttm_rev", "x",
        inputs=[
            _i("order_val", "new_order_value", "CURRENT"),
            _i("ttm_rev", "ttm_revenue", "CURRENT", kind="metric"),
        ],
        deps=["ttm_revenue"],
    ),
    _m(
        "acquisition_to_market_cap", "Acquisition / Market Cap", "strategic",
        "deal / mcap", "x",
        inputs=[
            _i("deal", "acquisition_value", "CURRENT"),
            _i("mcap", "market_cap", "CURRENT"),
        ],
    ),
    _m(
        "capacity_addition_pct", "Capacity Addition %", "operations",
        "new_cap / exist_cap * 100", "%", is_pct=True,
        inputs=[
            _i("new_cap", "new_capacity", "CURRENT"),
            _i("exist_cap", "existing_capacity", "CURRENT"),
        ],
    ),
    _m(
        "dividend_yield", "Dividend Yield", "valuation",
        "dps / price * 100", "%", is_pct=True,
        inputs=[
            _i("dps", "dividend_per_share", "CURRENT"),
            _i("price", "share_price_close", "CURRENT"),
        ],
    ),
    _m(
        "tam_growth_pct", "TAM Growth", "market_opportunity",
        "(tam - tam_py) / tam_py * 100", "%", is_pct=True,
        inputs=[
            _i("tam", "tam_market_size", "CURRENT"),
            _i("tam_py", "tam_market_size_prior", "CURRENT"),
        ],
    ),
    _m(
        "mix_shift_bps", "High-Margin Mix Shift", "business_quality",
        "(now - py) * 100", "bps", is_bps=True,
        inputs=[
            _i("now", "high_margin_revenue_pct", "CURRENT"),
            _i("py", "high_margin_revenue_pct", "PY"),
        ],
    ),
    _m(
        "target_gap_pct", "Management Target Gap", "execution",
        "(target - current) / current * 100", "%", is_pct=True,
        inputs=[
            _i("target", "management_target_value", "CURRENT"),
            _i("current", "revenue_from_operations", "CURRENT"),
        ],
    ),
    _m(
        "top_client_revenue_pct", "Top Client Revenue %", "business_quality",
        "s", "%", is_pct=True,
        inputs=[_i("s", "top_client_revenue_pct", "CURRENT")],
    ),
    _m(
        "region_revenue_pct", "Region Revenue %", "business_quality",
        "s", "%", is_pct=True,
        inputs=[_i("s", "region_revenue_pct", "CURRENT")],
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
        _leaf("other_income_to_pbt", ">", 18),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "elevated_other_income_share", "Elevated Other Income Share",
        "profit_quality", "Other income is a meaningful but not dominant share of PBT.",
        {"all": [
            _leaf("other_income_to_pbt", ">", 15),
            _leaf("other_income_to_pbt", "<", 18),
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "margin_compression", "Margin Compression",
        "margin", "EBITDA margin declined materially YoY.",
        _leaf("ebitda_margin_change_yoy_bps", "<", -75),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "margin_expansion", "Margin Expansion",
        "margin", "EBITDA margin expanded YoY.",
        _leaf("ebitda_margin_change_yoy_bps", ">", 75),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        # Fires when the YoY growth rate itself accelerated by >5 pp vs the
        # prior quarter's YoY rate. Distinct from "revenue_growth_qoq"
        # (sequential %) and "strong_revenue_growth_yoy" (YoY level).
        "revenue_acceleration", "Revenue Growth Acceleration",
        "growth", "YoY revenue growth accelerated by more than 5 pp vs the prior quarter's YoY rate.",
        _leaf("revenue_yoy_growth_acceleration_pp", ">", 5),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        # The old "Revenue Growth Acceleration" rule (YoY > 12) is what
        # analysts actually want labelled "Strong YoY Revenue Growth"; keep
        # it under a separate honest signal so the feed doesn't conflate
        # acceleration with the level.
        "strong_revenue_growth_yoy", "Strong YoY Revenue Growth",
        "growth", "Revenue YoY growth above 12%.",
        _leaf("revenue_yoy_growth", ">", 12),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "modest_revenue_growth", "Modest Revenue Growth (YoY)",
        "growth", "Revenue growing YoY but below acceleration tier.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 0),
            _leaf("revenue_yoy_growth", "<", 12),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.LOW,
    ),
    _s(
        "revenue_deceleration", "Revenue Growth Deceleration (YoY)",
        "growth", "Revenue YoY growth positive but slowing materially.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 0),
            _leaf("revenue_yoy_growth", "<", 5),
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_contraction", "Revenue Contraction (YoY)",
        "growth", "Revenue YoY growth turned negative.",
        _leaf("revenue_yoy_growth", "<", 0),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "finance_cost_pressure", "Finance Cost Pressure",
        "expense", "Finance costs absorb a heavy share of EBITDA.",
        _leaf("finance_cost_burden", ">", 22),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "pat_decline_despite_revenue_growth",
        "PAT Down Despite Revenue Growth (YoY)", "earnings_quality",
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
                _leaf("other_income_to_pbt", ">", 18),
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
            _leaf("revenue_yoy_growth", ">", 8),
            _leaf("ebitda_growth_yoy", ">", 8),
            _leaf("pat_growth_yoy", ">", 8),
            _leaf("other_income_to_pbt", "<", 15),
        ]},
        SignalDirection.POSITIVE, SeverityLevel.HIGH,
    ),
    # ---------------- Phase 1b — Current-period (no YoY required) ----------------
    _s(
        "strong_cash_conversion",
        "Strong Cash Conversion",
        "cash_quality",
        "CFO materially exceeds PAT — earnings backed by cash.",
        _leaf("cfo_to_pat", ">", 1.0),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "weak_cash_conversion",
        "Weak Cash Conversion",
        "cash_quality",
        "CFO fails to cover PAT — earnings quality concern.",
        _leaf("cfo_to_pat", "<", 0.5),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "healthy_pat_margin",
        "Healthy PAT Margin",
        "margin",
        "PAT margin above 12% for the quarter.",
        _leaf("pat_margin", ">", 12),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "thin_pat_margin",
        "Thin PAT Margin",
        "margin",
        "PAT margin below 8% for the quarter.",
        _leaf("pat_margin", "<", 8),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "high_effective_tax_rate",
        "High Effective Tax Rate",
        "profit_quality",
        "Effective tax rate above 28% of PBT.",
        _leaf("effective_tax_rate", ">", 28),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_growth_qoq",
        "Revenue Growth (QoQ)",
        "growth",
        "Revenue grew more than 5% versus the prior quarter.",
        _leaf("revenue_qoq_growth", ">", 5),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "revenue_decline_qoq",
        "Revenue Decline (QoQ)",
        "growth",
        "Revenue contracted versus the prior quarter.",
        _leaf("revenue_qoq_growth", "<", 0),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 2 — Cash flow / Working capital ----------------
    _s(
        "low_quality_growth", "Low-Quality Growth",
        "cash_quality",
        "Revenue growing but cash conversion weak or receivables growing far faster than revenue.",
        {"all": [
            _leaf("revenue_yoy_growth", ">", 8),
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
            _leaf("revenue_yoy_growth", ">", 8),
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
        _leaf("receivables_growth_minus_revenue_growth_bps", ">", 1500),
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
        _leaf("interest_coverage", "<", 2.5),
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
            _leaf("revenue_yoy_growth", ">", 8),
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
        _leaf("management_uncertainty_score", ">", 55),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 4e — Order book ----------------
    _s(
        "order_book_growth", "Order Book Growth (YoY)",
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
    _s(
        "booking_momentum", "Booking Momentum (YoY)",
        "order_book", "Order inflow grew materially YoY.",
        _leaf("order_inflow_growth_yoy", ">", 15),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "order_inflow_slowdown", "Order Inflow Slowdown (YoY)",
        "order_book", "Order inflow contracted YoY.",
        _leaf("order_inflow_growth_yoy", "<", 0),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 1 extensions — growth / WC / earnings ----------------
    _s(
        # The signal previously surfaced as "Operating Profit Momentum"
        # which hides that the rule actually fires on EBITDA YoY growth.
        # Honest label encodes the comparator (YoY).
        "operating_profit_momentum", "EBITDA Growth (YoY)",
        "growth", "EBITDA grew more than 8% versus the same quarter last year.",
        _leaf("ebitda_growth_yoy", ">", 8),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "shareholder_earnings_growth", "Shareholder Earnings Growth (YoY)",
        "growth", "EPS grew materially YoY.",
        _leaf("eps_growth_yoy", ">", 10),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "eps_contraction", "EPS Contraction (YoY)",
        "growth", "EPS declined YoY.",
        _leaf("eps_growth_yoy", "<", 0),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "receivable_days_stress", "Receivable Days Stress",
        "working_capital", "DSO above 90 days (quarter proxy).",
        _leaf("dso", ">", 90),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "inventory_buildup_risk", "Inventory Build-up Risk",
        "working_capital", "Days inventory outstanding above 120.",
        _leaf("dio", ">", 120),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        # Honest label — this is consolidated EBITDA margin, not a composite
        # "strength" score.
        "margin_strength", "EBITDA Margin",
        "margin", "EBITDA margin above 20% for the quarter.",
        _leaf("ebitda_margin", ">", 20),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 4d — Concall tone signals ----------------
    _s(
        "demand_tone_positive", "Demand Tone Positive",
        "management_tone", "Concall language references strong demand visibility.",
        _leaf("concall_demand_score", ">", 45),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "demand_tone_negative", "Demand Tone Negative",
        "management_tone", "Weak demand language on the concall.",
        {"all": [
            _leaf("concall_demand_score", "<", 15),
            _leaf("revenue_yoy_growth", "<", 5),
        ]},
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "margin_tone_pressure", "Margin Tone Pressure",
        "management_tone", "Concall cites cost / margin headwinds.",
        _leaf("concall_cost_pressure_score", ">", 50),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "margin_tone_confidence", "Margin Tone Confidence",
        "management_tone", "Concall language supportive of margins.",
        _leaf("concall_margin_tone_score", ">", 45),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "pricing_power_signal", "Pricing Power",
        "management_tone", "Management cites pricing actions / pass-through.",
        _leaf("concall_pricing_power_score", ">", 40),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        # These signals fire on a concall lexicon score (0–100), not on
        # capex spend itself. The honest name keeps the model nature visible
        # in the feed; the score is rendered as "N / 100" via _format_value.
        "capex_expansion_intent", "Capex Tone — Expansion",
        "management_tone", "Concall capex-intent score above 40 / 100 (lexicon-based).",
        _leaf("concall_capex_intent_score", ">", 40),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "capex_caution", "Capex Tone — Cautious",
        "management_tone", "Concall capex-intent score below 15 / 100 (lexicon-based).",
        _leaf("concall_capex_intent_score", "<", 15),
        SignalDirection.MIXED, SeverityLevel.LOW,
    ),
    _s(
        "utilization_improving", "Utilization Improving",
        "operations", "Capacity utilization rose versus prior year.",
        _leaf("capacity_utilization_change", ">", 5),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 4f — Segment signals ----------------
    _s(
        "segment_growth_driver", "Segment Growth Driver",
        "segment", "Primary segment revenue grew >15% YoY.",
        _leaf("primary_segment_revenue_growth_yoy", ">", 15),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        # Honest label: this rule looks at the EBIT margin of the company's
        # largest segment by revenue, not a weighted score or an
        # "overall margin strength" composite.
        "segment_margin_strength", "Primary Segment EBIT Margin",
        "segment", "EBIT margin of the largest segment by revenue is above 20%.",
        _leaf("primary_segment_margin", ">", 20),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    # ---------------- Phase 4g — Press / deck signals ----------------
    _s(
        "material_order_win", "Material Order Win",
        "order_book", "New order value exceeds 5% of TTM revenue.",
        _leaf("new_order_to_ttm_revenue", ">", 0.05),
        SignalDirection.POSITIVE, SeverityLevel.HIGH,
    ),
    _s(
        "strategic_acquisition", "Strategic Acquisition",
        "strategic", "Acquisition value exceeds 5% of market cap.",
        _leaf("acquisition_to_market_cap", ">", 0.05),
        SignalDirection.MIXED, SeverityLevel.HIGH,
    ),
    _s(
        "capacity_expansion", "Capacity Expansion",
        "operations", "New capacity addition above 10% of existing base.",
        _leaf("capacity_addition_pct", ">", 10),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "dividend_payout_signal", "Dividend Payout Signal",
        "valuation", "Indicative dividend yield above 2%.",
        _leaf("dividend_yield", ">", 2),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "tam_tailwind", "TAM Tailwind",
        "market_opportunity", "Addressable market grew >10% versus prior estimate.",
        _leaf("tam_growth_pct", ">", 10),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "mix_shift_positive", "Mix Shift Positive",
        "business_quality", "High-margin revenue mix expanded >100 bps YoY.",
        _leaf("mix_shift_bps", ">", 100),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "client_concentration_risk", "Client Concentration Risk",
        "business_quality", "Top client exceeds 25% of revenue.",
        _leaf("top_client_revenue_pct", ">", 25),
        SignalDirection.NEGATIVE, SeverityLevel.HIGH,
    ),
    _s(
        "region_concentration", "Region Concentration",
        "business_quality", "Single region exceeds 70% of revenue.",
        _leaf("region_revenue_pct", ">", 70),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "target_execution_upside", "Target Execution Upside",
        "execution", "Management target >5% above current revenue run-rate.",
        _leaf("target_gap_pct", ">", 5),
        SignalDirection.POSITIVE, SeverityLevel.MEDIUM,
    ),
    _s(
        "target_credibility_risk", "Target Credibility Risk",
        "execution", "Management target more than 10% below current revenue.",
        _leaf("target_gap_pct", "<", -10),
        SignalDirection.NEGATIVE, SeverityLevel.MEDIUM,
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
            _leaf("revenue_yoy_growth", ">", 10),
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
            _leaf("ebitda_margin_change_yoy_bps", ">", 75),
            _leaf("pat_growth_yoy", ">", 12),
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
                _leaf("ebitda_margin_change_yoy_bps", "<", -75),
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


# Analyst-facing definitions for the metric registry drawer (Phase 2A).
# Refreshed on every ``seed_catalog`` run so older DBs pick up copy changes.
METRIC_DESCRIPTIONS: dict[str, str] = {
    "revenue_yoy_growth": (
        "Year-on-year change in revenue from operations for the current quarter "
        "column versus the same quarter last year. Uses consolidated P&L lines only."
    ),
    "revenue_qoq_growth": (
        "Quarter-on-quarter change in revenue from operations versus the immediately "
        "prior reported quarter (not YTD or 9M columns)."
    ),
    "revenue_yoy_growth_acceleration_pp": (
        "Change in YoY revenue growth rate versus the prior quarter's YoY rate, "
        "in percentage points. Positive means growth is speeding up sequentially."
    ),
    "ebitda_growth_yoy": (
        "YoY change in reported EBITDA for the current quarter versus the prior-year "
        "quarter column."
    ),
    "pat_growth_yoy": (
        "YoY change in profit after tax for the current quarter versus the prior-year "
        "quarter column."
    ),
    "pat_growth_qoq": (
        "QoQ change in PAT versus the immediately prior quarter."
    ),
    "ebitda_margin": (
        "EBITDA divided by revenue from operations, expressed as a percentage. "
        "Both inputs must be from the same consolidation and period column."
    ),
    "pat_margin": (
        "PAT divided by revenue from operations, expressed as a percentage. "
        "Flags when PAT and revenue are drawn from mismatched segment vs consolidated rows."
    ),
    "ebitda_margin_change_yoy_bps": (
        "YoY change in EBITDA margin in basis points (current margin minus prior-year margin)."
    ),
    "primary_segment_margin": (
        "EBIT of the largest segment by revenue divided by that segment's revenue. "
        "Not a consolidated company margin."
    ),
    "primary_segment_revenue_growth_yoy": (
        "YoY growth of the primary (largest) segment's revenue."
    ),
    "other_income_to_pbt": (
        "Share of profit before tax coming from other income — high values can "
        "inflate headline profitability."
    ),
    "exceptional_to_pat": (
        "Exceptional items as a percentage of PAT — surfaces one-off earnings quality."
    ),
    "effective_tax_rate": (
        "Tax expense divided by PBT. Useful for spotting abnormally low or high tax rates."
    ),
    "finance_cost_burden": (
        "Finance costs as a percentage of EBITDA — leverage pressure indicator."
    ),
    "interest_coverage": (
        "EBITDA divided by finance costs. Higher is better; below 1x is stressed."
    ),
    "cfo_to_pat": (
        "Cash from operations divided by PAT — cash conversion proxy for the quarter."
    ),
    "cash_conversion_ratio": (
        "Same as CFO/PAT — operating cash generation relative to reported earnings."
    ),
    "fcf": (
        "Free cash flow: CFO minus capex (PPE and intangibles) in crore."
    ),
    "concall_confidence_score": (
        "Lexicon-based management confidence score from the earnings call transcript "
        "(0–100, higher = more confident language)."
    ),
    "concall_uncertainty_score": (
        "Lexicon score for hedging / uncertainty language on the concall (0–100)."
    ),
    "concall_capex_intent_score": (
        "Lexicon score for capex expansion vs caution language on the concall (0–100)."
    ),
    "concall_demand_score": (
        "Lexicon score for demand / volume commentary on the concall (0–100)."
    ),
    "concall_cost_pressure_score": (
        "Lexicon score for cost / margin pressure language on the concall (0–100)."
    ),
    "concall_pricing_power_score": (
        "Lexicon score for pricing / realisation commentary on the concall (0–100)."
    ),
    "concall_margin_tone_score": (
        "Lexicon score for margin outlook language on the concall (0–100)."
    ),
    "net_debt_to_ebitda": (
        "Net debt divided by EBITDA — leverage multiple (lower is generally healthier)."
    ),
    "debt_to_equity": (
        "Total debt divided by shareholders' equity."
    ),
    "promoter_holding_change_qoq_bps": (
        "Change in promoter holding versus the prior quarter, in basis points."
    ),
}


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
        bounds = spec.get("bounds")
        v_min = bounds[0] if bounds and bounds[0] is not None else None
        v_max = bounds[1] if bounds and bounds[1] is not None else None
        desc = METRIC_DESCRIPTIONS.get(code)
        existing = db.scalar(select(MetricDefinition).where(MetricDefinition.metric_code == code))
        if existing:
            # Idempotent re-seed: refresh the engine fields so older DBs pick
            # up new inputs/dependencies without manual surgery. Display
            # fields stay sticky to avoid clobbering manual tweaks.
            existing.formula_text = spec["formula"]
            existing.inputs_json = spec["inputs"]
            existing.dependencies_json = spec["deps"]
            existing.metric_category = spec["category"]
            existing.validation_min = v_min
            existing.validation_max = v_max
            existing.metric_kind = spec["kind"]
            if desc:
                existing.description = desc
            out[code] = existing
            continue
        md = MetricDefinition(
            metric_code=code,
            metric_name=spec["name"],
            metric_category=spec["category"],
            metric_kind=spec["kind"],
            formula_text=spec["formula"],
            unit=spec["unit"],
            is_percentage=spec["is_pct"],
            is_bps=spec["is_bps"],
            inputs_json=spec["inputs"],
            dependencies_json=spec["deps"],
            validation_min=v_min,
            validation_max=v_max,
            description=desc,
        )
        db.add(md)
        db.flush()
        out[code] = md
    db.commit()
    return out


def _format_rule_text(rule: dict | None) -> str | None:
    """Stringify a rule_json tree into the inline form shown on cards.

    Mirrors the grammar in ``services/pipeline/signals.py``:
    ``{"all": [...]}`` → ``" and "``, ``{"any": [...]}`` → ``" or "``,
    ``{"not": ...}`` → ``"not (...)"``, leaf → ``"metric op threshold"``.
    Returns ``None`` for empty rules (manual / fact-driven signals).
    """
    if not rule:
        return None
    if "all" in rule:
        parts = [
            _format_rule_text(child) for child in rule.get("all") or []
        ]
        return " and ".join(p for p in parts if p) or None
    if "any" in rule:
        parts = [
            _format_rule_text(child) for child in rule.get("any") or []
        ]
        return " or ".join(p for p in parts if p) or None
    if "not" in rule:
        child = _format_rule_text(rule.get("not"))
        return f"not ({child})" if child else None
    metric = rule.get("metric")
    op = rule.get("operator")
    if not metric or not op:
        return None
    if "metric_ref" in rule and rule["metric_ref"]:
        return f"{metric} {op} {rule['metric_ref']}"
    threshold = rule.get("threshold")
    if threshold is None:
        return None
    if isinstance(threshold, float) and threshold.is_integer():
        threshold = int(threshold)
    return f"{metric} {op} {threshold}"


def upsert_signal_defs(db: Session) -> dict[str, SignalDefinition]:
    out: dict[str, SignalDefinition] = {}
    for spec in SIGNAL_DEFS:
        code = spec["code"]
        rule_text = _format_rule_text(spec["rule"])
        existing = db.scalar(select(SignalDefinition).where(SignalDefinition.signal_code == code))
        if existing:
            existing.signal_name = spec["name"]
            existing.signal_category = spec["category"]
            existing.description = spec["desc"]
            existing.rule_json = spec["rule"]
            existing.rule_text = rule_text
            out[code] = existing
            continue
        sd = SignalDefinition(
            signal_code=code,
            signal_name=spec["name"],
            signal_category=spec["category"],
            description=spec["desc"],
            rule_json=spec["rule"],
            rule_text=rule_text,
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
