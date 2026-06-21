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
from app.models.facts import ExtractedValue
from app.models.intelligence import (
    CalculatedMetric,
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
    MetricDefinition,
    SignalDefinition,
)
from app.models.master import Company, FinancialPeriod
from app.routers._helpers import build_source_label, company_brief, period_brief
from app.schemas.common import EvidenceItem
from app.schemas.v1.events import EventBriefV1
from app.schemas.v1.intelligence_object import (
    CalculationChain,
    CalculationChainInput,
    CalculationChainMetric,
    CalculationChainSignal,
    IntelligenceObject,
    IntelligenceObjectBrief,
    IODisplayConfig,
    IOMetric,
    IOTriggerMetricBrief,
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


def _metric_source_kind(entry: dict) -> str | None:
    explicit = entry.get("source_kind")
    if explicit in ("extracted", "computed"):
        return explicit
    derivation = entry.get("derivation")
    if derivation == "raw":
        return "extracted"
    if derivation in ("yoy", "qoq", "formula", "alias", "margin"):
        return "computed"
    return None


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
                source_kind=_metric_source_kind(entry),
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


def _build_calculation_chain(
    db: Session,
    card: IntelligenceCard,
    signal_row: GeneratedSignal | None,
    signal_def: SignalDefinition | None,
) -> CalculationChain | None:
    """Assemble the full Signal → Metric → Facts explainability chain.

    Returns ``None`` for summary cards (`result_verdict`) and any card that
    has no underlying signal — those render through the existing metrics
    list rather than the calculation panel. The frontend
    `CalculationChainPanel` reads this structure directly.
    """
    cm: CalculatedMetric | None = None
    md: MetricDefinition | None = None
    if signal_row and signal_row.primary_metric_id:
        cm = db.get(CalculatedMetric, signal_row.primary_metric_id)
        if cm is not None and cm.metric_def_id is not None:
            md = db.get(MetricDefinition, cm.metric_def_id)

    if not signal_def and not cm:
        return None

    signal_chain: CalculationChainSignal | None = None
    if signal_def is not None:
        # First leaf from the signal's metric_refs drives the "fired at" copy.
        fired_value: float | None = None
        fired_unit: str | None = None
        threshold: float | None = None
        operator: str | None = None
        metric_ref_code: str | None = None
        refs = list(signal_row.metric_refs or []) if signal_row else []
        if refs:
            head = refs[0] if isinstance(refs[0], dict) else None
            if head:
                fired_value = (
                    float(head["value"]) if head.get("value") is not None else None
                )
                fired_unit = head.get("unit")
                threshold = (
                    float(head["threshold"])
                    if head.get("threshold") is not None
                    else None
                )
                operator = head.get("op")
                metric_ref_code = head.get("metric_ref")
        signal_chain = CalculationChainSignal(
            code=signal_def.signal_code,
            name=signal_def.signal_name,
            category=signal_def.signal_category,
            rule_text=signal_def.rule_text,
            direction=signal_row.signal_direction if signal_row else signal_def.default_direction,
            severity=signal_row.severity if signal_row else signal_def.default_severity,
            fired_value=fired_value,
            fired_unit=fired_unit,
            threshold=threshold,
            operator=operator,
            metric_ref=metric_ref_code,
        )

    metric_chain: CalculationChainMetric | None = None
    if cm is not None:
        inputs = _build_calculation_chain_inputs(db, cm, md, card.document_id)
        metric_chain = CalculationChainMetric(
            code=md.metric_code if md else None,
            name=md.metric_name if md else None,
            formula_text=md.formula_text if md else None,
            value=float(cm.metric_value) if cm.metric_value is not None else None,
            unit=cm.unit or (md.unit if md else None),
            inputs=inputs,
            is_quarantined=bool(cm.is_quarantined),
            quarantine_reason=cm.quarantine_reason,
        )

    if not signal_chain and not metric_chain:
        return None

    return CalculationChain(signal=signal_chain, metric=metric_chain)


def _build_calculation_chain_inputs(
    db: Session,
    cm: CalculatedMetric,
    md: MetricDefinition | None,
    document_id: int | None,
) -> list[CalculationChainInput]:
    """Resolve every input variable used by the metric into a source-anchored row.

    `CalculatedMetric.input_values` carries the runtime values keyed by the
    formula's local variable name. `MetricDefinition.inputs_json` carries the
    declarative `{name, code, scope, kind}` for each variable. We zip the two
    and then look up the matching `ExtractedValue` row (current-period facts
    only — prior-period sources live in a different document and won't have
    a quote in this filing) so the panel can show the underlying quote +
    page number.
    """
    runtime: dict = dict(cm.input_values or {})
    decls = list((md.inputs_json or []) if md else [])
    decl_by_name = {
        d.get("name"): d for d in decls if isinstance(d, dict) and d.get("name")
    }
    extracted_by_code = _extracted_lookup(db, document_id) if document_id else {}

    out: list[CalculationChainInput] = []
    for name, value in runtime.items():
        decl = decl_by_name.get(name) or {}
        code = decl.get("code")
        scope = (decl.get("scope") or "CURRENT").upper()
        kind = (decl.get("kind") or "fact").lower()
        page_number: int | None = None
        source_text: str | None = None
        doc_id: int | None = None
        unit: str | None = None
        if kind == "fact" and scope == "CURRENT" and code:
            ev = extracted_by_code.get(code)
            if ev is not None:
                page_number = ev.page_number
                source_text = ev.source_text
                doc_id = ev.document_id
                unit = ev.unit
        out.append(
            CalculationChainInput(
                formula_name=name,
                code=code,
                scope=scope,
                kind=kind,
                value=float(value) if value is not None else None,
                unit=unit,
                document_id=doc_id,
                page_number=page_number,
                source_text=source_text,
            )
        )
    return out


def _extracted_lookup(db: Session, document_id: int) -> dict[str, ExtractedValue]:
    rows = (
        db.query(ExtractedValue)
        .filter(ExtractedValue.document_id == document_id)
        .all()
    )
    return {ev.normalized_label or ev.raw_label: ev for ev in rows}


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

    calculation_chain = _build_calculation_chain(db, card, signal_row, signal_def)

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
        calculation_chain=calculation_chain,
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
    document: SourceDocument | None = None,
    db: Session | None = None,
) -> IntelligenceObjectBrief:
    """Lighter projection used by feeds and portfolio alerts.

    Skips the heavy joins on signal definitions and evidence so list endpoints
    stay fast. Consumers that need the full payload should call the by-id
    endpoint, which goes through `build_intelligence_object`.

    `document` is optional because portfolio_monitor's hot path does not load
    `SourceDocument`. When omitted, `source_label` falls back to the period /
    event label resolved by `build_source_label` and `document_id` comes from
    `card.document_id` so the feed-row PDF jump still works.

    ``db`` is optional: when supplied, we attach a compact ``trigger_metric``
    (formula, unit, source-page link, validation status) so the feed row can
    render the analyst-trust strip without round-tripping to the by-id
    endpoint. Callers that already hold a Session should pass it.
    """

    primary_metric: str | None = None
    if card.metrics_json:
        first = card.metrics_json[0]
        if isinstance(first, dict):
            value = first.get("value")
            unit = first.get("unit") or ""
            if value is not None:
                primary_metric = f"{value}{(' ' + unit) if unit else ''}".strip()

    trigger_metric = _build_trigger_metric_brief(db, card) if db is not None else None

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
        event_type=event.event_type if event else None,
        event_title=event.event_title if event else None,
        event_date=event.event_date.isoformat() if event else None,
        signal_id=card.signal_id,
        primary_metric=primary_metric,
        trigger_metric=trigger_metric,
        investor_relevance=_derive_investor_relevance(card.card_type, card.signal_direction),
        source_label=build_source_label(period, event, document),
        document_id=card.document_id,
        created_at=card.created_at,
    )


