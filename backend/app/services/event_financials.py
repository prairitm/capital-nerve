"""Financial snapshot rows for a single reporting period (event drill-down)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.master import FinancialPeriod
from app.schemas.common import FinancialSnapshotRow

_SNAPSHOT_METRICS: list[tuple[str, str, str]] = [
    ("revenue_from_operations", "Revenue", "Cr"),
    ("ebitda", "EBITDA", "Cr"),
    ("ebitda_margin", "EBITDA Margin", "%"),
    ("pat", "PAT", "Cr"),
    ("eps_basic", "EPS", "Rs"),
]


def build_financial_snapshot_for_period(
    db: Session,
    company_id: int,
    period: FinancialPeriod | None,
) -> list[FinancialSnapshotRow]:
    """Current period vs same quarter prior year (mirrors company hub logic)."""
    if not period:
        return []

    line_items = db.scalars(
        select(FinancialLineItemDefinition).where(
            FinancialLineItemDefinition.normalized_code.in_([code for code, _, _ in _SNAPSHOT_METRICS])
        )
    ).all()
    items_by_code = {li.normalized_code: li for li in line_items}

    periods = db.scalars(
        select(FinancialPeriod).order_by(FinancialPeriod.period_end_date.asc())
    ).all()

    prev_period_id: int | None = None
    for p in periods:
        if (
            p.fy_year == period.fy_year - 1
            and p.quarter == period.quarter
            and p.period_type == period.period_type
        ):
            prev_period_id = p.period_id
            break

    snapshot: list[FinancialSnapshotRow] = []
    for code, display, unit in _SNAPSHOT_METRICS:
        li = items_by_code.get(code)
        if not li:
            continue
        facts = db.scalars(
            select(FinancialStatementFact)
            .where(
                FinancialStatementFact.company_id == company_id,
                FinancialStatementFact.line_item_def_id == li.line_item_def_id,
                FinancialStatementFact.period_value_type == "CURRENT",
                FinancialStatementFact.period_id.in_(
                    [period.period_id] + ([prev_period_id] if prev_period_id else [])
                ),
            )
        ).all()
        fact_by_period = {f.period_id: float(f.value) for f in facts}
        cur_val = fact_by_period.get(period.period_id)
        if cur_val is None:
            continue
        prev_val = fact_by_period.get(prev_period_id) if prev_period_id else None
        yoy = ((cur_val - prev_val) / prev_val * 100) if prev_val else None
        snapshot.append(
            FinancialSnapshotRow(
                metric=display,
                code=code,
                current_value=cur_val,
                previous_value=prev_val,
                yoy_change_pct=yoy,
                unit=unit,
            )
        )
    return snapshot
