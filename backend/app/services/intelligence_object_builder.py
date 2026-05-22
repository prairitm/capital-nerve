"""Build an `IntelligenceObject` from the existing pipeline tables.

Every v1 router that returns an Intelligence Object goes through this module so
the derived fields (`importance_score`, `time_horizon`, `suggested_actions`,
`investor_relevance`) are computed in exactly one place.

Inputs are ORM rows already fetched by the router; the service does not raise
HTTPException and never writes. It returns Pydantic schemas from `schemas/v1/`.
"""

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import SeverityLevel, SignalDirection
from app.models.events import CompanyEvent, SourceDocument
from app.models.intelligence import (
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
    SignalDefinition,
)
from app.models.master import Company, FinancialPeriod
from app.routers._helpers import build_source_label, company_brief, period_brief
from app.schemas.common import EvidenceItem
from app.schemas.v1.events import EventBriefV1
from app.schemas.v1.intelligence_object import (
    IntelligenceObject,
    IntelligenceObjectBrief,
    IODisplayConfig,
    IOMetric,
)
from app.schemas.v1.signals import SignalBriefV1
from app.services.card_context import (
    load_concall_heatmap,
    load_metric_comparisons,
    load_trend_sparklines,
    should_show_concall,
)

# Card-type → default display layout. The render hint travels with the object so
# any consumer (drawer, alert, API plugin) renders the same shape.
_LAYOUT_BY_CARD_TYPE: dict[str, str] = {
    "result_verdict": "summary_hero",
    "revenue_growth": "metric_trend",
    "margin_movement": "metric_comparison",
    "profit_quality": "metric_comparison",
    "expense_pressure": "metric_comparison",
    "segment_performance": "segment_breakdown",
    "balance_sheet": "metric_table",
    "red_flag": "warning_callout",
    "management_tone": "narrative",
    "guidance_tracker": "guidance_band",
    "analyst_concern": "heatmap",
    "watch_next": "checklist",
}

_CHART_BY_CARD_TYPE: dict[str, str] = {
    "revenue_growth": "revenue_trend",
    "margin_movement": "margin_trend",
    "profit_quality": "ratio_trend",
    "expense_pressure": "ratio_trend",
    "balance_sheet": "balance_trend",
    "segment_performance": "segment_donut",
    "analyst_concern": "topic_heatmap",
}

_CTA_BY_CARD_TYPE: dict[str, str] = {
    "result_verdict": "Open event detail",
    "revenue_growth": "View revenue drivers",
    "margin_movement": "View margin drivers",
    "profit_quality": "View profit quality breakdown",
    "expense_pressure": "View cost breakdown",
    "segment_performance": "View segment mix",
    "balance_sheet": "View balance sheet",
    "red_flag": "Review red flag",
    "management_tone": "Open concall transcript",
    "guidance_tracker": "View guidance",
    "analyst_concern": "View analyst questions",
}

# Used to derive `time_horizon`. Cards tied to forward-looking narrative get a
# longer horizon; result/margin cards apply to the upcoming quarter.
_LONG_TERM_TYPES = frozenset({"guidance_tracker", "management_tone", "balance_sheet"})
_SHORT_TERM_TYPES = frozenset(
    {"red_flag", "expense_pressure", "margin_movement", "result_verdict"}
)

_RELEVANCE_BY_CARD_TYPE: dict[str, list[str]] = {
    "result_verdict": ["earnings", "verdict"],
    "revenue_growth": ["growth", "topline"],
    "margin_movement": ["profitability", "operating_leverage"],
    "profit_quality": ["earnings_quality", "cash_flow"],
    "expense_pressure": ["cost_structure", "operating_leverage"],
    "segment_performance": ["business_mix", "growth"],
    "balance_sheet": ["leverage", "liquidity"],
    "red_flag": ["governance", "risk"],
    "management_tone": ["management", "outlook"],
    "guidance_tracker": ["guidance", "outlook"],
    "analyst_concern": ["analyst_sentiment", "market_perception"],
    "watch_next": ["watch_item"],
}


def _normalize_importance(card_priority: float | None) -> int:
    """Map raw `card_priority` (seeded ≈ 0–100) to a clipped 0–100 int score."""

    if card_priority is None:
        return 0
    value = float(card_priority)
    if value < 0:
        value = 0
    elif value > 100:
        value = 100
    return int(round(value))


def _derive_time_horizon(card_type: str, severity: SeverityLevel | None) -> str:
    if card_type in _SHORT_TERM_TYPES:
        return "short_term"
    if card_type in _LONG_TERM_TYPES:
        return "medium_term"
    if severity in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}:
        return "short_term"
    return "medium_term"


