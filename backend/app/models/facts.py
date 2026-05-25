from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
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
from app.db.enums import (
    AuditStatus,
    ConfidenceLevel,
    ConsolidationType,
    SeverityLevel,
    SignalDirection,
    StatementType,
)


class FinancialLineItemDefinition(Base):
    __tablename__ = "financial_line_item_definitions"

    line_item_def_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    normalized_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    statement_type: Mapped[StatementType] = mapped_column(Enum(StatementType, name="statement_type"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_standard: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractedValue(Base):
    __tablename__ = "extracted_values"

    extracted_value_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    extraction_job_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_jobs.extraction_job_id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.document_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))

    raw_label: Mapped[str] = mapped_column(String, nullable=False)
    normalized_label: Mapped[str | None] = mapped_column(String)

    raw_value: Mapped[str | None] = mapped_column(String)
    numeric_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    date_value: Mapped[date | None] = mapped_column(Date)

    unit: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="INR")

    statement_type: Mapped[StatementType | None] = mapped_column(Enum(StatementType, name="statement_type"))
    table_name: Mapped[str | None] = mapped_column(String)
    section_name: Mapped[str | None] = mapped_column(String)

    page_number: Mapped[int | None] = mapped_column(Integer)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB)
    source_text: Mapped[str | None] = mapped_column(Text)

    # Period-column label inferred by the extractor (e.g. "Q3 FY24-25",
    # "9M FY24-25", "YTD"). Used by the comparator-integrity check in
    # ``services/pipeline/inputs.py`` so a YTD column never gets used as a
    # PQ/PY denominator. NULL means "unknown" (current quarter is the
    # default).
    column_label: Mapped[str | None] = mapped_column(String)

    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    confidence_level: Mapped[ConfidenceLevel | None] = mapped_column(Enum(ConfidenceLevel, name="confidence_level"))

    is_normalized: Mapped[bool] = mapped_column(Boolean, default=False)
    is_corrected: Mapped[bool] = mapped_column(Boolean, default=False)

    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialStatementFact(Base):
    __tablename__ = "financial_statement_facts"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "period_id",
            "line_item_def_id",
            "consolidation",
            "period_value_type",
            name="uq_financial_facts",
        ),
    )

    fact_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("financial_periods.period_id"), nullable=False)
    line_item_def_id: Mapped[int] = mapped_column(
        ForeignKey("financial_line_item_definitions.line_item_def_id"), nullable=False
    )

    consolidation: Mapped[ConsolidationType] = mapped_column(
        Enum(ConsolidationType, name="consolidation_type"), nullable=False
    )
    audit_status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status"), default=AuditStatus.UNKNOWN
    )

    value: Mapped[float] = mapped_column(Numeric(24, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String, default="crore")
    currency: Mapped[str] = mapped_column(String, default="INR")

    period_value_type: Mapped[str] = mapped_column(String, default="CURRENT")

    # Column the value came from in the source filing ("Q3 FY24-25", "9M",
    # "YTD"). Inherited from ``ExtractedValue.column_label`` during
    # normalization. The comparator-integrity check in
    # ``services/pipeline/inputs.py`` skips PQ/PY lookups whose column is
    # a YTD/9M/H1 aggregate so QoQ never divides by a year-to-date number.
    column_label: Mapped[str | None] = mapped_column(String)

    source_extracted_value_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_values.extracted_value_id"))
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CompanySegment(Base):
    __tablename__ = "company_segments"
    __table_args__ = (UniqueConstraint("company_id", "normalized_segment_name", "segment_type", name="uq_segments"),)

    segment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    segment_name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_segment_name: Mapped[str | None] = mapped_column(String)
    segment_type: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SegmentFact(Base):
    __tablename__ = "segment_facts"
    __table_args__ = (
        UniqueConstraint("company_id", "period_id", "segment_id", "consolidation", name="uq_segment_facts"),
    )

    segment_fact_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("financial_periods.period_id"), nullable=False)
    segment_id: Mapped[int] = mapped_column(ForeignKey("company_segments.segment_id"), nullable=False)

    consolidation: Mapped[ConsolidationType] = mapped_column(
        Enum(ConsolidationType, name="consolidation_type"), nullable=False
    )

    segment_revenue: Mapped[float | None] = mapped_column(Numeric(24, 6))
    segment_profit: Mapped[float | None] = mapped_column(Numeric(24, 6))
    segment_assets: Mapped[float | None] = mapped_column(Numeric(24, 6))
    segment_liabilities: Mapped[float | None] = mapped_column(Numeric(24, 6))

    unit: Mapped[str] = mapped_column(String, default="crore")
    currency: Mapped[str] = mapped_column(String, default="INR")

    source_extracted_value_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_values.extracted_value_id"))
    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConcallSpeaker(Base):
    __tablename__ = "concall_speakers"

    speaker_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.company_id"))
    speaker_name: Mapped[str] = mapped_column(String, nullable=False)
    speaker_role: Mapped[str | None] = mapped_column(String)
    organization: Mapped[str | None] = mapped_column(String)
    speaker_type: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    chunk_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.document_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    speaker_id: Mapped[int | None] = mapped_column(ForeignKey("concall_speakers.speaker_id"))

    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False)
    section_type: Mapped[str | None] = mapped_column(String)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConcallFact(Base):
    __tablename__ = "concall_facts"

    concall_fact_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))

    fact_type: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str | None] = mapped_column(String)
    extracted_claim: Mapped[str] = mapped_column(Text, nullable=False)

    direction: Mapped[SignalDirection | None] = mapped_column(Enum(SignalDirection, name="signal_direction"))
    severity: Mapped[SeverityLevel | None] = mapped_column(Enum(SeverityLevel, name="severity_level"))

    numeric_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    unit: Mapped[str | None] = mapped_column(String)
    target_period: Mapped[str | None] = mapped_column(String)

    speaker_id: Mapped[int | None] = mapped_column(ForeignKey("concall_speakers.speaker_id"))
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("transcript_chunks.chunk_id"))

    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalystQuestion(Base):
    __tablename__ = "analyst_questions"

    question_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))

    analyst_speaker_id: Mapped[int | None] = mapped_column(ForeignKey("concall_speakers.speaker_id"))
    management_speaker_id: Mapped[int | None] = mapped_column(ForeignKey("concall_speakers.speaker_id"))

    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text)

    topic: Mapped[str | None] = mapped_column(String)
    subtopic: Mapped[str | None] = mapped_column(String)

    evasiveness_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    directness_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    concern_score: Mapped[float | None] = mapped_column(Numeric(5, 2))

    question_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("transcript_chunks.chunk_id"))
    answer_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("transcript_chunks.chunk_id"))

    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PresentationFact(Base):
    __tablename__ = "presentation_facts"

    presentation_fact_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))

    fact_type: Mapped[str] = mapped_column(String, nullable=False)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String)

    target_value: Mapped[float | None] = mapped_column(Numeric(24, 6))
    target_period: Mapped[str | None] = mapped_column(String)

    page_number: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    bounding_box: Mapped[dict | None] = mapped_column(JSONB)

    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnnouncementFact(Base):
    __tablename__ = "announcement_facts"

    announcement_fact_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.document_id"))

    announcement_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    amount: Mapped[float | None] = mapped_column(Numeric(24, 6))
    unit: Mapped[str] = mapped_column(String, default="crore")
    currency: Mapped[str] = mapped_column(String, default="INR")

    customer_name: Mapped[str | None] = mapped_column(String)
    counterparty_name: Mapped[str | None] = mapped_column(String)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    execution_months: Mapped[int | None] = mapped_column(Integer)

    source_text: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)

    confidence_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
