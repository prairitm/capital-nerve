from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.db.enums import (
    ConfidenceLevel,
    DocumentType,
    EventType,
    SeverityLevel,
    SignalDirection,
)


class CompanyBrief(BaseModel):
    company_id: int
    company_name: str
    short_name: str | None
    nse_symbol: str | None
    bse_code: str | None
    sector_name: str | None
    industry: str | None
    market_cap_cr: float | None
    last_price: float | None


class PeriodBrief(BaseModel):
    period_id: int
    display_label: str
    fy_label: str
    quarter: int | None
    period_end_date: date


class CardBrief(BaseModel):
    card_id: int
    signal_id: int | None = None
    card_type: str
    headline: str
    one_line_summary: str
    signal_direction: SignalDirection | None
    severity: SeverityLevel | None
    confidence_score: float | None
    confidence_level: ConfidenceLevel | None
    card_priority: float
    company: CompanyBrief
    period: PeriodBrief | None
    event_id: int | None
    event_type: EventType | None
    event_title: str | None
    event_date: date | None
    metrics_json: list[dict[str, Any]] = []
    watch_next: str | None = None
    source_label: str | None = None
    document_id: int | None = None
    created_at: datetime


class CardMetric(BaseModel):
    name: str
    value: Any
    unit: str | None = None


class EvidenceItem(BaseModel):
    card_evidence_id: int
    document_id: int | None
    evidence_type: str
    evidence_label: str | None
    evidence_value: str | None
    source_text: str | None
    page_number: int | None
    calculation_text: str | None
    confidence_score: float | None


class CardMetricComparison(BaseModel):
    metric_code: str
    metric_name: str
    current_value: float | None
    previous_value: float | None = None
    change_percent: float | None = None
    change_bps: float | None = None
    unit: str = ""
    comparison_type: str | None = None


class ConcernHeatmapRow(BaseModel):
    topic: str
    count: int
    percent: float


class FinancialTrendBand(BaseModel):
    """Historical envelope for one metric across recent quarters."""

    min: float | None = None
    max: float | None = None
    median: float | None = None


class FinancialTrendPoint(BaseModel):
    period_label: str
    period_end_date: date
    value: float | None
    anomaly_flag: bool = False


class FinancialTrend(BaseModel):
    metric_code: str
    metric_name: str
    unit: str
    points: list[FinancialTrendPoint]
    band: FinancialTrendBand | None = None


class CardDetail(CardBrief):
    detailed_explanation: str | None
    investor_question: str | None
    action_label: str | None
    calculations_json: dict[str, Any] = {}
    evidence: list[EvidenceItem] = []
    event_summary: str | None = None
    event_main_issue: str | None = None
    metric_comparisons: list[CardMetricComparison] = []
    trend_sparklines: list[FinancialTrend] = []
    concern_heatmap: list[ConcernHeatmapRow] = []


class TimelineEvent(BaseModel):
    event_id: int
    event_type: EventType
    event_title: str
    event_date: date
    overall_signal: SignalDirection | None
    overall_severity: SeverityLevel | None
    summary_text: str | None
    period: PeriodBrief | None = None


class FinancialSnapshotRow(BaseModel):
    metric: str
    code: str
    current_value: float | None
    previous_value: float | None
    yoy_change_pct: float | None = None
    yoy_change_bps: float | None = None
    unit: str


class DocumentBrief(BaseModel):
    document_id: int
    document_type: DocumentType
    document_title: str
    document_date: date | None
    extraction_confidence: float | None
    values_extracted: int | None
    cards_generated: int | None


class CompanyBadge(BaseModel):
    label: str
    value: str
    tone: str
