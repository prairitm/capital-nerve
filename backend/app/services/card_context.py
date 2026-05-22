"""Financial and event context for card detail drawer."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import EventType
from app.models.events import CompanyEvent
from app.models.facts import AnalystQuestion, FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import CalculatedMetric, IntelligenceCard, MetricDefinition
from app.models.master import FinancialPeriod
from app.schemas.common import (
    CardMetricComparison,
    ConcernHeatmapRow,
    FinancialTrend,
    FinancialTrendPoint,
)

CONCALL_CARD_TYPES = frozenset({"management_tone", "guidance_tracker", "analyst_concern"})
TREND_LINE_CODES = [
    ("revenue_from_operations", "Revenue", "Cr"),
    ("ebitda_margin", "EBITDA Margin", "%"),
    ("pat", "PAT", "Cr"),
]

# Prefer these calculated metrics in the drawer (order matters)
HIGHLIGHT_METRIC_CODES = [
    "revenue_yoy_growth",
    "pat_growth_yoy",
    "ebitda_margin",
    "ebitda_margin_change_yoy_bps",
    "pat_margin",
    "other_income_to_pbt",
    "finance_cost_burden",
    "effective_tax_rate",
]


def _prior_year_period_id(db: Session, period_id: int) -> int | None:
    current = db.get(FinancialPeriod, period_id)
    if not current or current.quarter is None:
        return None
    return db.scalar(
        select(FinancialPeriod.period_id).where(
            FinancialPeriod.fy_year == current.fy_year - 1,
            FinancialPeriod.quarter == current.quarter,
            FinancialPeriod.period_type == current.period_type,
        )
    )


def _prior_metric_value(db: Session, cm: CalculatedMetric) -> float | None:
    prior_period_id = cm.comparison_period_id
    if prior_period_id is None and cm.period_id is not None:
        prior_period_id = _prior_year_period_id(db, cm.period_id)

    if prior_period_id is not None:
        prior = db.scalar(
            select(CalculatedMetric.metric_value)
            .where(
                CalculatedMetric.company_id == cm.company_id,
                CalculatedMetric.period_id == prior_period_id,
                CalculatedMetric.metric_def_id == cm.metric_def_id,
            )
            .order_by(CalculatedMetric.metric_id.desc())
            .limit(1)
        )
        if prior is not None:
            return float(prior)

    inputs = cm.input_values or {}
    for key in ("margin_lyq", "margin_pq", "revenue_lyq"):
        if key in inputs:
            return float(inputs[key])
    return None


def load_metric_comparisons(
    db: Session,
    company_id: int,
    period_id: int | None,
    event_id: int | None,
    card_type: str,
) -> list[CardMetricComparison]:
    if not period_id:
        return []

    stmt = (
        select(CalculatedMetric, MetricDefinition)
        .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
        .where(
            CalculatedMetric.company_id == company_id,
            CalculatedMetric.period_id == period_id,
        )
    )
    if event_id:
        stmt = stmt.where(
            (CalculatedMetric.event_id == event_id) | (CalculatedMetric.event_id.is_(None))
        )

    rows = db.execute(stmt).all()
    by_code: dict[str, tuple[CalculatedMetric, MetricDefinition]] = {
        md.metric_code: (cm, md) for cm, md in rows
    }

    ordered_codes = list(HIGHLIGHT_METRIC_CODES)
    for code in by_code:
        if code not in ordered_codes:
            ordered_codes.append(code)

    out: list[CardMetricComparison] = []
    for code in ordered_codes:
        if code not in by_code:
            continue
        cm, md = by_code[code]
        current = float(cm.metric_value) if cm.metric_value is not None else None
        previous = _prior_metric_value(db, cm)
        change_pct = float(cm.change_percent) if cm.change_percent is not None else None
        change_bps = float(cm.change_bps) if cm.change_bps is not None else None

        if md.is_bps and current is not None:
            change_bps = current
        elif md.metric_code == "ebitda_margin_change_yoy_bps":
            change_bps = current
        elif change_pct is None and current is not None and previous is not None:
            if md.is_percentage or md.unit == "%":
                if md.metric_code.endswith("_growth") or "yoy" in md.metric_code:
                    change_pct = current
                else:
                    change_bps = (current - previous) * 100 if md.unit == "%" else None
                    if change_bps is None:
                        change_pct = current - previous

        out.append(
            CardMetricComparison(
                metric_code=md.metric_code,
                metric_name=md.metric_name,
                current_value=current,
                previous_value=previous,
                change_percent=change_pct,
                change_bps=change_bps,
                unit=md.unit or "",
                comparison_type=cm.comparison_type,
            )
        )
    return out[:6]


def load_trend_sparklines(
    db: Session,
    company_id: int,
    period_id: int | None,
    limit_points: int = 8,
) -> list[FinancialTrend]:
    if not period_id:
        return []

    anchor = db.get(FinancialPeriod, period_id)
    if not anchor:
        return []

    periods = db.scalars(
        select(FinancialPeriod)
        .where(FinancialPeriod.period_end_date <= anchor.period_end_date)
        .order_by(FinancialPeriod.period_end_date.desc())
        .limit(limit_points)
    ).all()
    periods = list(reversed(periods))
    if not periods:
        return []

    period_ids = {p.period_id for p in periods}
    line_items = db.scalars(
        select(FinancialLineItemDefinition).where(
            FinancialLineItemDefinition.normalized_code.in_([c[0] for c in TREND_LINE_CODES])
        )
    ).all()
    items_by_code = {li.normalized_code: li for li in line_items}

    trends: list[FinancialTrend] = []
    for code, display, unit in TREND_LINE_CODES:
        li = items_by_code.get(code)
        if not li:
            continue
        facts = db.scalars(
            select(FinancialStatementFact).where(
                FinancialStatementFact.company_id == company_id,
                FinancialStatementFact.line_item_def_id == li.line_item_def_id,
                FinancialStatementFact.period_id.in_(period_ids),
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        ).all()
        fact_by_period = {f.period_id: float(f.value) for f in facts}
        points = [
            FinancialTrendPoint(
                period_label=p.display_label,
                period_end_date=p.period_end_date,
                value=fact_by_period.get(p.period_id),
            )
            for p in periods
            if p.period_id in fact_by_period
        ]
        if len(points) >= 2:
            trends.append(
                FinancialTrend(metric_code=code, metric_name=display, unit=unit, points=points)
            )
    return trends


def should_show_concall(card: IntelligenceCard, event: CompanyEvent | None) -> bool:
    if card.card_type in CONCALL_CARD_TYPES:
        return True
    if event and event.event_type == EventType.CONCALL_TRANSCRIPT:
        return True
    return False


def load_concall_heatmap(db: Session, event_id: int | None) -> list[ConcernHeatmapRow]:
    if not event_id:
        return []
    questions = db.scalars(select(AnalystQuestion).where(AnalystQuestion.event_id == event_id)).all()
    if not questions:
        return []
    heatmap: dict[str, int] = {}
    for q in questions:
        topic = q.topic or "Other"
        heatmap[topic] = heatmap.get(topic, 0) + 1
    total = sum(heatmap.values()) or 1
    return [
        ConcernHeatmapRow(topic=t, count=c, percent=round(c / total * 100, 1))
        for t, c in sorted(heatmap.items(), key=lambda kv: kv[1], reverse=True)
    ]
