"""v1 companies router — typed company hub + list.

Replaces the legacy `GET /companies` and `GET /companies/{symbol}` blob
endpoints. The hub payload (`CompanyHubV1`) embeds the latest-event verdict,
top intelligence objects, financial snapshot, 8-quarter trends, event
timeline, and source documents — everything the company page needs in a
single round-trip.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import EventType
from app.models.events import CompanyEvent, SourceDocument
from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import IntelligenceCard
from app.models.master import Company, FinancialPeriod, Sector
from app.models.user import AppUser, Watchlist, WatchlistCompany
from app.routers._helpers import company_brief, find_company, period_brief
from app.schemas.common import (
    CompanyBadge,
    CompanyBrief,
    DocumentBrief,
    FinancialSnapshotRow,
    FinancialTrend,
    FinancialTrendPoint,
    TimelineEvent,
)
from app.schemas.v1.companies import CompanyHubV1
from app.schemas.v1.intelligence_object import IntelligenceObjectBrief
from app.services.event_summary import (
    load_signals_and_cards_by_event,
    pick_main_issue,
    pick_watch_next,
    resolve_event_summary_text,
)
from app.services.intelligence_object_builder import build_intelligence_object_brief

router = APIRouter(prefix="/v1", tags=["v1: companies"])


_SNAPSHOT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("revenue_from_operations", "Revenue", "Cr"),
    ("ebitda", "EBITDA", "Cr"),
    ("ebitda_margin", "EBITDA Margin", "%"),
    ("pat", "PAT", "Cr"),
    ("eps_basic", "EPS", "Rs"),
)

_BADGE_CARD_TYPES: dict[str, str] = {
    "revenue_growth": "Growth",
    "margin_movement": "Margins",
    "profit_quality": "Profit Quality",
    "red_flag": "Red Flags",
    "management_tone": "Management Tone",
}

_DIRECTION_TONE: dict[str, str] = {
    "POSITIVE": "positive",
    "NEGATIVE": "negative",
    "MIXED": "mixed",
    "NEUTRAL": "neutral",
}


@router.get("/companies", response_model=list[CompanyBrief])
def list_companies(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    search: str | None = None,
    sector: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CompanyBrief]:
    """Searchable company list — replaces legacy `GET /companies`."""
    stmt = select(Company, Sector).join(Sector, Sector.sector_id == Company.sector_id, isouter=True)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                Company.company_name.ilike(like),
                Company.nse_symbol.ilike(like),
                Company.bse_code.ilike(like),
                Company.short_name.ilike(like),
            )
        )
    if sector:
        stmt = stmt.where(Sector.sector_name.ilike(f"%{sector}%"))
    stmt = stmt.order_by(Company.company_name.asc()).limit(limit)
    rows = db.execute(stmt).all()
    return [company_brief(c, s) for (c, s) in rows]


@router.get("/companies/{symbol}", response_model=CompanyHubV1)
def company_hub(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> CompanyHubV1:
    """Single-call company-page payload."""
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    latest_event = db.scalars(
        select(CompanyEvent)
        .where(CompanyEvent.company_id == company.company_id)
        .where(CompanyEvent.event_type == EventType.QUARTERLY_RESULT)
        .order_by(CompanyEvent.event_date.desc())
        .limit(1)
    ).first()
    if not latest_event:
        latest_event = db.scalars(
            select(CompanyEvent)
            .where(CompanyEvent.company_id == company.company_id)
            .order_by(CompanyEvent.event_date.desc())
            .limit(1)
        ).first()

    latest_period: FinancialPeriod | None = None
    if latest_event and latest_event.period_id:
        latest_period = db.get(FinancialPeriod, latest_event.period_id)

    top_object_rows = db.execute(
        select(IntelligenceCard, Company, FinancialPeriod, CompanyEvent, SourceDocument)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == IntelligenceCard.period_id)
        .outerjoin(CompanyEvent, CompanyEvent.event_id == IntelligenceCard.event_id)
        .outerjoin(SourceDocument, SourceDocument.document_id == IntelligenceCard.document_id)
        .where(IntelligenceCard.company_id == company.company_id)
        .where(IntelligenceCard.is_published.is_(True))
        .where(IntelligenceCard.card_type != "watch_next")
        .order_by(IntelligenceCard.card_priority.desc(), IntelligenceCard.created_at.desc())
        .limit(8)
    ).all()
    top_objects: list[IntelligenceObjectBrief] = [
        build_intelligence_object_brief(card, comp, per, ev)
        for (card, comp, per, ev, _doc) in top_object_rows
    ]

    events = db.scalars(
        select(CompanyEvent)
        .where(CompanyEvent.company_id == company.company_id)
        .order_by(CompanyEvent.event_date.desc())
        .limit(30)
    ).all()
    event_ids = [e.event_id for e in events]
    sigs_by_event, cards_by_event = load_signals_and_cards_by_event(db, event_ids)
    timeline = [
        TimelineEvent(
            event_id=e.event_id,
            event_type=e.event_type,
            event_title=e.event_title,
            event_date=e.event_date,
            overall_signal=e.overall_signal,
            overall_severity=e.overall_severity,
            summary_text=resolve_event_summary_text(
                e,
                sigs_by_event.get(e.event_id, []),
                cards_by_event.get(e.event_id, []),
            ),
        )
        for e in events
    ]

    docs = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.company_id == company.company_id)
        .order_by(SourceDocument.document_date.desc().nullslast())
        .limit(20)
    ).all()
    documents = [
        DocumentBrief(
            document_id=d.document_id,
            document_type=d.document_type,
            document_title=d.document_title,
            document_date=d.document_date,
            extraction_confidence=float(d.extraction_confidence) if d.extraction_confidence is not None else None,
            values_extracted=d.values_extracted,
            cards_generated=d.cards_generated,
        )
        for d in docs
    ]

    line_items = db.scalars(
        select(FinancialLineItemDefinition).where(
            FinancialLineItemDefinition.normalized_code.in_([code for code, _, _ in _SNAPSHOT_ROWS])
        )
    ).all()
    items_by_code = {li.normalized_code: li for li in line_items}

    periods = db.scalars(
        select(FinancialPeriod).order_by(FinancialPeriod.period_end_date.asc())
    ).all()

    trends: list[FinancialTrend] = []
    snapshot: list[FinancialSnapshotRow] = []

    for code, display, unit in _SNAPSHOT_ROWS:
        li = items_by_code.get(code)
        if not li:
            continue
        facts = db.scalars(
            select(FinancialStatementFact).where(
                FinancialStatementFact.company_id == company.company_id,
                FinancialStatementFact.line_item_def_id == li.line_item_def_id,
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        ).all()
        fact_by_period = {f.period_id: float(f.value) for f in facts}
        points = [
            FinancialTrendPoint(
                period_label=p.display_label,
                period_end_date=p.period_end_date,
                value=fact_by_period[p.period_id],
            )
            for p in periods
            if p.period_id in fact_by_period
        ]
        trends.append(
            FinancialTrend(
                metric_code=code, metric_name=display, unit=unit, points=points
            )
        )

        if latest_period and latest_period.period_id in fact_by_period:
            cur_val = fact_by_period[latest_period.period_id]
            prev_period_id = next(
                (
                    p.period_id
                    for p in periods
                    if (
                        p.fy_year == latest_period.fy_year - 1
                        and p.quarter == latest_period.quarter
                        and p.period_type == latest_period.period_type
                    )
                ),
                None,
            )
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

    watchlist_status = False
    wl = db.scalar(select(Watchlist).where(Watchlist.user_id == user.user_id).limit(1))
    if wl:
        exists = db.scalar(
            select(WatchlistCompany).where(
                WatchlistCompany.watchlist_id == wl.watchlist_id,
                WatchlistCompany.company_id == company.company_id,
            )
        )
        watchlist_status = exists is not None

    badges: list[CompanyBadge] = []
    if latest_event and latest_event.overall_signal:
        badges.append(
            CompanyBadge(
                label="Latest Result",
                value=latest_event.overall_signal.value.title(),
                tone=_DIRECTION_TONE.get(latest_event.overall_signal.value, "neutral"),
            )
        )
    if latest_period:
        for obj in top_objects:
            label = _BADGE_CARD_TYPES.get(obj.object_type)
            if not label or any(b.label == label for b in badges):
                continue
            tone = "neutral"
            value = "Neutral"
            if obj.status:
                sd = obj.status.value
                tone = _DIRECTION_TONE.get(sd, "neutral")
                value = sd.title()
            badges.append(CompanyBadge(label=label, value=value, tone=tone))

    latest_summary = (
        resolve_event_summary_text(
            latest_event,
            sigs_by_event.get(latest_event.event_id, []),
            cards_by_event.get(latest_event.event_id, []),
        )
        if latest_event
        else None
    )
    main_issue = (
        latest_event.main_issue
        or (
            pick_main_issue(
                sigs_by_event.get(latest_event.event_id, []),
                cards_by_event.get(latest_event.event_id, []),
            )
            if latest_event
            else None
        )
    )
    watch_next = (
        latest_event.watch_next
        or (
            pick_watch_next(cards_by_event.get(latest_event.event_id, []))
            if latest_event
            else None
        )
    )

    return CompanyHubV1(
        company=company_brief(company),
        watchlist_status=watchlist_status,
        badges=badges,
        latest_event_id=latest_event.event_id if latest_event else None,
        latest_period=period_brief(latest_period),
        latest_summary=latest_summary,
        main_issue=main_issue,
        watch_next=watch_next,
        top_objects=top_objects,
        financial_snapshot=snapshot,
        trends=trends,
        timeline=timeline,
        documents=documents,
    )
