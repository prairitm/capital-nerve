"""Portfolio monitoring service.

Given a list of NSE/BSE symbols + optional severity / importance / direction
filters, returns ranked `PortfolioAlert` rows that point at the underlying
intelligence objects per company.
"""

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.enums import SeverityLevel, SignalDirection
from app.models.events import CompanyEvent
from app.models.intelligence import IntelligenceCard
from app.models.master import Company, FinancialPeriod
from app.routers._helpers import exclude_suspect_cards
from app.schemas.v1.intelligence_object import IntelligenceObjectBrief
from app.schemas.v1.portfolio import (
    PortfolioAlert,
    PortfolioMonitorRequest,
    PortfolioMonitorResponse,
)
from app.services.intelligence_object_builder import build_intelligence_object_brief


def _resolve_companies(db: Session, symbols: list[str]) -> tuple[list[Company], list[str]]:
    cleaned = [s.strip().upper() for s in symbols if s and s.strip()]
    if not cleaned:
        return [], []

    rows = db.scalars(
        select(Company).where(
            or_(Company.nse_symbol.in_(cleaned), Company.bse_code.in_(cleaned))
        )
    ).all()

    found_keys: set[str] = set()
    for c in rows:
        if c.nse_symbol:
            found_keys.add(c.nse_symbol.upper())
        if c.bse_code:
            found_keys.add(c.bse_code.upper())

    unresolved = [s for s in cleaned if s not in found_keys]
    return list(rows), unresolved


def _reason_from_objects(objects: list[IntelligenceObjectBrief]) -> str | None:
    if not objects:
        return None
    top = objects[0]
    severity = top.severity.value if top.severity else None
    direction = top.status.value if top.status else None
    pieces: list[str] = []
    if direction:
        pieces.append(direction.lower())
    if severity:
        pieces.append(f"severity {severity.lower()}")
    descriptor = ", ".join(pieces) if pieces else "intelligence object"
    return f"{top.title} ({descriptor})"


def monitor_portfolio(
    db: Session, payload: PortfolioMonitorRequest
) -> PortfolioMonitorResponse:
    companies, unresolved = _resolve_companies(db, payload.symbols)
    if not companies:
        return PortfolioMonitorResponse(
            requested_symbols=payload.symbols,
            resolved_companies=0,
            unresolved_symbols=unresolved,
            alerts=[],
        )

    severity_filter: set[SeverityLevel] | None = (
        set(payload.severity_in) if payload.severity_in else None
    )
    direction_filter: set[SignalDirection] | None = (
        set(payload.direction_in) if payload.direction_in else None
    )

    company_ids = [c.company_id for c in companies]

    stmt = exclude_suspect_cards(
        select(IntelligenceCard, Company, FinancialPeriod, CompanyEvent)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == IntelligenceCard.period_id)
        .outerjoin(CompanyEvent, CompanyEvent.event_id == IntelligenceCard.event_id)
        .where(IntelligenceCard.is_published.is_(True))
        .where(IntelligenceCard.card_type != "watch_next")
        .where(IntelligenceCard.company_id.in_(company_ids))
    ).order_by(IntelligenceCard.card_priority.desc(), IntelligenceCard.created_at.desc())

    if severity_filter:
        stmt = stmt.where(IntelligenceCard.severity.in_(severity_filter))
    if direction_filter:
        stmt = stmt.where(IntelligenceCard.signal_direction.in_(direction_filter))

    rows = db.execute(stmt).all()

    grouped: dict[int, list[tuple[IntelligenceCard, Company, FinancialPeriod | None, CompanyEvent | None]]] = (
        defaultdict(list)
    )
    for card, comp, per, ev in rows:
        if len(grouped[comp.company_id]) >= payload.limit_per_company:
            continue
        grouped[comp.company_id].append((card, comp, per, ev))

    alerts: list[PortfolioAlert] = []
    triggered_at = datetime.now(timezone.utc)

    for company in companies:
        bucket = grouped.get(company.company_id, [])
        if payload.min_importance is not None:
            bucket = [
                row
                for row in bucket
                if float(row[0].card_priority or 0) >= payload.min_importance
            ]

        objects = [
            build_intelligence_object_brief(card, comp, per, ev, db=db)
            for (card, comp, per, ev) in bucket
        ]
        matched = bool(objects)
        alerts.append(
            PortfolioAlert(
                company=_company_brief_only(company),
                matched=matched,
                reason=_reason_from_objects(objects),
                top_objects=objects,
                triggered_at=triggered_at if matched else None,
            )
        )

    alerts.sort(
        key=lambda a: (
            -1 if a.matched else 0,
            -(a.top_objects[0].importance_score if a.top_objects else 0),
        )
    )

    return PortfolioMonitorResponse(
        requested_symbols=payload.symbols,
        resolved_companies=len(companies),
        unresolved_symbols=unresolved,
        alerts=alerts,
    )


def _company_brief_only(company: Company):
    """Tiny wrapper around `company_brief` that avoids a circular import."""

    from app.routers._helpers import company_brief

    return company_brief(company)
