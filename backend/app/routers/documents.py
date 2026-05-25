from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.enums import ExtractionStatus
from app.models.events import DocumentPage, ExtractionJob, SourceDocument
from app.models.facts import ExtractedValue
from app.models.intelligence import CardEvidence, IntelligenceCard
from app.services.pipeline.cards import _extracted_evidence_display
from app.models.master import Company
from app.models.user import AppUser
from app.services.pipeline.storage import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])

_PDF_MEDIA = "application/pdf"


def _source_content_type(doc: SourceDocument) -> str | None:
    meta = doc.meta if isinstance(doc.meta, dict) else {}
    content_type = meta.get("content_type")
    if isinstance(content_type, str) and content_type.strip():
        return content_type.strip()
    if doc.storage_path and doc.storage_path.lower().endswith(".pdf"):
        return _PDF_MEDIA
    return None


def _has_source_file(doc: SourceDocument) -> bool:
    if not doc.storage_path:
        return False
    return get_storage().exists(doc.storage_path)


def _panel_fact_key(
    *,
    page_number: int | None,
    evidence_label: str | None,
    evidence_value: str | None,
) -> tuple[int | None, str, str]:
    return (
        page_number,
        (evidence_label or "").strip().lower(),
        (evidence_value or "").strip().lower(),
    )


def _panel_row_rank(*, evidence_type: str | None, source_text: str | None, confidence: float | None) -> float:
    rank = float(confidence or 0)
    if source_text and source_text.strip():
        rank += 100
    if evidence_type in ("source_quote", "extracted_value"):
        rank += 50
    if evidence_type == "calculated_metric":
        rank -= 40
    return rank


def _upsert_panel_row(
    rows: dict[tuple[int | None, str, str], dict[str, object]],
    row: dict[str, object],
) -> None:
    key = _panel_fact_key(
        page_number=row.get("page_number"),  # type: ignore[arg-type]
        evidence_label=row.get("evidence_label"),  # type: ignore[arg-type]
        evidence_value=row.get("evidence_value"),  # type: ignore[arg-type]
    )
    if not key[1] and not key[2]:
        return
    prev = rows.get(key)
    if prev is None or _panel_row_rank(
        evidence_type=row.get("evidence_type"),  # type: ignore[arg-type]
        source_text=row.get("source_text"),  # type: ignore[arg-type]
        confidence=row.get("confidence_score"),  # type: ignore[arg-type]
    ) > _panel_row_rank(
        evidence_type=prev.get("evidence_type"),  # type: ignore[arg-type]
        source_text=prev.get("source_text"),  # type: ignore[arg-type]
        confidence=prev.get("confidence_score"),  # type: ignore[arg-type]
    ):
        rows[key] = row