def _derive_investor_relevance(card_type: str, direction: SignalDirection | None) -> list[str]:
    base = list(_RELEVANCE_BY_CARD_TYPE.get(card_type, ["intelligence"]))
    if direction == SignalDirection.NEGATIVE:
        base.append("risk")
    elif direction == SignalDirection.POSITIVE:
        base.append("opportunity")
    elif direction == SignalDirection.MIXED:
        base.append("mixed_quality")
    # Dedupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for tag in base:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _derive_suggested_actions(
    card_type: str, direction: SignalDirection | None, severity: SeverityLevel | None
) -> list[str]:
    actions: list[str] = []

    if card_type == "margin_movement" and direction == SignalDirection.NEGATIVE:
        actions += [
            "compare_with_peer_margin",
            "check_management_commentary",
            "update_model_assumptions",
        ]
    elif card_type == "margin_movement" and direction == SignalDirection.POSITIVE:
        actions += ["check_operating_leverage_drivers", "compare_with_peer_margin"]
    elif card_type == "revenue_growth":
        actions += ["check_segment_mix", "compare_with_peer_growth"]
    elif card_type == "profit_quality":
        actions += [
            "compare_cfo_vs_pat",
            "inspect_other_income_share",
            "review_working_capital",
        ]
    elif card_type == "expense_pressure":
        actions += ["inspect_cost_breakdown", "compare_with_peer_cost_ratios"]
    elif card_type == "red_flag":
        actions += ["escalate_to_risk_team", "review_evidence", "check_auditor_notes"]
    elif card_type == "guidance_tracker":
        actions += ["update_model_assumptions", "track_management_commentary"]
    elif card_type == "management_tone":
        actions += ["review_concall_transcript", "compare_with_prior_calls"]
    elif card_type == "analyst_concern":
        actions += ["review_analyst_questions", "monitor_topic_recurrence"]
    elif card_type == "balance_sheet":
        actions += ["check_interest_coverage", "monitor_debt_movement"]
    elif card_type == "segment_performance":
        actions += ["review_segment_drivers", "compare_with_peer_segments"]
    elif card_type == "result_verdict":
        actions += ["open_event_detail", "review_metric_comparisons"]

    if severity in {SeverityLevel.HIGH, SeverityLevel.CRITICAL}:
        actions.append("flag_for_review")

    seen: set[str] = set()
    deduped: list[str] = []
    for action in actions:
        if action not in seen:
            seen.add(action)
            deduped.append(action)
    return deduped


def _display_for(card: IntelligenceCard) -> IODisplayConfig:
    ctx = card.display_context or {}
    layout = ctx.get("layout") or _LAYOUT_BY_CARD_TYPE.get(card.card_type, "metric_comparison")
    chart_type = ctx.get("chart_type") or _CHART_BY_CARD_TYPE.get(card.card_type)
    cta = ctx.get("cta") or _CTA_BY_CARD_TYPE.get(card.card_type)

    primary_metric: str | None = ctx.get("primary_metric")
    if not primary_metric and card.metrics_json:
        first = card.metrics_json[0]
        if isinstance(first, dict):
            name = first.get("name")
            value = first.get("value")
            unit = first.get("unit") or ""
            if name is not None and value is not None:
                primary_metric = f"{value}{(' ' + unit) if unit else ''}".strip()

    surfaces_raw = ctx.get("surfaces") or []
    surfaces = [str(s) for s in surfaces_raw] if isinstance(surfaces_raw, list) else []

    return IODisplayConfig(
        layout=str(layout),
        primary_metric=primary_metric,
        chart_type=str(chart_type) if chart_type else None,
        cta=str(cta) if cta else None,
        surfaces=surfaces,
    )


def _to_io_metrics(card: IntelligenceCard) -> list[IOMetric]:
    metrics: list[IOMetric] = []
    for entry in card.metrics_json or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if name is None:
            continue
        metrics.append(
            IOMetric(
                name=str(name),
                value=value,
                unit=str(entry["unit"]) if entry.get("unit") not in (None, "") else None,
            )
        )
    return metrics


def _event_brief(event: CompanyEvent | None, period: FinancialPeriod | None) -> EventBriefV1 | None:
    if not event:
        return None
    return EventBriefV1(
        event_id=event.event_id,
        event_type=event.event_type,
        event_title=event.event_title,
        event_date=event.event_date,
        period=period_brief(period),
        source_exchange=event.source_exchange.value if event.source_exchange else None,
        consolidation=event.consolidation,
        overall_signal=event.overall_signal,
        overall_severity=event.overall_severity,
        overall_confidence=float(event.overall_confidence) if event.overall_confidence is not None else None,
        summary_text=event.summary_text,
    )


def _signal_brief(
    sig: GeneratedSignal | None,
    sd: SignalDefinition | None,
    period: FinancialPeriod | None,
) -> SignalBriefV1 | None:
    if not sig or not sd:
        return None
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
        period=period_brief(period),
        event_id=sig.event_id,
        document_id=sig.document_id,
        created_at=sig.created_at,
    )


def _evidence_items(rows: Iterable[CardEvidence]) -> list[EvidenceItem]:
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


