"""Shared financial snapshot rows (company hub + event drill-down).

Level margins (``ebitda_margin``) are resolved from ``calculated_metrics`` or
recomputed from ``ebitda`` / ``revenue_from_operations`` facts — never from a
raw extracted margin fact that may be a segment EBIT margin mis-tagged as EBITDA.

YoY deltas on ``%`` margin levels are expressed in **bps** (percentage-point × 100),
not relative percent growth of the margin level.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import CalculatedMetric, MetricDefinition
from app.models.master import FinancialPeriod
from app.schemas.common import FinancialSnapshotRow

SNAPSHOT_METRICS: tuple[tuple[str, str, str], ...] = (
    ("revenue_from_operations", "Revenue", "Cr"),
    ("ebitda", "EBITDA", "Cr"),
    ("ebitda_margin", "EBITDA Margin", "%"),
    ("pat", "PAT", "Cr"),
    ("eps_basic", "EPS", "Rs"),
)

# Consolidated margin levels: YoY delta in bps; levels from calculated / recompute.
MARGIN_LEVEL_CODES: frozenset[str] = frozenset({"ebitda_margin", "pat_margin"})

_DERIVED_MARGIN_INPUTS: dict[str, tuple[str, str]] = {
    "ebitda_margin": ("ebitda", "revenue_from_operations"),
    "pat_margin": ("pat", "revenue_from_operations"),
}


def prior_year_period_id(db: Session, period: FinancialPeriod) -> int | None:
    if period.quarter is None:
        return None
    return db.scalar(
        select(FinancialPeriod.period_id).where(
            FinancialPeriod.fy_year == period.fy_year - 1,
            FinancialPeriod.quarter == period.quarter,
            FinancialPeriod.period_type == period.period_type,
        )
    )


def snapshot_yoy_delta(
    code: str,
    unit: str,
    current: float | None,
    previous: float | None,
) -> tuple[float | None, float | None]:
    """Return ``(yoy_change_pct, yoy_change_bps)`` for a snapshot row."""
    if current is None or previous is None:
        return None, None
    if code in MARGIN_LEVEL_CODES or unit == "%":
        return None, (current - previous) * 100.0
    if previous == 0:
        return None, None
    return (current - previous) / abs(previous) * 100.0, None


def margin_from_facts(facts: dict[str, float], code: str) -> float | None:
    pair = _DERIVED_MARGIN_INPUTS.get(code)
    if not pair:
        return None
    numerator_code, denominator_code = pair
    num = facts.get(numerator_code)
    den = facts.get(denominator_code)
    if num is None or den is None or den <= 0:
        return None
    return (num / den) * 100.0


def calculated_metric_value(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    metric_code: str,
) -> float | None:
    row = db.scalar(
        select(CalculatedMetric.metric_value)
        .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
        .where(
            CalculatedMetric.company_id == company_id,
            CalculatedMetric.period_id == period_id,
            MetricDefinition.metric_code == metric_code,
            CalculatedMetric.is_quarantined.is_(False),
            CalculatedMetric.metric_value.is_not(None),
        )
        .order_by(CalculatedMetric.metric_id.desc())
        .limit(1)
    )
    return float(row) if row is not None else None


def facts_for_period(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    codes: frozenset[str] | set[str],
) -> dict[str, float]:
    if not codes:
        return {}
    rows = db.execute(
        select(FinancialLineItemDefinition.normalized_code, FinancialStatementFact.value)
        .join(
            FinancialLineItemDefinition,
            FinancialLineItemDefinition.line_item_def_id
            == FinancialStatementFact.line_item_def_id,
        )
        .where(
            FinancialStatementFact.company_id == company_id,
            FinancialStatementFact.period_id == period_id,
            FinancialStatementFact.period_value_type == "CURRENT",
            FinancialLineItemDefinition.normalized_code.in_(codes),
        )
    ).all()
    out: dict[str, float] = {}
    for code, value in rows:
        if value is not None:
            out[code] = float(value)
    return out


def resolve_snapshot_level(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    code: str,
    facts: dict[str, float],
) -> float | None:
    if code in MARGIN_LEVEL_CODES:
        calculated = calculated_metric_value(
            db, company_id=company_id, period_id=period_id, metric_code=code
        )
        if calculated is not None:
            return calculated
        return margin_from_facts(facts, code)
    return facts.get(code)


def build_snapshot_row(
    db: Session,
    *,
    company_id: int,
    period: FinancialPeriod,
    prev_period_id: int | None,
    code: str,
    display: str,
    unit: str,
) -> FinancialSnapshotRow | None:
    codes_needed: set[str] = {code}
    if code in MARGIN_LEVEL_CODES:
        pair = _DERIVED_MARGIN_INPUTS[code]
        codes_needed.update(pair)

    cur_facts = facts_for_period(
        db, company_id=company_id, period_id=period.period_id, codes=codes_needed
    )
    cur_val = resolve_snapshot_level(
        db, company_id=company_id, period_id=period.period_id, code=code, facts=cur_facts
    )
    if cur_val is None:
        return None

    prev_val: float | None = None
    if prev_period_id is not None:
        prev_facts = facts_for_period(
            db, company_id=company_id, period_id=prev_period_id, codes=codes_needed
        )
        prev_val = resolve_snapshot_level(
            db,
            company_id=company_id,
            period_id=prev_period_id,
            code=code,
            facts=prev_facts,
        )

    yoy_pct, yoy_bps = snapshot_yoy_delta(code, unit, cur_val, prev_val)
    return FinancialSnapshotRow(
        metric=display,
        code=code,
        current_value=cur_val,
        previous_value=prev_val,
        yoy_change_pct=yoy_pct,
        yoy_change_bps=yoy_bps,
        unit=unit,
    )


def build_financial_snapshot(
    db: Session,
    *,
    company_id: int,
    period: FinancialPeriod | None,
) -> list[FinancialSnapshotRow]:
    if period is None:
        return []
    prev_id = prior_year_period_id(db, period)
    snapshot: list[FinancialSnapshotRow] = []
    for code, display, unit in SNAPSHOT_METRICS:
        row = build_snapshot_row(
            db,
            company_id=company_id,
            period=period,
            prev_period_id=prev_id,
            code=code,
            display=display,
            unit=unit,
        )
        if row is not None:
            snapshot.append(row)
    return snapshot


def trend_value_for_code(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    code: str,
    fact_value: float | None,
) -> float | None:
    """Use calculated/recomputed margin for sparklines when ``code`` is a margin level."""
    if code not in MARGIN_LEVEL_CODES:
        return fact_value
    facts = facts_for_period(
        db,
        company_id=company_id,
        period_id=period_id,
        codes=set(_DERIVED_MARGIN_INPUTS.get(code, ())),
    )
    resolved = resolve_snapshot_level(
        db, company_id=company_id, period_id=period_id, code=code, facts=facts
    )
    return resolved if resolved is not None else fact_value
