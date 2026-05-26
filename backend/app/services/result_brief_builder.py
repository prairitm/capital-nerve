"""Result brief service — analyst-shaped quarterly brief.

Combines:
  - The selected quarterly event's summary / verdict
  - Cards split into positives and negatives by `signal_direction`
  - The standard YoY metric comparisons
  - Peer median for the same period (companies in the same sector)
  - Evidence rows from the underlying cards
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import EventType, SignalDirection
from app.models.events import CompanyEvent
from app.models.intelligence import CalculatedMetric, IntelligenceCard, MetricDefinition
from app.models.master import Company, FinancialPeriod
from app.routers._helpers import company_brief, exclude_suspect_cards, period_brief
from app.schemas.common import EvidenceItem
from app.schemas.v1.result_brief import (
    ResultBrief,
    ResultBriefPoint,
    ResultPeerComparison,
)
from app.services.card_context import HIGHLIGHT_METRIC_CODES, load_metric_comparisons


def _resolve_event(
    db: Session, company_id: int, period_id: int | None
) -> CompanyEvent | None:
    if period_id:
        stmt = (
            select(CompanyEvent)
            .where(CompanyEvent.company_id == company_id)
            .where(CompanyEvent.event_type == EventType.QUARTERLY_RESULT)
            .where(CompanyEvent.period_id == period_id)
            .order_by(CompanyEvent.event_date.desc())
            .limit(1)
        )
    else:
        stmt = (
            select(CompanyEvent)
            .where(CompanyEvent.company_id == company_id)
            .where(CompanyEvent.event_type == EventType.QUARTERLY_RESULT)
            .order_by(CompanyEvent.event_date.desc())
            .limit(1)
        )
    return db.scalars(stmt).first()


def _resolve_period(db: Session, period_label: str | None) -> FinancialPeriod | None:
    if not period_label:
        return None
    cleaned = period_label.strip()
    if not cleaned:
        return None
    # Try display label first (Q4FY26), then fy_label fallback.
    period = db.scalar(
        select(FinancialPeriod).where(FinancialPeriod.display_label.ilike(cleaned))
    )
    if period:
        return period
    return db.scalar(
        select(FinancialPeriod).where(FinancialPeriod.fy_label.ilike(cleaned))
    )


def _point_from_card(card: IntelligenceCard) -> ResultBriefPoint:
    metric_code: str | None = None
    value = None
    unit = None
    if card.metrics_json:
        first = card.metrics_json[0]
        if isinstance(first, dict):
            value = first.get("value")
            unit = first.get("unit")
            metric_code = first.get("metric_code") or first.get("name")
    return ResultBriefPoint(
        title=card.headline,
        detail=card.one_line_summary,
        metric_code=metric_code,
        value=value,
        unit=unit,
    )


def _peer_comparisons(
    db: Session, company: Company, period_id: int | None
) -> list[ResultPeerComparison]:
    if not period_id or company.sector_id is None:
        return []

    peers = db.scalars(
        select(Company)
        .where(Company.sector_id == company.sector_id)
        .where(Company.company_id != company.company_id)
    ).all()
    if not peers:
        return []

    peer_ids = [p.company_id for p in peers]
    metric_defs = db.scalars(
        select(MetricDefinition).where(MetricDefinition.metric_code.in_(HIGHLIGHT_METRIC_CODES))
    ).all()
    defs_by_code = {md.metric_code: md for md in metric_defs}

    out: list[ResultPeerComparison] = []
    for code in HIGHLIGHT_METRIC_CODES:
        md = defs_by_code.get(code)
        if not md:
            continue
        peer_metrics = db.scalars(
            select(CalculatedMetric).where(
                CalculatedMetric.company_id.in_(peer_ids),
                CalculatedMetric.metric_def_id == md.metric_def_id,
                CalculatedMetric.period_id == period_id,
            )
        ).all()
        peer_values = [float(m.metric_value) for m in peer_metrics if m.metric_value is not None]

        company_metric = db.scalar(
            select(CalculatedMetric).where(
                CalculatedMetric.company_id == company.company_id,
                CalculatedMetric.metric_def_id == md.metric_def_id,
                CalculatedMetric.period_id == period_id,
            )
        )
        company_value = (
            float(company_metric.metric_value)
            if company_metric and company_metric.metric_value is not None
            else None
        )
        median = _median(peer_values)

        if company_value is None and not peer_values:
            continue

        rank: int | None = None
        if company_value is not None and peer_values:
            all_values = sorted([*peer_values, company_value], reverse=True)
            rank = all_values.index(company_value) + 1

        out.append(
            ResultPeerComparison(
                metric_code=code,
                metric_name=md.metric_name,
                company_value=company_value,
                peer_median=median,
                rank=rank,
                sample_size=len(peer_values),
                unit=md.unit or "",
            )
        )
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def _evidence_for_cards(
    db: Session, cards: list[IntelligenceCard], limit: int = 12
) -> list[EvidenceItem]:
    if not cards:
        return []
    from app.models.intelligence import CardEvidence

    card_ids = [c.card_id for c in cards]
    rows = db.scalars(
        select(CardEvidence)
        .where(CardEvidence.card_id.in_(card_ids))
        .order_by(CardEvidence.card_evidence_id)
        .limit(limit)
    ).all()
    return [
        EvidenceItem(
            card_evidence_id=e.card_evidence_id,
            document_id=e.document_id,
            evidence_type=e.evidence_type,
            evidence_label=e.evidence_label,
            evidence_value=e.evidence_value,
            source_text=e.source_text,
            page_number=e.page_number,
            calculation_text=e.calculation_text,
            confidence_score=float(e.confidence_score) if e.confidence_score is not None else None,
        )
        for e in rows
    ]


def build_result_brief(
    db: Session, company: Company, period_label: str | None
) -> ResultBrief | None:
    period = _resolve_period(db, period_label)
    event = _resolve_event(db, company.company_id, period.period_id if period else None)
    if not event:
        return None
    if not period and event.period_id:
        period = db.get(FinancialPeriod, event.period_id)

    cards = db.scalars(
        exclude_suspect_cards(
            select(IntelligenceCard)
            .where(IntelligenceCard.event_id == event.event_id)
            .where(IntelligenceCard.is_published.is_(True))
            .where(IntelligenceCard.card_type != "watch_next")
        )
        .order_by(IntelligenceCard.card_priority.desc())
    ).all()

    key_positives = [_point_from_card(c) for c in cards if c.signal_direction == SignalDirection.POSITIVE][:5]
    key_negatives = [_point_from_card(c) for c in cards if c.signal_direction == SignalDirection.NEGATIVE][:5]

    metric_comparisons = load_metric_comparisons(
        db,
        company.company_id,
        period.period_id if period else None,
        event.event_id,
        "result_verdict",
    )

    model_update_fields: dict[str, float | str | None] = {}
    for row in metric_comparisons:
        if row.current_value is not None:
            model_update_fields[row.metric_code] = row.current_value
    if event.overall_signal:
        model_update_fields["overall_signal"] = event.overall_signal.value

    headline = event.event_title or f"{company.short_name or company.company_name} result"
    if event.summary_text:
        verdict = event.summary_text
    else:
        verdict = (
            f"{company.short_name or company.company_name}: "
            f"{event.overall_signal.value.lower() if event.overall_signal else 'mixed'} verdict."
        )

    return ResultBrief(
        company=company_brief(company),
        period=period_brief(period),
        event_id=event.event_id,
        headline=headline,
        overall_verdict=verdict,
        key_positives=key_positives,
        key_negatives=key_negatives,
        model_update_fields=model_update_fields,
        peer_comparison=_peer_comparisons(db, company, period.period_id if period else None),
        metric_comparisons=metric_comparisons,
        source_evidence=_evidence_for_cards(db, cards),
    )
