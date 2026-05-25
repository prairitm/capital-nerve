"""Event-level v1 schemas — raw timeline layer."""

from datetime import date
from typing import Any

from pydantic import BaseModel

from app.db.enums import ConsolidationType, EventType, SeverityLevel, SignalDirection
from app.schemas.common import (
    CardBrief,
    CompanyBrief,
    ConcernHeatmapRow,
    DocumentBrief,
    FinancialSnapshotRow,
    PeriodBrief,
    TimelineEvent,
)
from app.schemas.v1.signals import SignalBriefV1


class EventRawFacts(BaseModel):
    """Subset of `financial_statement_facts` exposed alongside an event."""

    line_item_code: str
    line_item_name: str
    value: float
    unit: str
    period_value_type: str
    consolidation: ConsolidationType | None = None


class EventBriefV1(BaseModel):
    """Compact event row for nested embedding and feeds.

    Used inside `IntelligenceObject.event` and as the list item shape on
    `GET /v1/companies/{symbol}/events`.
    """

    event_id: int
    event_type: EventType
    event_title: str
    event_date: date
    company: CompanyBrief | None = None
    period: PeriodBrief | None = None
    source_exchange: str | None = None
    consolidation: ConsolidationType | None = None
    overall_signal: SignalDirection | None = None
    overall_severity: SeverityLevel | None = None
    overall_confidence: float | None = None
    summary_text: str | None = None
    document_id: int | None = None


class EventIngestionStatus(BaseModel):
    """Ingestion telemetry surfaced on the event detail page."""

    published_card_count: int
    unpublished_card_count: int
    published_signal_count: int
    unpublished_signal_count: int
    document_count: int
    values_extracted_total: int


class AnalystSummaryTheme(BaseModel):
    """One themed sentence in the analyst summary card."""

    label: str  # "Topline", "Margins", "Segments", "Capex / management tone"
    tone: str  # "positive" | "negative" | "mixed" | "neutral"
    sentence: str
    evidence_ids: list[int] = []


class AnalystSummary(BaseModel):
    """Themed quarter / event summary pinned above the cards list.

    Built by [`services/event_summary.build_analyst_summary`] from the fired
    signals + published cards and persisted alongside the `result_verdict`
    card in `intelligence_cards.calculations_json["analyst_summary"]`.
    """

    verdict: str  # "positive" | "negative" | "mixed" | "neutral"
    themes: list[AnalystSummaryTheme] = []


class EventConcallFact(BaseModel):
    fact_type: str
    topic: str | None
    extracted_claim: str
    direction: SignalDirection | None
    severity: SeverityLevel | None
    target_period: str | None
    document_id: int | None
    document_title: str | None
    page_number: int | None


class EventDetailV1(EventBriefV1):
    """Full event detail.

    Aggregates everything the event-detail page needs in a single request:
    summary text, main issue, watch next, raw period facts, cards from this
    event, fired signals, financial snapshot, related events, concall
    commentary, analyst-concern heatmap, ingestion telemetry, and source
    documents.
    """

    main_issue: str | None = None
    watch_next: str | None = None
    audit_status: str | None = None
    raw_facts: list[EventRawFacts] = []
    documents: list[DocumentBrief] = []
    metric_snapshot: dict[str, Any] = {}
    cards: list[CardBrief] = []
    signals: list[SignalBriefV1] = []
    financial_snapshot: list[FinancialSnapshotRow] = []
    related_events: list[TimelineEvent] = []
    concern_heatmap: list[ConcernHeatmapRow] = []
    concall_facts: list[EventConcallFact] = []
    ingestion_status: EventIngestionStatus
    analyst_summary: AnalystSummary | None = None
