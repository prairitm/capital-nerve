"""v1 signals router — typed signal feed and detail."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import SeverityLevel, SignalDirection
from app.models.intelligence import (
    CalculatedMetric,
    GeneratedSignal,
    MetricDefinition,
    SignalDefinition,
)
from app.models.master import Company, FinancialPeriod, Sector
from app.models.user import AppUser
from app.routers._helpers import company_brief, find_company, period_brief
from app.schemas.common import CardBrief, CardMetricComparison, DocumentBrief, FinancialTrend
from app.schemas.v1.signals import (
    SignalBriefV1,
    SignalCalculation,
    SignalDetailV1,
    SignalEventBrief,
    SignalPrimaryMetric,
    SignalRelatedBrief,
    SignalRuleLeaf,
)
from app.services.signal_context import enrich_signal_detail

router = APIRouter(prefix="/v1", tags=["v1: signals"])


def _signal_query():
    return (
        select(GeneratedSignal, SignalDefinition, Company, Sector, FinancialPeriod)
        .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
        .join(Company, Company.company_id == GeneratedSignal.company_id)
        .outerjoin(Sector, Sector.sector_id == Company.sector_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == GeneratedSignal.period_id)
        .where(GeneratedSignal.is_published.is_(True))
    )


def _signal_brief(
    sig: GeneratedSignal,
    sd: SignalDefinition,
    comp: Company,
    sec: Sector | None,
    per: FinancialPeriod | None,
) -> SignalBriefV1:
    return SignalBriefV1(
        signal_id=sig.signal_id,
        signal_code=sd.signal_code,
        signal_name=sd.signal_name,
        signal_category=sd.signal_category,
        direction=sig.signal_direction,
        severity=sig.severity,
        confidence_score=float(sig.confidence_score) if sig.confidence_score is not None else None,
        signal_score=float(sig.signal_score) if sig.signal_score is not None else None,
        headline=sig.headline,
        explanation=sig.explanation,
        company=company_brief(comp, sec),
        period=period_brief(per),
        event_id=sig.event_id,
        document_id=sig.document_id,
        created_at=sig.created_at,
    )


@router.get("/companies/{symbol}/signals", response_model=list[SignalBriefV1])
def list_company_signals(
    symbol: str,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    category: str | None = None,
    severity: SeverityLevel | None = None,
    direction: SignalDirection | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SignalBriefV1]:
    company = find_company(db, symbol)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    stmt = _signal_query().where(GeneratedSignal.company_id == company.company_id)
    if category:
        stmt = stmt.where(SignalDefinition.signal_category == category)
    if severity:
        stmt = stmt.where(GeneratedSignal.severity == severity)
    if direction:
        stmt = stmt.where(GeneratedSignal.signal_direction == direction)
    stmt = stmt.order_by(
        GeneratedSignal.signal_score.desc().nullslast(), GeneratedSignal.created_at.desc()
    ).limit(limit)

    rows = db.execute(stmt).all()
    return [_signal_brief(sig, sd, comp, sec, per) for sig, sd, comp, sec, per in rows]


@router.get("/signals", response_model=list[SignalBriefV1])
def list_signals(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
    category: str | None = None,
    severity: SeverityLevel | None = None,
    direction: SignalDirection | None = None,
    sector: str | None = None,
    min_confidence: float | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SignalBriefV1]:
    stmt = _signal_query()
    if category:
        stmt = stmt.where(SignalDefinition.signal_category == category)
    if severity:
        stmt = stmt.where(GeneratedSignal.severity == severity)
    if direction:
        stmt = stmt.where(GeneratedSignal.signal_direction == direction)
    if sector:
        stmt = stmt.where(Sector.sector_name.ilike(f"%{sector}%"))
    if min_confidence is not None:
        stmt = stmt.where(GeneratedSignal.confidence_score >= min_confidence)
    stmt = stmt.order_by(
        GeneratedSignal.signal_score.desc().nullslast(), GeneratedSignal.created_at.desc()
    ).limit(limit)

    rows = db.execute(stmt).all()
    return [_signal_brief(sig, sd, comp, sec, per) for sig, sd, comp, sec, per in rows]


@router.get("/signals/categories", response_model=list[dict])
def signal_categories(
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[dict]:
    """Categories used by the Signal Screener filter chip row."""
    defs = db.scalars(select(SignalDefinition)).all()
    seen: dict[str, str] = {}
    for d in defs:
        if d.signal_category not in seen:
            seen[d.signal_category] = d.signal_category.replace("_", " ").title()
    return [{"value": k, "label": v} for k, v in seen.items()]


@router.get("/signals/{signal_id}", response_model=SignalDetailV1)
def signal_detail(
    signal_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> SignalDetailV1:
    row = db.execute(_signal_query().where(GeneratedSignal.signal_id == signal_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")
    sig, sd, comp, sec, per = row

    base = _signal_brief(sig, sd, comp, sec, per)
    rule = sd.rule_json or {}

    # Build the structured SignalCalculation from the primary metric. The
    # legacy detail returned this even when the rule was a tree; we keep it
    # for parity so the drawer card can still render a quick calculation
    # block.
    calculation: SignalCalculation | None = None
    if rule:
        current_value: float | None = None
        change_percent: float | None = None
        change_bps: float | None = None
        unit: str | None = None
        if sig.primary_metric_id is not None:
            metric_row = db.execute(
                select(CalculatedMetric, MetricDefinition)
                .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
                .where(CalculatedMetric.metric_id == sig.primary_metric_id)
            ).first()
            if metric_row:
                cm, md = metric_row
                current_value = float(cm.metric_value) if cm.metric_value is not None else None
                change_percent = float(cm.change_percent) if cm.change_percent is not None else None
                change_bps = float(cm.change_bps) if cm.change_bps is not None else None
                unit = md.unit
        calculation = SignalCalculation(
            metric_code=rule.get("metric"),
            operator=rule.get("operator"),
            threshold=rule.get("threshold"),
            current_value=current_value,
            previous_value=None,
            change_percent=change_percent,
            change_bps=change_bps,
            unit=unit,
            rule_text=sd.rule_text,
        )

    enrichment = enrich_signal_detail(db, sig, sd, comp, sec, per, base={})

    metric_comparisons = [
        CardMetricComparison(**row) for row in enrichment.get("metric_comparisons", [])
    ]
    trend_sparklines = [
        FinancialTrend(**trend) for trend in enrichment.get("trend_sparklines", [])
    ]
    related_cards = [CardBrief(**card) for card in enrichment.get("related_cards", [])]
    related_signals = [
        SignalRelatedBrief(**sig_row) for sig_row in enrichment.get("related_signals", [])
    ]
    rule_leaves = [SignalRuleLeaf(**leaf) for leaf in enrichment.get("rule_leaves", [])]
    evidence = enrichment.get("evidence", [])

    trigger_raw = enrichment.get("trigger_metric")
    trigger_metric = CardMetricComparison(**trigger_raw) if trigger_raw else None

    primary_raw = enrichment.get("primary_metric")
    primary_metric = SignalPrimaryMetric(**primary_raw) if primary_raw else None

    event_brief: SignalEventBrief | None = None
    if (event_raw := enrichment.get("event")) is not None:
        event_brief = SignalEventBrief(**event_raw)

    document_brief: DocumentBrief | None = None
    if (doc_raw := enrichment.get("document")) is not None:
        document_brief = DocumentBrief(**doc_raw)

    return SignalDetailV1(
        **base.model_dump(),
        description=sd.description,
        rule_text=sd.rule_text,
        rule_summary=enrichment.get("rule_summary"),
        rule_json=rule,
        rule_metric_codes=enrichment.get("rule_metric_codes", []),
        rule_leaves=rule_leaves,
        calculation=calculation,
        primary_metric=primary_metric,
        trigger_metric=trigger_metric,
        metric_refs=sig.metric_refs or [],
        evidence_refs=sig.evidence_refs or [],
        metric_comparisons=metric_comparisons,
        trend_sparklines=trend_sparklines,
        related_cards=related_cards,
        related_signals=related_signals,
        evidence=evidence,
        event=event_brief,
        document=document_brief,
    )