def _build_trigger_metric_brief(
    db: Session | None, card: IntelligenceCard
) -> IOTriggerMetricBrief | None:
    """Compact metric provenance for the feed row.

    Reads the card's primary metric, its definition, and the first
    CURRENT-period extracted value backing one of its formula inputs. One
    metric-definition lookup + one extracted-value lookup per row keeps the
    feed endpoint cheap.
    """
    if db is None:
        return None
    metrics_json = list(card.metrics_json or [])
    if not metrics_json or not isinstance(metrics_json[0], dict):
        return None
    metric_entry = metrics_json[0]
    name = metric_entry.get("name") or None
    value_display = (
        _format_brief_value(metric_entry.get("value"), metric_entry.get("unit"))
        if metric_entry.get("value") is not None
        else None
    )
    unit = metric_entry.get("unit") or None

    md: MetricDefinition | None = None
    cm: CalculatedMetric | None = None
    if card.signal_id is not None:
        sig = db.get(GeneratedSignal, card.signal_id)
        if sig is not None and sig.primary_metric_id is not None:
            cm = db.get(CalculatedMetric, sig.primary_metric_id)
            if cm is not None and cm.metric_def_id is not None:
                md = db.get(MetricDefinition, cm.metric_def_id)
    if md is None and name:
        md = db.scalar(select(MetricDefinition).where(MetricDefinition.metric_name == name))

    code = md.metric_code if md else None
    formula_text = md.formula_text if md else None
    metric_kind = md.metric_kind if md else None
    comparison_type = cm.comparison_type if cm else None
    if comparison_type is None and md is not None:
        # Derive from declared inputs when the metric is a within-period
        # ratio (e.g. pat_margin) that has no comparison_type row stored.
        comparison_type = _infer_comparison_type(md)

    validation_status, validation_reason = _derive_validation_status(cm)

    source_page = _primary_input_page(db, card.document_id, md)

    confidence_score, confidence_band = _confidence_summary(cm)

    if all(
        x is None
        for x in (
            code,
            name,
            value_display,
            formula_text,
            metric_kind,
            comparison_type,
            source_page,
            confidence_band,
        )
    ) and validation_status == "validated":
        return None

    return IOTriggerMetricBrief(
        code=code,
        name=name or (md.metric_name if md else None),
        value_display=value_display,
        unit=unit,
        metric_kind=metric_kind,
        comparison_type=comparison_type,
        formula_text=formula_text,
        source_page=source_page,
        validation_status=validation_status,
        validation_reason=validation_reason,
        confidence_band=confidence_band,
        confidence_score=confidence_score,
    )


