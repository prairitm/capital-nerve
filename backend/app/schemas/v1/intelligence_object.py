"""Intelligence Object — the canonical decision-ready payload exposed by v1.

An Intelligence Object is the productized projection of:

    company_events + generated_signals + intelligence_cards + card_evidence

It is everything a downstream consumer (frontend drawer, API client, alert
renderer, LLM tool, Excel plugin) needs to render or reason about a single unit
of intelligence without making additional requests.

The shape mirrors the spec:
    Event = what happened
    Signal = what it means
    Intelligence Object = machine-readable decision package
    Card = one visual representation of an Intelligence Object
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.enums import ConfidenceLevel, EventType, SeverityLevel, SignalDirection
from app.schemas.common import (
    CardMetricComparison,
    CompanyBrief,
    ConcernHeatmapRow,
    EvidenceItem,
    FinancialTrend,
    PeriodBrief,
)
from app.schemas.v1.events import EventBriefV1
from app.schemas.v1.signals import SignalBriefV1


class IOMetric(BaseModel):
    """One metric slot inside the metrics array of an Intelligence Object."""

    name: str
    value: Any
    unit: str | None = None


class IODisplayConfig(BaseModel):
    """Display contract that tells a renderer (UI / API client / Excel / Slack)
    how to surface this object.

    Sourced from `intelligence_cards.display_context` plus a few derived hints
    so consumers can render the same object across channels.
    """

    layout: str = "metric_comparison"
    primary_metric: str | None = None
    chart_type: str | None = None
    cta: str | None = None
    surfaces: list[str] = []


class CalculationChainInput(BaseModel):
    """One input fact feeding the metric formula.

    Carries the page-anchored source for the analyst to verify in one click.
    """

    formula_name: str  # local variable name in the formula (e.g. "revenue")
    code: str | None = None  # normalized line-item code or metric code
    scope: str = "CURRENT"
    kind: str = "fact"  # "fact" | "metric"
    value: float | None = None
    unit: str | None = None
    document_id: int | None = None
    page_number: int | None = None
    source_text: str | None = None


class CalculationChainMetric(BaseModel):
    """The CalculatedMetric layer of the value → metric → signal → card chain."""

    code: str | None = None
    name: str | None = None
    formula_text: str | None = None
    value: float | None = None
    unit: str | None = None
    inputs: list[CalculationChainInput] = []
    is_quarantined: bool = False
    quarantine_reason: str | None = None


class CalculationChainSignal(BaseModel):
    """The GeneratedSignal layer of the chain — what rule fired, with what value."""

    code: str | None = None
    name: str | None = None
    category: str | None = None
    rule_text: str | None = None
    direction: SignalDirection | None = None
    severity: SeverityLevel | None = None
    fired_value: float | None = None
    fired_unit: str | None = None
    threshold: float | None = None
    operator: str | None = None
    metric_ref: str | None = None


class CalculationChain(BaseModel):
    """Full value → metric → signal → card explainability payload.

    Designed so a single panel can render the rule, the formula, every input
    with its source quote + page reference, without joining any other API
    response. NULL fields gracefully degrade for summary cards
    (`result_verdict`) that don't have one underlying signal.
    """

    signal: CalculationChainSignal | None = None
    metric: CalculationChainMetric | None = None


class IntelligenceObjectBrief(BaseModel):
    """Compact intelligence object row for feeds and portfolio alerts."""

    intelligence_object_id: int
    object_type: str
    title: str
    subtitle: str
    status: SignalDirection | None
    importance_score: int
    severity: SeverityLevel | None
    confidence: ConfidenceLevel | None
    confidence_score: float | None = None
    time_horizon: str
    company: CompanyBrief
    period: PeriodBrief | None = None
    event_id: int | None = None
    event_type: EventType | None = None
    event_title: str | None = None
    event_date: str | None = None
    signal_id: int | None = None
    primary_metric: str | None = None
    investor_relevance: list[str] = []
    source_label: str | None = None
    document_id: int | None = None
    created_at: datetime


class IntelligenceObject(BaseModel):
    """The full decision package: event + signal + metrics + evidence + display."""

    intelligence_object_id: int
    object_type: str
    title: str
    subtitle: str
    status: SignalDirection | None
    importance_score: int
    severity: SeverityLevel | None
    confidence: ConfidenceLevel | None
    confidence_score: float | None = None
    time_horizon: str
    investor_relevance: list[str] = []
    insight: str | None = None
    investor_question: str | None = None
    watch_next: str | None = None
    company: CompanyBrief
    period: PeriodBrief | None = None
    event: EventBriefV1 | None = None
    signal: SignalBriefV1 | None = None
    metrics: list[IOMetric] = []
    metric_comparisons: list[CardMetricComparison] = []
    trend_sparklines: list[FinancialTrend] = []
    concern_heatmap: list[ConcernHeatmapRow] = []
    calculation: dict[str, Any] = {}
    calculation_chain: CalculationChain | None = None
    evidence: list[EvidenceItem] = []
    display: IODisplayConfig
    suggested_actions: list[str] = []
    source_label: str | None = None
    document_id: int | None = None
    event_main_issue: str | None = None
    event_summary: str | None = None
    created_at: datetime
