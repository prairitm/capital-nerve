from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.events import DocumentPage, SourceDocument
from app.models.intelligence import CardEvidence, IntelligenceCard
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

    content_type = _source_content_type(doc)
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
        "evidence": [
            {
                "card_evidence_id": e.card_evidence_id,
                "card_id": e.card_id,
                "evidence_label": e.evidence_label,
                "evidence_value": e.evidence_value,
                "source_text": e.source_text,
                "page_number": e.page_number,
                "calculation_text": e.calculation_text,
                "confidence_score": float(e.confidence_score) if e.confidence_score is not None else None,
            }
            for e in evidence
        ],
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
