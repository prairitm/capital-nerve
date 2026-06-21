"""Documents router — serves stored filing PDFs and parsed page text."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from .. import ids, mapper, resolve
from ..builder import Catalog
from ..config import settings
from ..deps import catalog_dep, get_current_user
from ..state import User

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}")
def get_document(
    document_id: int,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict:
    filing = resolve.find_filing_by_int(catalog, document_id)
    if filing is None:
        raise HTTPException(status_code=404, detail="Document not found")

    md_path = settings.parsed_dir / f"{filing.document_id}.md"
    meta_path = settings.parsed_dir / f"{filing.document_id}.meta.json"
    raw_path = settings.raw_dir / f"{filing.sha256}.pdf"

    page_count = None
    if meta_path.exists():
        try:
            page_count = json.loads(meta_path.read_text(encoding="utf-8")).get("page_count")
        except (OSError, json.JSONDecodeError):
            page_count = None

    pages = []
    if md_path.exists():
        markdown = md_path.read_text(encoding="utf-8")
        pages = [
            {
                "page_id": ids.stable_int("page", filing.document_id, 1),
                "page_number": 1,
                "page_markdown": markdown,
                "page_text": markdown,
            }
        ]

    built = None
    if filing.quarter is not None and filing.fy_start_year is not None:
        from ..builder import Period

        period = Period(
            ticker=filing.ticker,
            quarter=filing.quarter,
            fy_start_year=filing.fy_start_year,
            fy_label=filing.fy_label or "",
            quarter_end=filing.quarter_end or "",
            label=f"Q{filing.quarter} {filing.fy_label or ''}".strip(),
        )
        built = catalog.build_period(period)

    cards = []
    evidence = []
    if built is not None:
        brief = mapper.intelligence_object_brief(catalog, built)
        cards = [
            {
                "card_id": brief["intelligence_object_id"],
                "card_type": brief["object_type"],
                "headline": brief["title"],
                "one_line_summary": brief["subtitle"],
                "signal_direction": brief["status"],
                "severity": brief["severity"],
            }
        ]
        for item in mapper._evidence_items(catalog, built):
            evidence.append(
                {
                    "card_evidence_id": item["card_evidence_id"],
                    "card_id": brief["intelligence_object_id"],
                    "evidence_type": item["evidence_type"],
                    "evidence_label": item["evidence_label"],
                    "evidence_value": item["evidence_value"],
                    "source_text": item["source_text"],
                    "page_number": item["page_number"],
                    "calculation_text": item["calculation_text"],
                    "confidence_score": item["confidence_score"],
                }
            )

    return {
        "document_id": document_id,
        "document_type": "FINANCIAL_RESULT",
        "document_title": filing.title or f"{filing.ticker} filing",
        "has_source_file": raw_path.exists(),
        "source_content_type": "application/pdf" if raw_path.exists() else None,
        "document_date": filing.quarter_end,
        "extraction_confidence": 0.9,
        "extraction_status": "COMPLETED",
        "values_extracted": len([e for e in evidence]),
        "cards_generated": len(cards),
        "page_count": page_count,
        "company": {
            "company_id": ids.company_id(filing.ticker),
            "company_name": filing.ticker.title(),
            "symbol": filing.ticker,
        },
        "pages": pages,
        "cards": cards,
        "evidence": evidence,
    }


@router.get("/{document_id}/file")
def get_document_file(
    document_id: int,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> FileResponse:
    filing = resolve.find_filing_by_int(catalog, document_id)
    if filing is None:
        raise HTTPException(status_code=404, detail="Document not found")
    raw_path = settings.raw_dir / f"{filing.sha256}.pdf"
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="Source file not available")
    return FileResponse(raw_path, media_type="application/pdf", filename=raw_path.name)


@router.post("/{document_id}/reextract", status_code=status.HTTP_202_ACCEPTED)
def reextract(
    document_id: int,
    user: User = Depends(get_current_user),
) -> dict:
    # Re-extraction happens in the v2 notebook pipeline, not over HTTP.
    return {"queued": False, "job_id": 0}