def _confidence_summary(
    cm: CalculatedMetric | None,
) -> tuple[float | None, str | None]:
    """Map a ``CalculatedMetric.confidence_score`` onto a coarse band.

    The score on ``calculated_metrics`` is the aggregate of the input
    extraction confidences (see ``services/pipeline/metrics.py``). Bands
    follow the same thresholds the UI uses for card-level confidence:
    high ≥ 80, medium ≥ 60, low otherwise.
    """
    if cm is None:
        return None, None
    raw = getattr(cm, "confidence_score", None)
    if raw is None:
        return None, None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None, None
    if score >= 80.0:
        band = "high"
    elif score >= 60.0:
        band = "medium"
    else:
        band = "low"
    return score, band


def _format_brief_value(value, unit: str | None) -> str | None:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    u = (unit or "").strip()
    if u == "%":
        return f"{val:.1f}%"
    if u == "bps":
        return f"{val:+.0f} bps"
    if u == "x":
        return f"{val:.2f}x"
    if u == "pp":
        return f"{val:+.1f} pp"
    if u == "score":
        return f"{val:.0f} / 100"
    return f"{val:.2f}{(' ' + u) if u else ''}"


def _derive_validation_status(
    cm: CalculatedMetric | None,
) -> tuple[str, str | None]:
    if cm is None:
        return "validated", None
    if getattr(cm, "is_quarantined", False):
        return "quarantined", getattr(cm, "quarantine_reason", None)
    if getattr(cm, "anomaly_flag", False):
        return "anomaly", getattr(cm, "anomaly_reason", None)
    return "validated", None


def _infer_comparison_type(md: MetricDefinition) -> str | None:
    """Pick a short comparator label from the metric's declared inputs.

    Pure metadata read — no DB calls. Codes are intended to be UI-stable so
    the frontend can branch on them without re-stringifying.
    """
    inputs = list(md.inputs_json or [])
    scopes = {(i.get("scope") or "CURRENT").upper() for i in inputs if isinstance(i, dict)}
    kinds = {(i.get("kind") or "fact").lower() for i in inputs if isinstance(i, dict)}
    if "PY" in scopes and "PQ" not in scopes:
        return "yoy"
    if "PQ" in scopes and "PY" not in scopes:
        # PQ over kind=metric describes a true acceleration (pp delta), not
        # a sequential level — surface it distinctly so the UI can render
        # "+5 pp vs prior YoY rate" instead of conflating with QoQ.
        if "metric" in kinds:
            return "pp_vs_prior_yoy"
        return "qoq"
    if "PY" in scopes and "PQ" in scopes:
        return "yoy_and_qoq"
    return None


def _primary_input_page(
    db: Session,
    document_id: int | None,
    md: MetricDefinition | None,
) -> int | None:
    """Return the page of the first CURRENT fact backing the metric formula."""
    if document_id is None or md is None:
        return None
    inputs = list(md.inputs_json or [])
    code: str | None = None
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        scope = (inp.get("scope") or "CURRENT").upper()
        kind = (inp.get("kind") or "fact").lower()
        if scope == "CURRENT" and kind == "fact" and inp.get("code"):
            code = inp["code"]
            break
    if code is None:
        return None
    row = db.execute(
        select(ExtractedValue.page_number).where(
            ExtractedValue.document_id == document_id,
            ExtractedValue.normalized_label == code,
            ExtractedValue.page_number.is_not(None),
        )
        .order_by(ExtractedValue.page_number.asc())
        .limit(1)
    ).scalar()
    return int(row) if row is not None else None


# Re-export to keep the import surface small for callers that just need the
# concall helper alongside the builder (e.g. routers/v1/intelligence_objects).
__all__ = [
    "build_intelligence_object",
    "build_intelligence_object_brief",
    "load_concall_heatmap",
    "load_trend_sparklines",
    "should_show_concall",
]
