"""Ingestion endpoints.

`POST /ingest/upload` (multipart) is the only ingestion path. Upload a PDF
(or markdown / text) with the company + period metadata; the endpoint
persists the file, creates a `CompanyEvent` + `SourceDocument`, queues an
`ExtractionJob(status=PENDING)`, and the worker (see
`app/workers/pipeline_worker.py`) drains the queue.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import (
    AuditStatus,
    ConsolidationType,
    DocumentType,
    EventType,
    ExtractionStatus,
    SeverityLevel,
)
from app.models.events import CompanyEvent, ExtractionJob, SourceDocument
from app.models.master import Company
from app.models.review import ReviewQueue
from app.models.user import AppUser
from app.services.ingest_common import (
    FetchError,
    PeriodResolutionError,
    fetch_document_from_url,
    resolve_period_id,
    suffix_for,
)
from app.services.pipeline.storage import get_storage

router = APIRouter(prefix="/ingest", tags=["ingest"])


# ---------------------------------------------------------------------------
# Multipart upload — the only ingestion path
# ---------------------------------------------------------------------------


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
def ingest_upload(
    company_id: Annotated[int, Form()],
    event_type: Annotated[EventType, Form()],
    document_type: Annotated[DocumentType, Form()],
    document_title: Annotated[str, Form()],
    event_date: Annotated[date | None, Form()] = None,
    period_id: Annotated[int | None, Form()] = None,
    period_label: Annotated[str | None, Form()] = None,
    document_url: Annotated[str | None, Form()] = None,
    file: Annotated[
        UploadFile | None,
        File(description="PDF, markdown, or plain text source document"),
    ] = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict:
    """Accept a file or remote URL, persist bytes to storage, queue the pipeline."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if file is None and not (document_url and document_url.strip()):
        raise HTTPException(
            status_code=400,
            detail="Provide an uploaded file or a document_url to fetch.",
        )

    if file is not None:
        data = file.file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        filename = file.filename
        content_type = file.content_type
        source_url = document_url.strip() if document_url and document_url.strip() else None
    else:
        url = document_url.strip() if document_url else ""
        try:
            data, filename, content_type = fetch_document_from_url(url)
        except FetchError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        source_url = url

    storage = get_storage()
    suffix = suffix_for(filename, content_type)
    stored = storage.put_bytes(data, suffix=suffix)

    try:
        resolved_period = resolve_period_id(
            db, period_id=period_id, period_label=period_label, event_date=event_date
        )
    except PeriodResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if resolved_period is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not resolve a financial period. Use a label like "
                "'Q4 FY2025-26' or 'Q4 FY25-26', or set an event date inside the quarter."
            ),
        )

    event = CompanyEvent(
        company_id=company_id,
        period_id=resolved_period,
        event_type=event_type,
        event_title=document_title,
        event_date=event_date or date.today(),
        filing_date=datetime.now(timezone.utc),
        consolidation=ConsolidationType.CONSOLIDATED,
        audit_status=AuditStatus.UNKNOWN,
        is_published=False,
    )
    db.add(event)
    db.flush()

    # If the same file is uploaded twice we reuse the existing SourceDocument
    # — the unique index on `file_hash` would reject the duplicate insert.
    existing_doc = db.scalar(
        select(SourceDocument).where(SourceDocument.file_hash == stored.file_hash)
    )
    if existing_doc:
        doc = existing_doc
        doc.event_id = event.event_id
        doc.company_id = company_id
        doc.period_id = resolved_period
        doc.document_type = document_type
        doc.document_title = document_title
        doc.source_url = source_url
        doc.extraction_status = ExtractionStatus.PENDING
    else:
        doc = SourceDocument(
            event_id=event.event_id,
            company_id=company_id,
            period_id=resolved_period,
            document_type=document_type,
            document_title=document_title,
            source_url=source_url,
            storage_path=stored.storage_path,
            file_hash=stored.file_hash,
            extraction_status=ExtractionStatus.PENDING,
            meta={
                "content_type": content_type,
                "original_filename": filename,
                "size_bytes": stored.size_bytes,
            },
        )
        db.add(doc)
        db.flush()

    job = ExtractionJob(
        document_id=doc.document_id,
        company_id=company_id,
        job_type="document_extraction",
        status=ExtractionStatus.PENDING,
        meta={"queued_by_user_id": user.user_id},
    )
    db.add(job)
    db.flush()

    review = _enqueue_review(db, company_id=company_id, event=event, document=doc)
    db.commit()

    return {
        "queued": True,
        "event_id": event.event_id,
        "document_id": doc.document_id,
        "job_id": job.extraction_job_id,
        "review_id": review.review_id,
        "file_hash": stored.file_hash,
        "size_bytes": stored.size_bytes,
    }


# ---------------------------------------------------------------------------
# Job inspection (admin-friendly status)
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=None)
def list_jobs(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> list[dict]:
    """Recent extraction jobs across all documents."""
    stmt = (
        select(ExtractionJob, SourceDocument, Company)
        .join(SourceDocument, SourceDocument.document_id == ExtractionJob.document_id)
        .join(Company, Company.company_id == ExtractionJob.company_id)
        .order_by(ExtractionJob.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "job_id": j.extraction_job_id,
            "document_id": j.document_id,
            "company_id": j.company_id,
            "company_name": c.company_name,
            "company_symbol": c.nse_symbol or c.bse_code,
            "document_title": d.document_title,
            "document_type": d.document_type.value,
            "status": j.status.value,
            "model_name": j.model_name,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "input_tokens": j.input_tokens,
            "output_tokens": j.output_tokens,
            "cost_usd": float(j.cost_usd) if j.cost_usd is not None else None,
            "extraction_confidence": float(d.extraction_confidence) if d.extraction_confidence is not None else None,
            "values_extracted": d.values_extracted,
            "cards_generated": d.cards_generated,
            "error_message": j.error_message,
            "meta": j.meta or {},
            "created_at": j.created_at.isoformat(),
        }
        for (j, d, c) in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enqueue_review(
    db: Session, *, company_id: int, event: CompanyEvent, document: SourceDocument
) -> ReviewQueue:
    review = ReviewQueue(
        company_id=company_id,
        event_id=event.event_id,
        document_id=document.document_id,
        review_type="new_document_ingested",
        priority=SeverityLevel.MEDIUM,
        issue_description=f"New {document.document_type.value} awaiting extraction.",
        status="OPEN",
    )
    db.add(review)
    db.flush()
    return review
