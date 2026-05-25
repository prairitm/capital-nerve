from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import (
    AuditStatus,
    ConsolidationType,
    DocumentType,
    EventType,
    ExchangeCode,
    ExtractionStatus,
    SeverityLevel,
    SignalDirection,
)


class CompanyEvent(Base):
    __tablename__ = "company_events"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))

    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"), nullable=False)
    event_title: Mapped[str] = mapped_column(String, nullable=False)

    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_exchange: Mapped[ExchangeCode | None] = mapped_column(Enum(ExchangeCode, name="exchange_code"))
    source_url: Mapped[str | None] = mapped_column(String)

    consolidation: Mapped[ConsolidationType | None] = mapped_column(Enum(ConsolidationType, name="consolidation_type"))
    audit_status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status"), default=AuditStatus.UNKNOWN
    )

    overall_signal: Mapped[SignalDirection | None] = mapped_column(Enum(SignalDirection, name="signal_direction"))
    overall_severity: Mapped[SeverityLevel | None] = mapped_column(Enum(SeverityLevel, name="severity_level"))
    overall_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))

    summary_text: Mapped[str | None] = mapped_column(Text)
    main_issue: Mapped[str | None] = mapped_column(Text)
    watch_next: Mapped[str | None] = mapped_column(Text)

    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourceDocument(Base):
    __tablename__ = "source_documents"

    document_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("company_events.event_id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("financial_periods.period_id"))

    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="document_type"), nullable=False)

    document_title: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String)
    storage_path: Mapped[str | None] = mapped_column(String)
    file_hash: Mapped[str | None] = mapped_column(String, unique=True)

    filing_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_date: Mapped[date | None] = mapped_column(Date)

    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String, default="en")

    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status"), default=ExtractionStatus.PENDING
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    values_extracted: Mapped[int | None] = mapped_column(Integer, default=0)
    cards_generated: Mapped[int | None] = mapped_column(Integer, default=0)

    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_pages"),)

    page_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.document_id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_text: Mapped[str | None] = mapped_column(Text)
    page_markdown: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)
    image_path: Mapped[str | None] = mapped_column(String)
    layout_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentPageEmbedding(Base):
    __tablename__ = "document_page_embeddings"

    page_id: Mapped[int] = mapped_column(
        ForeignKey("document_pages.page_id", ondelete="CASCADE"), primary_key=True
    )
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractionJob(Base):
    __tablename__ = "extraction_jobs"

    extraction_job_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.document_id"), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)

    job_type: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)
    parser_version: Mapped[str | None] = mapped_column(String)

    status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status"), default=ExtractionStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    error_message: Mapped[str | None] = mapped_column(Text)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 4))

    # Determinism + cache (0005_extraction_cache):
    # `request_hash` is the lookup key for replay; `raw_response` is the
    # provider payload we replay against; `llm_*` + `provider_used` are
    # surfaced in the admin Review Queue; `validator_report` collects
    # downstream sanity-check outcomes.
    request_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_response: Mapped[str | None] = mapped_column(Text)
    llm_temperature: Mapped[float | None] = mapped_column(Numeric(3, 2))
    llm_seed: Mapped[int | None] = mapped_column(Integer)
    provider_used: Mapped[str | None] = mapped_column(String)
    validator_report: Mapped[dict] = mapped_column(JSONB, default=dict)

    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
