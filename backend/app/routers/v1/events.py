"""v1 events router — `/v1/companies/{symbol}/events` and `/v1/events/{id}`."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import EventType
from app.models.events import CompanyEvent, SourceDocument
from app.models.facts import (
    AnalystQuestion,
    ConcallFact,
    FinancialLineItemDefinition,
    FinancialStatementFact,
)
from app.models.intelligence import (
    GeneratedSignal,
    IntelligenceCard,
    SignalDefinition,
)
from app.models.master import Company, FinancialPeriod, Sector
from app.models.user import AppUser
from app.routers._helpers import card_brief, company_brief, find_company, period_brief
from app.routers.v1.signals import _signal_brief
from app.schemas.common import (
    CardBrief,
    DocumentBrief,
    ConcernHeatmapRow,
    TimelineEvent,
)
from app.schemas.v1.events import (
    EventBriefV1,
    EventConcallFact,
    EventDetailV1,
    EventIngestionStatus,
    EventRawFacts,
)
from app.schemas.v1.signals import SignalBriefV1
from app.services.event_financials import build_financial_snapshot_for_period
from app.services.event_summary import (
    load_signals_and_cards_by_event,
    pick_main_issue,
    pick_watch_next,
    resolve_event_summary_text,
)

router = APIRouter(prefix="/v1", tags=["v1: events"])


# Spec §7 card ordering on the event page.
_CARD_ORDER: tuple[str, ...] = (
    "result_verdict",
    "revenue_growth",
    "margin_movement",
    "profit_quality",
    "expense_pressure",
    "segment_performance",
    "balance_sheet",
    "red_flag",
    "management_tone",
    "guidance_tracker",
    "analyst_concern",
)


@router.get("/companies/{symbol}/events", response_model=list[EventBriefV1])
def list_company_events(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    event_type: EventType | None = None,
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[EventBriefV1]:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    stmt = (
        select(CompanyEvent, FinancialPeriod)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == CompanyEvent.period_id)
        .where(CompanyEvent.company_id == company.company_id)
        .where(CompanyEvent.is_published.is_(True))
    )
    if event_type:
        stmt = stmt.where(CompanyEvent.event_type == event_type)
    stmt = stmt.order_by(CompanyEvent.event_date.desc(), CompanyEvent.event_id.desc()).offset(offset).limit(limit)

    rows = db.execute(stmt).all()
    events = [event for (event, _period) in rows]
    sigs_by, cards_by = load_signals_and_cards_by_event(
        db, [e.event_id for e in events]
    )

    return [
        EventBriefV1(
            event_id=event.event_id,
            event_type=event.event_type,
            event_title=event.event_title,
            event_date=event.event_date,
            company=company_brief(company),
            period=period_brief(period),
            source_exchange=event.source_exchange.value if event.source_exchange else None,
            consolidation=event.consolidation,
            overall_signal=event.overall_signal,
            overall_severity=event.overall_severity,
            overall_confidence=float(event.overall_confidence) if event.overall_confidence is not None else None,
            summary_text=resolve_event_summary_text(
                event,
                sigs_by.get(event.event_id, []),
                cards_by.get(event.event_id, []),
            ),
        )
        for (event, period) in rows
    ]


@router.get("/events/{event_id}", response_model=EventDetailV1)
def event_detail(
    event_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> EventDetailV1:
    event = db.get(CompanyEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    company = db.get(Company, event.company_id)
    period = db.get(FinancialPeriod, event.period_id) if event.period_id else None

    docs = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.event_id == event_id)
        .order_by(SourceDocument.document_date.desc().nullslast())
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

    raw_facts: list[EventRawFacts] = []
    if event.period_id:
        fact_rows = db.execute(
            select(FinancialStatementFact, FinancialLineItemDefinition)
            .join(
                FinancialLineItemDefinition,
                FinancialLineItemDefinition.line_item_def_id == FinancialStatementFact.line_item_def_id,
            )
            .where(FinancialStatementFact.company_id == event.company_id)
            .where(FinancialStatementFact.period_id == event.period_id)
            .where(FinancialStatementFact.period_value_type == "CURRENT")
            .order_by(FinancialLineItemDefinition.normalized_code)
        ).all()
        raw_facts = [
            EventRawFacts(
                line_item_code=li.normalized_code,
                line_item_name=li.display_name,
                value=float(fact.value),
                unit=fact.unit or "",
                period_value_type=fact.period_value_type,
                consolidation=fact.consolidation,
            )
            for (fact, li) in fact_rows
        ]

    metric_snapshot: dict[str, object] = {}
    for fact in raw_facts:
        if fact.line_item_code in {"revenue_from_operations", "ebitda", "ebitda_margin", "pat"}:
            metric_snapshot[fact.line_item_code] = fact.value

    # ---- Cards on this event ----
    card_rows = db.execute(
        select(IntelligenceCard, Company, FinancialPeriod, CompanyEvent, SourceDocument)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == IntelligenceCard.period_id)
        .outerjoin(CompanyEvent, CompanyEvent.event_id == IntelligenceCard.event_id)
        .outerjoin(SourceDocument, SourceDocument.document_id == IntelligenceCard.document_id)
        .where(IntelligenceCard.event_id == event_id)
        .where(IntelligenceCard.card_type != "watch_next")
    ).all()
    card_models = [c for (c, *_rest) in card_rows]
    published_card_rows = [row for row in card_rows if row[0].is_published]
    cards: list[CardBrief] = [
        card_brief(c, comp, per, ev, doc) for (c, comp, per, ev, doc) in published_card_rows
    ]
    cards.sort(
        key=lambda c: (
            _CARD_ORDER.index(c.card_type) if c.card_type in _CARD_ORDER else 99,
            -c.card_priority,
        )
    )

    # ---- Signals from this event ----
    sigs_by_event, _cards_by = load_signals_and_cards_by_event(db, [event_id])
    sigs = sigs_by_event.get(event_id, [])

    signal_rows = db.execute(
        select(GeneratedSignal, SignalDefinition, Company, Sector, FinancialPeriod)
        .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
        .join(Company, Company.company_id == GeneratedSignal.company_id)
        .outerjoin(Sector, Sector.sector_id == Company.sector_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == GeneratedSignal.period_id)
        .where(GeneratedSignal.event_id == event_id)
        .where(GeneratedSignal.is_published.is_(True))
        .order_by(GeneratedSignal.signal_score.desc().nullslast(), GeneratedSignal.created_at.desc())
    ).all()
    signals: list[SignalBriefV1] = [
        _signal_brief(sig, sd, comp, sec, per) for sig, sd, comp, sec, per in signal_rows
    ]

    # ---- Financial snapshot ----
    financial_snapshot = build_financial_snapshot_for_period(db, event.company_id, period)

    # ---- Related events ----
    related_rows = db.scalars(
        select(CompanyEvent)
        .where(CompanyEvent.company_id == event.company_id)
        .order_by(CompanyEvent.event_date.desc(), CompanyEvent.event_id.desc())
        .limit(8)
    ).all()
    related_events: list[TimelineEvent] = [
        TimelineEvent(
            event_id=e.event_id,
            event_type=e.event_type,
            event_title=e.event_title,
            event_date=e.event_date,
            overall_signal=e.overall_signal,
            overall_severity=e.overall_severity,
            summary_text=e.summary_text,
        )
        for e in related_rows
        if e.event_id != event_id
    ][:5]

    # ---- Concern heatmap from analyst questions ----
    questions = db.scalars(select(AnalystQuestion).where(AnalystQuestion.event_id == event_id)).all()
    heatmap_counts: dict[str, int] = {}
    for q in questions:
        topic = q.topic or "Other"
        heatmap_counts[topic] = heatmap_counts.get(topic, 0) + 1
    total_q = sum(heatmap_counts.values()) or 1
    concern_heatmap = [
        ConcernHeatmapRow(topic=t, count=c, percent=round(c / total_q * 100, 1))
        for t, c in sorted(heatmap_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # ---- Concall facts ----
    doc_by_id = {d.document_id: d for d in docs}
    concall_facts_rows = db.scalars(
        select(ConcallFact).where(ConcallFact.event_id == event_id)
    ).all()
    concall_facts: list[EventConcallFact] = []
    for f in concall_facts_rows:
        doc = doc_by_id.get(f.document_id) if f.document_id else None
        page_number: int | None = None
        if isinstance(f.meta, dict) and f.meta.get("page") is not None:
            try:
                page_number = int(f.meta["page"])
            except (TypeError, ValueError):
                page_number = None
        concall_facts.append(
            EventConcallFact(
                fact_type=f.fact_type,
                topic=f.topic,
                extracted_claim=f.extracted_claim,
                direction=f.direction,
                severity=f.severity,
                target_period=f.target_period,
                document_id=f.document_id,
                document_title=doc.document_title if doc else None,
                page_number=page_number,
            )
        )

    # ---- Ingestion telemetry ----
    values_extracted_total = sum((d.values_extracted or 0) for d in docs)
    unpublished_card_count = sum(1 for c in card_models if not c.is_published)
    unpublished_signal_count = sum(1 for s in sigs if not s.is_published)
    ingestion_status = EventIngestionStatus(
        published_card_count=len(cards),
        unpublished_card_count=unpublished_card_count,
        published_signal_count=len(signals),
        unpublished_signal_count=unpublished_signal_count,
        document_count=len(docs),
        values_extracted_total=values_extracted_total,
    )

    summary_text = resolve_event_summary_text(event, sigs, card_models)

    return EventDetailV1(
        event_id=event.event_id,
        event_type=event.event_type,
        event_title=event.event_title,
        event_date=event.event_date,
        company=company_brief(company) if company else None,
        period=period_brief(period),
        source_exchange=event.source_exchange.value if event.source_exchange else None,
        consolidation=event.consolidation,
        overall_signal=event.overall_signal,
        overall_severity=event.overall_severity,
        overall_confidence=float(event.overall_confidence) if event.overall_confidence is not None else None,
        summary_text=summary_text,
        main_issue=event.main_issue or pick_main_issue(sigs, card_models),
        watch_next=event.watch_next or pick_watch_next(card_models),
        audit_status=event.audit_status.value if event.audit_status else None,
        raw_facts=raw_facts,
        documents=documents,
        metric_snapshot=metric_snapshot,
        cards=cards,
        signals=signals,
        financial_snapshot=financial_snapshot,
        related_events=related_events,
        concern_heatmap=concern_heatmap,
        concall_facts=concall_facts,
        ingestion_status=ingestion_status,
    )
