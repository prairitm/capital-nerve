"""v1 Intelligence Object router — the canonical decision-package endpoint.

Every response goes through `services.intelligence_object_builder` so the IO
shape stays consistent across the nested company route, the cross-company feed,
and the by-id endpoint.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import SeverityLevel, SignalDirection
from app.models.events import CompanyEvent, SourceDocument
from app.models.intelligence import IntelligenceCard
from app.models.master import Company, FinancialPeriod, Sector
from app.models.user import AppUser, Watchlist, WatchlistCompany
from app.routers._helpers import find_company
from app.schemas.v1.feed import FeedSummaryV1
from app.schemas.v1.intelligence_object import (
    IntelligenceObject,
    IntelligenceObjectBrief,
)
from app.services.intelligence_object_builder import (
    build_intelligence_object,
    build_intelligence_object_brief,
)

router = APIRouter(prefix="/v1", tags=["v1: intelligence-objects"])


def _io_query():
    """Canonical join for published intelligence objects."""

    return (
        select(IntelligenceCard, Company, FinancialPeriod, CompanyEvent, SourceDocument)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == IntelligenceCard.period_id)
        .outerjoin(CompanyEvent, CompanyEvent.event_id == IntelligenceCard.event_id)
        .outerjoin(SourceDocument, SourceDocument.document_id == IntelligenceCard.document_id)
        .where(IntelligenceCard.is_published.is_(True))
        .where(IntelligenceCard.card_type != "watch_next")
    )


def _apply_feed_scope(
    stmt,
    *,
    db: Session,
    user: AppUser,
    feed: Literal["home", "watchlist", "company"],
    company_id: int | None,
) -> tuple:
    """Watchlist scoping and watch-next exclusion for home / watchlist feeds."""
    if feed == "watchlist":
        wl = db.scalar(select(Watchlist).where(Watchlist.user_id == user.user_id).limit(1))
        if wl:
            sub = select(WatchlistCompany.company_id).where(
                WatchlistCompany.watchlist_id == wl.watchlist_id
            )
            stmt = stmt.where(IntelligenceCard.company_id.in_(sub))
        else:
            return None
    if feed == "company" and company_id:
        stmt = stmt.where(IntelligenceCard.company_id == company_id)
    return stmt


def _apply_feed_tab(stmt, tab: str):
    """Pulse / tab filters — same semantics as the former `GET /cards` endpoint."""
    if tab == "results":
        return stmt.where(
            IntelligenceCard.card_type.in_(["result_verdict", "revenue_growth", "margin_movement"])
        )
    if tab in ("red_flags", "risks"):
        return stmt.where(
            IntelligenceCard.card_type.in_(["red_flag", "profit_quality", "expense_pressure"])
        )
    if tab == "positive":
        return stmt.where(IntelligenceCard.signal_direction == SignalDirection.POSITIVE)
    if tab == "negative":
        return stmt.where(IntelligenceCard.signal_direction == SignalDirection.NEGATIVE)
    if tab == "margin_pressure":
        return stmt.where(IntelligenceCard.card_type == "margin_movement").where(
            IntelligenceCard.signal_direction == SignalDirection.NEGATIVE
        )
    if tab == "verdicts":
        return stmt.where(IntelligenceCard.card_type == "result_verdict")
    if tab == "growth":
        return stmt.where(IntelligenceCard.card_type == "revenue_growth")
    if tab == "margins":
        return stmt.where(IntelligenceCard.card_type == "margin_movement")
    if tab in ("management", "concall"):
        return stmt.where(
            IntelligenceCard.card_type.in_(
                ["management_tone", "guidance_tracker", "analyst_concern"]
            )
        )
    return stmt


def _feed_order(stmt, *, feed: Literal["home", "watchlist", "company"]):
    if feed in ("home", "watchlist"):
        return stmt.order_by(
            CompanyEvent.event_date.desc().nullslast(),
            IntelligenceCard.created_at.desc(),
            IntelligenceCard.card_id.desc(),
        )
    return stmt.order_by(
        IntelligenceCard.card_priority.desc(),
        IntelligenceCard.created_at.desc(),
        IntelligenceCard.card_id.desc(),
    )


@router.get(
    "/companies/{symbol}/intelligence-objects",
    response_model=list[IntelligenceObjectBrief],
)
def list_company_intelligence_objects(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    period: str | None = Query(default=None, description="Period display label or fy_label"),
    card_type: str | None = None,
    direction: SignalDirection | None = None,
    severity: SeverityLevel | None = None,
    min_importance: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=30, ge=1, le=200),
) -> list[IntelligenceObjectBrief]:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    stmt = _io_query().where(IntelligenceCard.company_id == company.company_id)
    if card_type:
        stmt = stmt.where(IntelligenceCard.card_type == card_type)
    if direction:
        stmt = stmt.where(IntelligenceCard.signal_direction == direction)
    if severity:
        stmt = stmt.where(IntelligenceCard.severity == severity)
    if min_importance is not None:
        stmt = stmt.where(IntelligenceCard.card_priority >= min_importance)
    if period:
        clean = period.strip()
        stmt = stmt.where(
            (FinancialPeriod.display_label.ilike(clean)) | (FinancialPeriod.fy_label.ilike(clean))
        )

    stmt = stmt.order_by(
        IntelligenceCard.card_priority.desc(),
        IntelligenceCard.created_at.desc(),
        IntelligenceCard.card_id.desc(),
    ).limit(limit)

    rows = db.execute(stmt).all()
    return [
        build_intelligence_object_brief(card, comp, per, ev)
        for (card, comp, per, ev, _doc) in rows
    ]


@router.get("/intelligence-objects", response_model=list[IntelligenceObjectBrief])
def list_intelligence_objects(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    feed: Literal["home", "watchlist", "company"] = "home",
    tab: Literal[
        "all",
        "results",
        "red_flags",
        "positive",
        "negative",
        "margin_pressure",
        "management",
        "verdicts",
        "growth",
        "margins",
        "risks",
        "concall",
    ] = "all",
    company: str | None = Query(default=None, description="NSE/BSE symbol"),
    company_id: int | None = None,
    sector: str | None = None,
    direction: SignalDirection | None = None,
    severity: SeverityLevel | None = None,
    card_type: str | None = None,
    min_importance: int | None = Query(default=None, ge=0, le=100),
    period: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[IntelligenceObjectBrief]:
    stmt = _io_query()
    scoped = _apply_feed_scope(
        stmt, db=db, user=user, feed=feed, company_id=company_id
    )
    if scoped is None:
        return []
    stmt = scoped
    if company:
        target = find_company(db, company)
        if not target:
            raise HTTPException(status_code=404, detail="Company not found")
        stmt = stmt.where(IntelligenceCard.company_id == target.company_id)
    if sector:
        stmt = stmt.join(Sector, Sector.sector_id == Company.sector_id).where(
            Sector.sector_name.ilike(f"%{sector}%")
        )
    if direction:
        stmt = stmt.where(IntelligenceCard.signal_direction == direction)
    if severity:
        stmt = stmt.where(IntelligenceCard.severity == severity)
    if card_type:
        stmt = stmt.where(IntelligenceCard.card_type == card_type)
    if min_importance is not None:
        stmt = stmt.where(IntelligenceCard.card_priority >= min_importance)
    if period:
        clean = period.strip()
        stmt = stmt.where(
            (FinancialPeriod.display_label.ilike(clean)) | (FinancialPeriod.fy_label.ilike(clean))
        )
    stmt = _apply_feed_tab(stmt, tab)
    stmt = _feed_order(stmt, feed=feed).limit(limit)

    rows = db.execute(stmt).all()
    return [
        build_intelligence_object_brief(card, comp, per, ev)
        for (card, comp, per, ev, _doc) in rows
    ]


@router.get("/intelligence-objects/summary", response_model=FeedSummaryV1)
def intelligence_objects_summary(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> FeedSummaryV1:
    """Counters used by the home feed's market pulse strip.

    Replaces the legacy `GET /cards/summary` dict response with a typed
    schema. Counts are computed across **published** cards so the strip and
    the feed never disagree on what the user can see.
    """
    cards = db.scalars(
        select(IntelligenceCard).where(IntelligenceCard.is_published.is_(True))
    ).all()

    positive = sum(1 for c in cards if c.signal_direction == SignalDirection.POSITIVE)
    negative = sum(1 for c in cards if c.signal_direction == SignalDirection.NEGATIVE)
    red_flags = sum(
        1 for c in cards if c.card_type in {"red_flag", "profit_quality", "expense_pressure"}
    )
    margin = sum(
        1
        for c in cards
        if c.card_type == "margin_movement"
        and c.signal_direction == SignalDirection.NEGATIVE
    )
    verdicts = sum(1 for c in cards if c.card_type == "result_verdict")
    growth = sum(1 for c in cards if c.card_type == "revenue_growth")
    margins = sum(1 for c in cards if c.card_type == "margin_movement")
    guidance = sum(
        1
        for c in cards
        if c.card_type in {"guidance_tracker", "management_tone", "analyst_concern"}
    )

    return FeedSummaryV1(
        results_processed=verdicts,
        positive_signals=positive,
        negative_signals=negative,
        margin_warnings=margin,
        red_flags=red_flags,
        guidance_updates=guidance,
        verdicts=verdicts,
        growth=growth,
        margins=margins,
        risks=red_flags,
    )


@router.get("/intelligence-objects/{object_id}", response_model=IntelligenceObject)
def get_intelligence_object(
    object_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> IntelligenceObject:
    row = db.execute(_io_query().where(IntelligenceCard.card_id == object_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Intelligence object not found")
    card, comp, per, ev, doc = row
    return build_intelligence_object(db, card, comp, per, ev, doc)
