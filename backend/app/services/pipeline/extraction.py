"""Stage 1 of the pipeline: pages → `ExtractedValue` rows.

This is the only stage that talks to the LLM. Everything below it operates on
plain SQL rows, so the rest of the pipeline is provider-agnostic.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.enums import ConfidenceLevel, ExtractionStatus
from app.models.events import DocumentPage, ExtractionJob, SourceDocument
from app.models.facts import ExtractedValue, FinancialStatementFact, SegmentFact
from app.models.intelligence import CardEvidence
from app.models.review import ReviewQueue
from app.services.pipeline.llm import ExtractionResult, LLMProvider


def run_extraction(
    db: Session,
    *,
    document: SourceDocument,
    job: ExtractionJob,
    provider: LLMProvider,
) -> ExtractionResult:
    """Call the LLM provider and persist the structured output."""
    pages = _load_pages(db, document.document_id)
    if not pages:
        result = ExtractionResult(items=[], model_name=provider.name, overall_confidence=0.0)
        result.notes.append("Document has no parsed pages — extraction skipped.")
        return result

    job.status = ExtractionStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    job.model_name = provider.name
    db.flush()

    result = provider.extract_financial_facts(
        pages=pages, document_title=document.document_title
    )

    # Wipe any previous extraction for this document/job — re-runs are allowed.
    ev_ids = list(
        db.scalars(
            select(ExtractedValue.extracted_value_id).where(
                ExtractedValue.document_id == document.document_id
            )
        ).all()
    )
    if ev_ids:
        # Downstream stages run after this delete; clear FK pointers from a prior run.
        db.execute(
            update(FinancialStatementFact)
            .where(FinancialStatementFact.source_extracted_value_id.in_(ev_ids))
            .values(source_extracted_value_id=None)
        )
        db.execute(
            update(SegmentFact)
            .where(SegmentFact.source_extracted_value_id.in_(ev_ids))
            .values(source_extracted_value_id=None)
        )
        db.execute(
            update(CardEvidence)
            .where(CardEvidence.extracted_value_id.in_(ev_ids))
            .values(extracted_value_id=None)
        )
        db.execute(
            update(ReviewQueue)
            .where(ReviewQueue.extracted_value_id.in_(ev_ids))
            .values(extracted_value_id=None)
        )
    db.execute(
        delete(ExtractedValue).where(ExtractedValue.document_id == document.document_id)
    )

    for item in result.items:
        db.add(
            ExtractedValue(
                extraction_job_id=job.extraction_job_id,
                document_id=document.document_id,
                event_id=document.event_id,
                company_id=document.company_id,
                period_id=document.period_id,
                raw_label=item.raw_label,
                normalized_label=item.normalized_code,
                raw_value=str(item.value),
                numeric_value=item.value,
                unit=item.unit,
                page_number=item.page_number,
                source_text=item.source_text,
                confidence_score=item.confidence,
                confidence_level=_confidence_to_level(item.confidence),
                is_normalized=True,
            )
        )

    job.input_tokens = result.input_tokens
    job.output_tokens = result.output_tokens
    job.cost_usd = result.cost_usd
    job.meta = {
        **(job.meta or {}),
        "extracted_count": len(result.items),
        "overall_confidence": result.overall_confidence,
        "notes": result.notes,
    }

    document.extraction_confidence = result.overall_confidence
    document.values_extracted = len(result.items)

    # Sessions use autoflush=False (see app/db/session.py). Make every stage
    # see the rows we just wrote without relying on the next query to flush.
    db.flush()

    return result


def _load_pages(db: Session, document_id: int) -> list[tuple[int, str]]:
    rows = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    return [(r.page_number, r.page_text or "") for r in rows]


def _confidence_to_level(score: float) -> ConfidenceLevel:
    if score >= 85:
        return ConfidenceLevel.HIGH
    if score >= 65:
        return ConfidenceLevel.MEDIUM
    if score >= 40:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.NEEDS_REVIEW
