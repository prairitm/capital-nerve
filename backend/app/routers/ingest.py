"""Ingestion endpoints.

`POST /ingest/upload` (multipart) is the only ingestion path. Upload a PDF
(or markdown / text) with the company + period metadata; the endpoint
persists the file, creates a `CompanyEvent` + `SourceDocument`, queues an
`ExtractionJob(status=PENDING)`, and the worker (see
`app/workers/pipeline_worker.py`) drains the queue.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated
from urllib.parse import unquote, urlparse

import httpx
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
    PeriodType,
    SeverityLevel,
)
from app.models.events import CompanyEvent, ExtractionJob, SourceDocument
from app.models.master import Company, FinancialPeriod
from app.models.review import ReviewQueue
from app.models.user import AppUser
from app.services.pipeline.storage import get_storage

router = APIRouter(prefix="/ingest", tags=["ingest"])

_MAX_URL_BYTES = 50 * 1024 * 1024


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
            data, filename, content_type = _fetch_document_from_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        source_url = url

    storage = get_storage()
    suffix = _suffix_for(filename, content_type)
    stored = storage.put_bytes(data, suffix=suffix)

    resolved_period = _resolve_period_id(
        db, period_id=period_id, period_label=period_label, event_date=event_date
    )
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


# e.g. "Q4 FY2025-26", "Q4 FY25-26", "q4 fy25/26"
_PERIOD_LABEL_RE = re.compile(
    r"^\s*Q([1-4])\s+FY\s*(\d{2,4})\s*[-/]\s*(\d{2,4})\s*$",
    re.IGNORECASE,
)


def _resolve_period_id(
    db: Session,
    *,
    period_id: int | None,
    period_label: str | None,
    event_date: date | None,
) -> int | None:
    """Find an existing financial period by id, label, or event date.

    Resolution order: `period_id` → exact `display_label` → parsed quarter/FY
    label → date lookup → create quarterly period from date or parsed label.
    """
    if period_id:
        if db.get(FinancialPeriod, period_id):
            return period_id
        raise HTTPException(status_code=400, detail=f"period_id {period_id} not found")

    if period_label:
        label = period_label.strip()
        matched = db.scalar(
            select(FinancialPeriod).where(FinancialPeriod.display_label == label)
        )
        if matched:
            return matched.period_id
        parsed = _parse_period_label(label)
        if parsed:
            quarter, fy_year = parsed
            by_key = db.scalar(
                select(FinancialPeriod).where(
                    FinancialPeriod.fy_year == fy_year,
                    FinancialPeriod.quarter == quarter,
                    FinancialPeriod.period_type == PeriodType.QUARTERLY,
                )
            )
            if by_key:
                return by_key.period_id
            return _create_period_from_quarter(db, fy_year=fy_year, quarter=quarter)

    if event_date:
        q = db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.period_type == PeriodType.QUARTERLY,
                FinancialPeriod.period_start_date <= event_date,
                FinancialPeriod.period_end_date >= event_date,
            )
        )
        if q:
            return q.period_id
        return _create_period_from_date(db, event_date)

    return None


def _parse_period_label(label: str) -> tuple[int, int] | None:
    """Parse 'Q4 FY25-26' → (quarter=4, fy_year=2025). Returns None if unrecognized."""
    m = _PERIOD_LABEL_RE.match(label.strip())
    if not m:
        return None
    quarter = int(m.group(1))
    y1 = int(m.group(2))
    if len(m.group(2)) == 2:
        y1 = 2000 + y1 if y1 < 70 else 1900 + y1
    return quarter, y1


def _quarter_date_bounds(fy_year: int, quarter: int) -> tuple[date, date, str, str]:
    """Indian FY quarter window and canonical labels for `fy_year` + `quarter`."""
    q_start_month = 4 + (quarter - 1) * 3
    q_start_year = fy_year if q_start_month <= 12 else fy_year + 1
    if q_start_month > 12:
        q_start_month -= 12
    start = date(q_start_year, q_start_month, 1)
    next_month = q_start_month + 3
    end_year = q_start_year + (next_month - 1) // 12
    end_month = ((next_month - 1) % 12) + 1
    end = date(end_year, end_month, 1) - _one_day()
    fy_label = f"FY{fy_year}-{(fy_year + 1) % 100:02d}"
    display_label = f"Q{quarter} {fy_label}"
    return start, end, fy_label, display_label


def _create_period_from_quarter(db: Session, *, fy_year: int, quarter: int) -> int:
    """Find or insert a quarterly period for the parsed FY quarter."""
    existing = db.scalar(
        select(FinancialPeriod).where(
            FinancialPeriod.fy_year == fy_year,
            FinancialPeriod.quarter == quarter,
            FinancialPeriod.period_type == PeriodType.QUARTERLY,
        )
    )
    if existing:
        return existing.period_id
    start, end, fy_label, display_label = _quarter_date_bounds(fy_year, quarter)
    period = FinancialPeriod(
        fy_year=fy_year,
        fy_label=fy_label,
        quarter=quarter,
        period_type=PeriodType.QUARTERLY,
        period_start_date=start,
        period_end_date=end,
        display_label=display_label,
    )
    db.add(period)
    db.flush()
    return period.period_id


def _create_period_from_date(db: Session, d: date) -> int:
    """Create a quarterly `FinancialPeriod` whose window contains `d`."""
    month = d.month
    quarter = ((month - 4) % 12) // 3 + 1
    fy_year = d.year if month >= 4 else d.year - 1
    return _create_period_from_quarter(db, fy_year=fy_year, quarter=quarter)


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _fetch_document_from_url(url: str) -> tuple[bytes, str | None, str | None]:
    """Download a PDF or text filing from an http(s) URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("document_url must be a valid http or https URL")

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].strip() or None
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > _MAX_URL_BYTES:
                        raise ValueError(
                            f"Remote document exceeds {_MAX_URL_BYTES // (1024 * 1024)} MB limit"
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Could not fetch document_url: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Could not fetch document_url: {exc}") from exc

    if not data:
        raise ValueError("Remote document is empty")

    filename = _filename_from_url(parsed.path) or _filename_from_content_type(content_type)
    if not _suffix_for(filename, content_type) in (".pdf", ".txt", ".md"):
        raise ValueError(
            "Remote document must be a PDF or plain text file "
            "(check the URL extension or Content-Type header)"
        )
    return data, filename, content_type


def _filename_from_url(path: str) -> str | None:
    name = unquote(path.rsplit("/", 1)[-1]).strip()
    if name and "." in name:
        return name
    return None


def _filename_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    if "pdf" in content_type:
        return "document.pdf"
    if "markdown" in content_type:
        return "document.md"
    if "text" in content_type:
        return "document.txt"
    return None


def _suffix_for(filename: str | None, content_type: str | None) -> str:
    """Pick a sensible extension so storage files are still introspectable."""
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    if content_type:
        if "pdf" in content_type:
            return ".pdf"
        if "markdown" in content_type:
            return ".md"
        if "text" in content_type:
            return ".txt"
    return ".bin"