@router.get("/{document_id}")
def document_detail(
    document_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    doc = db.get(SourceDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    company = db.get(Company, doc.company_id)
    pages = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
    ).all()

    cards = db.scalars(
        select(IntelligenceCard).where(IntelligenceCard.document_id == document_id)
    ).all()

    evidence = db.scalars(
        select(CardEvidence).where(CardEvidence.document_id == document_id)
    ).all()
    covered_extracted_ids = {
        e.extracted_value_id for e in evidence if e.extracted_value_id is not None
    }
    supplemental_extracted = db.scalars(
        select(ExtractedValue)
        .where(ExtractedValue.document_id == document_id)
        .where(ExtractedValue.page_number.is_not(None))
        .where(
            (ExtractedValue.source_text.is_not(None))
            | (ExtractedValue.raw_value.is_not(None))
            | (ExtractedValue.numeric_value.is_not(None))
        )
    ).all()

    content_type = _source_content_type(doc)
    panel_rows: dict[tuple[int | None, str, str], dict[str, object]] = {}
    orphan_rows: list[dict[str, object]] = []

    for e in evidence:
        row = {
            "card_evidence_id": e.card_evidence_id,
            "card_id": e.card_id,
            "evidence_type": e.evidence_type,
            "evidence_label": e.evidence_label,
            "evidence_value": e.evidence_value,
            "source_text": e.source_text,
            "page_number": e.page_number,
            "calculation_text": e.calculation_text,
            "confidence_score": float(e.confidence_score)
            if e.confidence_score is not None
            else None,
        }
        key = _panel_fact_key(
            page_number=e.page_number,
            evidence_label=e.evidence_label,
            evidence_value=e.evidence_value,
        )
        if not key[1] and not key[2]:
            orphan_rows.append(row)
        else:
            _upsert_panel_row(panel_rows, row)

    for ev in supplemental_extracted:
        if ev.extracted_value_id in covered_extracted_ids:
            continue
        row = {
            "card_evidence_id": -ev.extracted_value_id,
            "card_id": 0,
            "evidence_type": "extracted_value",
            "evidence_label": ev.raw_label,
            "evidence_value": _extracted_evidence_display(ev),
            "source_text": ev.source_text,
            "page_number": ev.page_number,
            "calculation_text": None,
            "confidence_score": float(ev.confidence_score)
            if ev.confidence_score is not None
            else None,
        }
        _upsert_panel_row(panel_rows, row)

    evidence_payload: list[dict[str, object]] = [
        *panel_rows.values(),
        *orphan_rows,
    ]

    return {
        "document_id": doc.document_id,
        "document_type": doc.document_type.value,
        "document_title": doc.document_title,
        "has_source_file": _has_source_file(doc),
        "source_content_type": content_type,
        "document_date": doc.document_date.isoformat() if doc.document_date else None,
        "extraction_confidence": float(doc.extraction_confidence) if doc.extraction_confidence is not None else None,
        "extraction_status": doc.extraction_status.value,
        "values_extracted": doc.values_extracted,
        "cards_generated": doc.cards_generated,
        "page_count": doc.page_count,
        "company": {
            "company_id": company.company_id,
            "company_name": company.company_name,
            "symbol": company.nse_symbol or company.bse_code,
        }
        if company
        else None,
        "pages": [
            {
                "page_id": p.page_id,
                "page_number": p.page_number,
                "page_markdown": p.page_markdown,
                "page_text": p.page_text,
            }
            for p in pages
        ],
        "cards": [
            {
                "card_id": c.card_id,
                "card_type": c.card_type,
                "headline": c.headline,
                "one_line_summary": c.one_line_summary,
                "signal_direction": c.signal_direction.value if c.signal_direction else None,
                "severity": c.severity.value if c.severity else None,
            }
            for c in cards
        ],
        "evidence": evidence_payload,
    }


@router.post("/{document_id}/reextract", status_code=status.HTTP_202_ACCEPTED)
def reextract_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-run the extraction pipeline for one stored document (same file, new job)."""
    doc = db.get(SourceDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.storage_path or not _has_source_file(doc):
        raise HTTPException(
            status_code=400,
            detail="Document has no stored source file to re-extract.",
        )

    active_job_id = db.scalar(
        select(ExtractionJob.extraction_job_id)
        .where(
            ExtractionJob.document_id == document_id,
            ExtractionJob.status.in_(
                (ExtractionStatus.PENDING, ExtractionStatus.PROCESSING)
            ),
        )
        .order_by(ExtractionJob.created_at.desc())
        .limit(1)
    )
    if active_job_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Extraction is already queued or running for this document.",
        )

    doc.extraction_status = ExtractionStatus.PENDING
    job = ExtractionJob(
        document_id=doc.document_id,
        company_id=doc.company_id,
        job_type="document_reextract",
        status=ExtractionStatus.PENDING,
        meta={
            "queued_by_user_id": user.user_id,
            "reextract": True,
            "document_title": doc.document_title,
        },
    )
    db.add(job)
    db.commit()

    return {
        "queued": True,
        "document_id": doc.document_id,
        "job_id": job.extraction_job_id,
        "extraction_status": doc.extraction_status.value,
    }


@router.get("/{document_id}/file")
def document_file(
    document_id: int,
    db: Session = Depends(get_db),
    user: AppUser = Depends(get_current_user),
) -> Response:
    doc = db.get(SourceDocument, document_id)
    if not doc or not doc.storage_path:
        raise HTTPException(status_code=404, detail="Document file not found")
    storage = get_storage()
    if not storage.exists(doc.storage_path):
        raise HTTPException(status_code=404, detail="Document file not found")
    data = storage.open_bytes(doc.storage_path)
    media_type = _source_content_type(doc) or "application/octet-stream"
    filename = (doc.document_title or f"document-{document_id}").replace('"', "")
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
