from sqlalchemy import not_, select
from sqlalchemy.orm import Session

from app.models.events import CompanyEvent, SourceDocument
from app.models.intelligence import CalculatedMetric, GeneratedSignal, IntelligenceCard
from app.models.master import Company, FinancialPeriod, Sector
from app.schemas.common import CardBrief, CompanyBrief, PeriodBrief


def suspect_signal_exists():
    """Correlated EXISTS clause: an `IntelligenceCard`'s signal has a suspect primary metric.

    A card is suspect when the `GeneratedSignal` it was built from points at a
    `CalculatedMetric` that is `is_quarantined=True` or `anomaly_flag=True`.
    Cards with `signal_id IS NULL` are unaffected — `EXISTS` returns false when
    nothing matches.

    Used by every read path that lists "published cards" so the public surface
    stays consistent with the Review Queue. The corresponding write-path gate
    lives in `services/pipeline/runner._summarize_anomalies`.
    """
    return (
        select(GeneratedSignal.signal_id)
        .join(
            CalculatedMetric,
            CalculatedMetric.metric_id == GeneratedSignal.primary_metric_id,
        )
        .where(GeneratedSignal.signal_id == IntelligenceCard.signal_id)
        .where(
            (CalculatedMetric.is_quarantined.is_(True))
            | (CalculatedMetric.anomaly_flag.is_(True))
        )
        .exists()
    )


def exclude_suspect_cards(stmt):
    """Apply `NOT suspect_signal_exists()` to a select that includes IntelligenceCard."""
    return stmt.where(not_(suspect_signal_exists()))


def company_brief(company: Company, sector: Sector | None = None) -> CompanyBrief:
    sector_name = (sector.sector_name if sector else None) if sector else (
        company.sector.sector_name if company.sector else None
    )
    return CompanyBrief(
        company_id=company.company_id,
        company_name=company.company_name,
        short_name=company.short_name,
        nse_symbol=company.nse_symbol,
        bse_code=company.bse_code,
        sector_name=sector_name,
        industry=company.industry,
        market_cap_cr=float(company.market_cap_cr) if company.market_cap_cr is not None else None,
        last_price=float(company.last_price) if company.last_price is not None else None,
    )


def period_brief(period: FinancialPeriod | None) -> PeriodBrief | None:
    if not period:
        return None
    return PeriodBrief(
        period_id=period.period_id,
        display_label=period.display_label,
        fy_label=period.fy_label,
        quarter=period.quarter,
        period_end_date=period.period_end_date,
    )


def build_source_label(
    period: FinancialPeriod | None,
    event: CompanyEvent | None,
    document: SourceDocument | None,
) -> str | None:
    if document:
        title = (document.document_title or "").strip()
        if title:
            return title
        return document.document_type.value.replace("_", " ").title()
    if event:
        if event.event_title:
            return event.event_title
        return event.event_type.value.replace("_", " ").title()
    if period:
        return period.display_label
    return None


def card_brief(
    card: IntelligenceCard,
    company: Company,
    period: FinancialPeriod | None,
    event: CompanyEvent | None,
    document: SourceDocument | None = None,
) -> CardBrief:
    return CardBrief(
        card_id=card.card_id,
        signal_id=card.signal_id,
        card_type=card.card_type,
        headline=card.headline,
        one_line_summary=card.one_line_summary,
        signal_direction=card.signal_direction,
        severity=card.severity,
        confidence_score=float(card.confidence_score) if card.confidence_score is not None else None,
        confidence_level=card.confidence_level,
        card_priority=float(card.card_priority) if card.card_priority is not None else 0,
        company=company_brief(company),
        period=period_brief(period),
        event_id=event.event_id if event else None,
        event_type=event.event_type if event else None,
        event_title=event.event_title if event else None,
        event_date=event.event_date if event else None,
        metrics_json=card.metrics_json or [],
        watch_next=card.watch_next,
        source_label=build_source_label(period, event, document),
        document_id=card.document_id,
        created_at=card.created_at,
    )


def find_company(db: Session, symbol: str) -> Company | None:
    symbol_upper = symbol.upper()
    from sqlalchemy import or_, select

    stmt = select(Company).where(
        or_(Company.nse_symbol == symbol_upper, Company.bse_code == symbol_upper)
    )
    return db.scalar(stmt)