def build_intelligence_object(
    db: Session,
    card: IntelligenceCard,
    company: Company,
    period: FinancialPeriod | None,
    event: CompanyEvent | None,
    document: SourceDocument | None,
) -> IntelligenceObject:
    """Stitch the full intelligence object together.

    The router is expected to have already joined the row tuple via the standard
    `IntelligenceCard → Company → FinancialPeriod → CompanyEvent → SourceDocument`
    shape (see `routers/cards.list_cards`). Heavier enrichment (metric
    comparisons, signal definition lookup, evidence) happens here so individual
    routers stay small.
    """

    signal_def: SignalDefinition | None = None
    signal_row: GeneratedSignal | None = None
    if card.signal_id is not None:
        signal_join = db.execute(
            select(GeneratedSignal, SignalDefinition)
            .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
            .where(GeneratedSignal.signal_id == card.signal_id)
        ).first()
        if signal_join:
            signal_row, signal_def = signal_join

    evidence_rows = db.scalars(
        select(CardEvidence)
        .where(CardEvidence.card_id == card.card_id)
        .order_by(CardEvidence.card_evidence_id)
    ).all()

    metric_comparisons = load_metric_comparisons(
        db,
        card.company_id,
        period.period_id if period else None,
        card.event_id,
        card.card_type,
    )
    trend_sparklines = load_trend_sparklines(
        db, card.company_id, period.period_id if period else None
    )
    concern_heatmap = (
        load_concall_heatmap(db, card.event_id) if should_show_concall(card, event) else []
    )

    severity = card.severity

    return IntelligenceObject(
        intelligence_object_id=card.card_id,
        object_type=card.card_type,
        title=card.headline,
        subtitle=card.one_line_summary,
        status=card.signal_direction,
        importance_score=_normalize_importance(float(card.card_priority) if card.card_priority is not None else None),
        severity=severity,
        confidence=card.confidence_level,
        confidence_score=float(card.confidence_score) if card.confidence_score is not None else None,
        time_horizon=_derive_time_horizon(card.card_type, severity),
        investor_relevance=_derive_investor_relevance(card.card_type, card.signal_direction),
        insight=card.detailed_explanation,
        investor_question=card.investor_question,
        watch_next=card.watch_next,
        company=company_brief(company),
        period=period_brief(period),
        event=_event_brief(event, period),
        signal=_signal_brief(signal_row, signal_def, period),
        metrics=_to_io_metrics(card),
        metric_comparisons=metric_comparisons,
        trend_sparklines=trend_sparklines,
        concern_heatmap=concern_heatmap,
        calculation=card.calculations_json or {},
        evidence=_evidence_items(evidence_rows),
        display=_display_for(card),
        suggested_actions=_derive_suggested_actions(card.card_type, card.signal_direction, severity),
        source_label=build_source_label(period, event, document),
        document_id=card.document_id,
        event_main_issue=event.main_issue if event else None,
        event_summary=event.summary_text if event else None,
        created_at=card.created_at,
    )


def build_intelligence_object_brief(
    card: IntelligenceCard,
    company: Company,
    period: FinancialPeriod | None,
    event: CompanyEvent | None,
) -> IntelligenceObjectBrief:
    """Lighter projection used by feeds and portfolio alerts.

    Skips the heavy joins on signal definitions and evidence so list endpoints
    stay fast. Consumers that need the full payload should call the by-id
    endpoint, which goes through `build_intelligence_object`.
    """

    primary_metric: str | None = None
    if card.metrics_json:
        first = card.metrics_json[0]
        if isinstance(first, dict):
            value = first.get("value")
            unit = first.get("unit") or ""
            if value is not None:
                primary_metric = f"{value}{(' ' + unit) if unit else ''}".strip()

    return IntelligenceObjectBrief(
        intelligence_object_id=card.card_id,
        object_type=card.card_type,
        title=card.headline,
        subtitle=card.one_line_summary,
        status=card.signal_direction,
        importance_score=_normalize_importance(
            float(card.card_priority) if card.card_priority is not None else None
        ),
        severity=card.severity,
        confidence=card.confidence_level,
        confidence_score=float(card.confidence_score) if card.confidence_score is not None else None,
        time_horizon=_derive_time_horizon(card.card_type, card.severity),
        company=company_brief(company),
        period=period_brief(period),
        event_id=event.event_id if event else None,
        event_title=event.event_title if event else None,
        event_date=event.event_date.isoformat() if event else None,
        signal_id=card.signal_id,
        primary_metric=primary_metric,
        investor_relevance=_derive_investor_relevance(card.card_type, card.signal_direction),
        created_at=card.created_at,
    )


# Re-export to keep the import surface small for callers that just need the
# concall helper alongside the builder (e.g. routers/v1/intelligence_objects).
__all__ = [
    "build_intelligence_object",
    "build_intelligence_object_brief",
    "load_concall_heatmap",
    "load_trend_sparklines",
    "should_show_concall",
]
