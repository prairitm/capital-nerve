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
    evidence: list[EvidenceItem] = []
    display: IODisplayConfig
    suggested_actions: list[str] = []
    source_label: str | None = None
    document_id: int | None = None
    event_main_issue: str | None = None
    event_summary: str | None = None
    created_at: datetime
