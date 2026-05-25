from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import ConfidenceLevel, SeverityLevel, SignalDirection


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"

    metric_def_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_category: Mapped[str] = mapped_column(String, nullable=False)

    formula_text: Mapped[str | None] = mapped_column(Text)
    formula_sql: Mapped[str | None] = mapped_column(Text)

    inputs_json: Mapped[list] = mapped_column(JSONB, default=list)
    dependencies_json: Mapped[list] = mapped_column(JSONB, default=list)

    unit: Mapped[str | None] = mapped_column(String)
    is_percentage: Mapped[bool] = mapped_column(Boolean, default=False)
    is_bps: Mapped[bool] = mapped_column(Boolean, default=False)

    # Plausible (min, max) bounds for the computed value. NULL means
    # unbounded. Used by the metrics stage to quarantine impossibly large
    # margin / growth values that almost always indicate a unit / period
    # mismatch upstream — see ``services/pipeline/metrics.py``.
    validation_min: Mapped[float | None] = mapped_column(Numeric(24, 6))
    validation_max: Mapped[float | None] = mapped_column(Numeric(24, 6))

    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalculatedMetric(Base):
    __tablename__ = "calculated_metrics"
    __table_args__ = (
        UniqueConstraint("company_id", "period_id", "metric_def_id", "comparison_type", name="uq_calculated_metrics"),
    )

    metric_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("financial_periods.period_id"), nullable=False)
    metric_def_id: Mapped[int] = mapped_column(ForeignKey("metric_definitions.metric_def_id"), nullable=False)

    metric_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    metric_text_value: Mapped[str | None] = mapped_column(Text)

    comparison_period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))
    comparison_type: Mapped[str | None] = mapped_column(String)

    change_absolute: Mapped[float | None] = mapped_column(Numeric(24, 6))
    change_percent: Mapped[float | None] = mapped_column(Numeric(12, 4))
    change_bps: Mapped[float | None] = mapped_column(Numeric(12, 4))

    unit: Mapped[str | None] = mapped_column(String)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    input_values: Mapped[dict] = mapped_column(JSONB, default=dict)
    calculation_steps: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Quarantine flag for metric values outside the metric definition's
    # plausible (min, max) bounds. Quarantined metrics are persisted for the
    # admin Review Queue but never feed signals/cards.
    is_quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    quarantine_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalDefinition(Base):
    __tablename__ = "signal_definitions"

    signal_def_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    signal_name: Mapped[str] = mapped_column(String, nullable=False)
    signal_category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rule_text: Mapped[str | None] = mapped_column(Text)
    rule_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    default_direction: Mapped[SignalDirection | None] = mapped_column(Enum(SignalDirection, name="signal_direction"))
    default_severity: Mapped[SeverityLevel | None] = mapped_column(Enum(SeverityLevel, name="severity_level"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeneratedSignal(Base):
    __tablename__ = "generated_signals"

    signal_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))
    signal_def_id: Mapped[int] = mapped_column(ForeignKey("signal_definitions.signal_def_id"), nullable=False)

    signal_direction: Mapped[SignalDirection] = mapped_column(
        Enum(SignalDirection, name="signal_direction"), nullable=False
    )
    severity: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel, name="severity_level"), nullable=False)

    signal_score: Mapped[float | None] = mapped_column(Numeric(8, 2))
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    headline: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)

    primary_metric_id: Mapped[int | None] = mapped_column(ForeignKey("calculated_metrics.metric_id"))

    metric_refs: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)

    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntelligenceCard(Base):
    __tablename__ = "intelligence_cards"

    card_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("generated_signals.signal_id"))

    card_type: Mapped[str] = mapped_column(String, nullable=False)
    card_priority: Mapped[float] = mapped_column(Numeric(8, 2), default=0)

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    one_line_summary: Mapped[str] = mapped_column(Text, nullable=False)
    detailed_explanation: Mapped[str | None] = mapped_column(Text)

    signal_direction: Mapped[SignalDirection | None] = mapped_column(Enum(SignalDirection, name="signal_direction"))
    severity: Mapped[SeverityLevel | None] = mapped_column(Enum(SeverityLevel, name="severity_level"))

    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    confidence_level: Mapped[ConfidenceLevel | None] = mapped_column(Enum(ConfidenceLevel, name="confidence_level"))

    investor_question: Mapped[str | None] = mapped_column(Text)
    watch_next: Mapped[str | None] = mapped_column(Text)
    action_label: Mapped[str | None] = mapped_column(String)

    metrics_json: Mapped[list] = mapped_column(JSONB, default=list)
    calculations_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_json: Mapped[list] = mapped_column(JSONB, default=list)

    display_context: Mapped[dict] = mapped_column(JSONB, default=dict)

    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CardEvidence(Base):
    __tablename__ = "card_evidence"

    card_evidence_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("intelligence_cards.card_id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    extracted_value_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_values.extracted_value_id"))
    metric_id: Mapped[int | None] = mapped_column(ForeignKey("calculated_metrics.metric_id"))

    evidence_type: Mapped[str] = mapped_column(String, nullable=False)
    evidence_label: Mapped[str | None] = mapped_column(String)
    evidence_value: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB)
    calculation_text: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
