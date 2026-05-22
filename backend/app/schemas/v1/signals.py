"""Signal-level v1 schemas — interpretation layer."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.enums import SeverityLevel, SignalDirection
from app.schemas.common import (
    CardBrief,
    CardMetricComparison,
    CompanyBrief,
    DocumentBrief,
    EvidenceItem,
    FinancialTrend,
    PeriodBrief,
)


class SignalCalculation(BaseModel):
    """Structured calculation behind a signal (input metric, operator, threshold, current)."""

    metric_code: str | None = None
    operator: str | None = None
    threshold: float | None = None
    current_value: float | None = None
    previous_value: float | None = None
    change_percent: float | None = None
    change_bps: float | None = None
    unit: str | None = None
    rule_text: str | None = None


class SignalRuleLeaf(BaseModel):
    """One metric inside a (possibly compound) signal rule."""

    metric_code: str
    metric_name: str
    current_value: float | None = None
    unit: str = ""
    operator: str | None = None
    threshold: float | None = None
    passed: bool | None = None
    rule_text: str | None = None


class SignalPrimaryMetric(BaseModel):
    metric_code: str
    metric_name: str
    value: float | None
    unit: str


class SignalEventBrief(BaseModel):
    """Lightweight event header surfaced on the signal detail page."""

    event_id: int
    event_type: str
    event_title: str
    event_date: str
    summary_text: str | None = None
    main_issue: str | None = None
    watch_next: str | None = None
    overall_signal: SignalDirection | None = None
    overall_severity: SeverityLevel | None = None
    overall_confidence: float | None = None


class SignalRelatedBrief(BaseModel):
    signal_id: int
    signal_code: str
    signal_name: str
    signal_category: str
    direction: SignalDirection
    severity: SeverityLevel
    confidence_score: float | None = None
    signal_score: float | None = None
    headline: str | None = None


class SignalBriefV1(BaseModel):
    """Compact signal row — embedded inside `IntelligenceObject.signal` and
    returned by the cross-company signal feed."""

    signal_id: int
    signal_code: str
    signal_name: str
    signal_category: str
    direction: SignalDirection
    severity: SeverityLevel
    confidence_score: float | None = None
    signal_score: float | None = None
    headline: str | None = None
    explanation: str | None = None
    company: CompanyBrief | None = None
    period: PeriodBrief | None = None
    event_id: int | None = None
    document_id: int | None = None
    created_at: datetime | None = None


class SignalDetailV1(SignalBriefV1):
    """Full signal detail.

    Aggregates the rule explanation, primary metric, comparisons, sparklines,
    related cards and signals, evidence, event and document context the
    signal-detail page renders.
    """

    description: str | None = None
    rule_text: str | None = None
    rule_summary: str | None = None
    rule_json: dict[str, Any] = {}
    rule_metric_codes: list[str] = []
    rule_leaves: list[SignalRuleLeaf] = []
    calculation: SignalCalculation | None = None
    primary_metric: SignalPrimaryMetric | None = None
    trigger_metric: CardMetricComparison | None = None
    metric_refs: list[Any] = []
    evidence_refs: list[Any] = []
    metric_comparisons: list[CardMetricComparison] = []
    trend_sparklines: list[FinancialTrend] = []
    related_cards: list[CardBrief] = []
    related_signals: list[SignalRelatedBrief] = []
    evidence: list[EvidenceItem] = []
    event: SignalEventBrief | None = None
    document: DocumentBrief | None = None
