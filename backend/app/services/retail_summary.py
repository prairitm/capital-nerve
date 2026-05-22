"""Retail summary service.

Boils the latest published intelligence cards for a company into a short, plain
language summary + risk level + momentum, suitable for a consumer brokerage
stock page. No new tables — the inputs are existing cards + signals + facts.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import EventType, SeverityLevel, SignalDirection
from app.models.events import CompanyEvent
from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import CalculatedMetric, IntelligenceCard, MetricDefinition
from app.models.master import Company, FinancialPeriod
from app.routers._helpers import company_brief, period_brief
from app.schemas.v1.retail import RetailSummary, RetailSummaryPoint

_TONE_BY_DIRECTION: dict[SignalDirection, str] = {
    SignalDirection.POSITIVE: "positive",
    SignalDirection.NEGATIVE: "negative",
    SignalDirection.MIXED: "mixed",
    SignalDirection.NEUTRAL: "neutral",
}


def _latest_period(db: Session, company_id: int) -> FinancialPeriod | None:
    event = db.scalars(
        select(CompanyEvent)
        .where(CompanyEvent.company_id == company_id)
        .where(CompanyEvent.event_type == EventType.QUARTERLY_RESULT)
        .order_by(CompanyEvent.event_date.desc())
        .limit(1)
    ).first()
    if event and event.period_id:
        return db.get(FinancialPeriod, event.period_id)
    return None


def _top_cards(db: Session, company_id: int) -> list[IntelligenceCard]:
    return db.scalars(
        select(IntelligenceCard)
        .where(IntelligenceCard.company_id == company_id)
        .where(IntelligenceCard.is_published.is_(True))
        .where(IntelligenceCard.card_type != "watch_next")
        .order_by(IntelligenceCard.card_priority.desc(), IntelligenceCard.created_at.desc())
        .limit(6)
    ).all()


def _headline_metrics(
    db: Session, company_id: int, period_id: int | None
) -> list[dict[str, str | float | None]]:
    if not period_id:
        return []

    line_codes = ["revenue_from_operations", "ebitda", "pat"]
    items = db.scalars(
        select(FinancialLineItemDefinition).where(
            FinancialLineItemDefinition.normalized_code.in_(line_codes)
        )
    ).all()
    items_by_code = {li.normalized_code: li for li in items}

    out: list[dict[str, str | float | None]] = []
    for code, label in [
        ("revenue_from_operations", "Revenue"),
        ("ebitda", "EBITDA"),
        ("pat", "PAT"),
    ]:
        li = items_by_code.get(code)
        if not li:
            continue
        fact = db.scalar(
            select(FinancialStatementFact).where(
                FinancialStatementFact.company_id == company_id,
                FinancialStatementFact.line_item_def_id == li.line_item_def_id,
                FinancialStatementFact.period_id == period_id,
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        )
        if not fact:
            continue
        out.append(
            {
                "name": label,
                "value": float(fact.value) if fact.value is not None else None,
                "unit": fact.unit or "Cr",
            }
        )

    # Add EBITDA margin if available as a calculated metric.
    margin_def = db.scalar(
        select(MetricDefinition).where(MetricDefinition.metric_code == "ebitda_margin")
    )
    if margin_def:
        cm = db.scalar(
            select(CalculatedMetric).where(
                CalculatedMetric.company_id == company_id,
                CalculatedMetric.period_id == period_id,
                CalculatedMetric.metric_def_id == margin_def.metric_def_id,
            )
        )
        if cm and cm.metric_value is not None:
            out.append({"name": "EBITDA Margin", "value": float(cm.metric_value), "unit": "%"})

    return out


def _momentum_for(cards: list[IntelligenceCard]) -> SignalDirection:
    counter: Counter[SignalDirection] = Counter()
    for c in cards:
        if c.signal_direction:
            counter[c.signal_direction] += 1
    if not counter:
        return SignalDirection.NEUTRAL
    return counter.most_common(1)[0][0]


def _risk_level_for(cards: list[IntelligenceCard]) -> SeverityLevel:
    severities = [c.severity for c in cards if c.severity is not None]
    if not severities:
        return SeverityLevel.LOW
    order = [SeverityLevel.LOW, SeverityLevel.MEDIUM, SeverityLevel.HIGH, SeverityLevel.CRITICAL]
    return max(severities, key=lambda s: order.index(s) if s in order else 0)


def _top_points(cards: list[IntelligenceCard]) -> list[RetailSummaryPoint]:
    out: list[RetailSummaryPoint] = []
    seen_types: set[str] = set()
    for card in cards:
        if len(out) >= 3:
            break
        if card.card_type in seen_types:
            continue
        seen_types.add(card.card_type)
        tone = _TONE_BY_DIRECTION.get(card.signal_direction or SignalDirection.NEUTRAL, "neutral")
        out.append(
            RetailSummaryPoint(
                label=card.headline,
                tone=tone,  # type: ignore[arg-type]
                detail=card.one_line_summary,
            )
        )
    return out


def build_retail_summary(db: Session, company: Company) -> RetailSummary:
    period = _latest_period(db, company.company_id)
    cards = _top_cards(db, company.company_id)
    momentum = _momentum_for(cards)
    risk = _risk_level_for(cards)
    simple = (
        cards[0].one_line_summary
        if cards
        else f"No published intelligence for {company.short_name or company.company_name}."
    )

    return RetailSummary(
        company=company_brief(company),
        period=period_brief(period),
        simple_summary=simple,
        risk_level=risk.value,  # type: ignore[arg-type]
        momentum=_TONE_BY_DIRECTION.get(momentum, "neutral"),  # type: ignore[arg-type]
        top_3_points=_top_points(cards),
        headline_metrics=_headline_metrics(db, company.company_id, period.period_id if period else None),
    )
