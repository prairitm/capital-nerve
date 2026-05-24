"""Stage 1f: segment table extractor for financial results.

Quarterly results often include a segment revenue / EBIT table. This pass
parses conservative row patterns, persists ``SegmentFact`` rows for the
read-side segment breakdown, and rolls the largest segment up into
``primary_segment_revenue`` / ``primary_segment_ebit`` ``ExtractedValue`` rows
so the metric engine can compute segment growth and margin signals.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import ConfidenceLevel, ConsolidationType
from app.models.events import CompanyEvent, DocumentPage, SourceDocument
from app.models.facts import CompanySegment, ExtractedValue, SegmentFact

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SegmentRow:
    name: str
    revenue: float
    ebit: float | None


# Segment name followed by two crore-scale numbers (revenue, profit).
_SEGMENT_ROW = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9\s&./-]{2,48}?)\s+"
    r"(?P<rev>[\d,]+(?:\.\d+)?)\s+"
    r"(?P<ebit>-?[\d,]+(?:\.\d+)?)",
)


def is_segment_document(document: SourceDocument | None) -> bool:
    if not document or not document.document_type:
        return False
    return document.document_type.value == "FINANCIAL_RESULT"


def run_segment_extraction(
    db: Session, *, document: SourceDocument, event: CompanyEvent
) -> int:
    if document.period_id is None:
        return 0

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document.document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        return 0

    rows: list[_SegmentRow] = []
    for page in pages:
        text = page.page_text or ""
        if "segment" not in text.lower():
            continue
        for m in _SEGMENT_ROW.finditer(text):
            name = (m.group("name") or "").strip()
            if not name or len(name) < 3:
                continue
            lower = name.lower()
            if any(
                skip in lower
                for skip in (
                    "total",
                    "consolidated",
                    "unallocated",
                    "inter segment",
                    "inter-segment",
                    "particulars",
                    "segment revenue",
                    "segment profit",
                )
            ):
                continue
            try:
                rev = float((m.group("rev") or "").replace(",", ""))
                ebit = float((m.group("ebit") or "").replace(",", ""))
            except ValueError:
                continue
            if rev <= 0:
                continue
            rows.append(_SegmentRow(name=name, revenue=rev, ebit=ebit))

    if not rows:
        return 0

    # Keep the largest revenue row per normalized name.
    by_name: dict[str, _SegmentRow] = {}
    for row in rows:
        key = _normalize_segment_name(row.name)
        prev = by_name.get(key)
        if prev is None or row.revenue > prev.revenue:
            by_name[key] = row

    consolidation = event.consolidation or ConsolidationType.CONSOLIDATED
    written = 0
    primary: _SegmentRow | None = None

    for norm_name, row in by_name.items():
        segment = db.scalar(
            select(CompanySegment).where(
                CompanySegment.company_id == document.company_id,
                CompanySegment.normalized_segment_name == norm_name,
            )
        )
        if not segment:
            segment = CompanySegment(
                company_id=document.company_id,
                segment_name=row.name,
                normalized_segment_name=norm_name,
                segment_type="BUSINESS",
            )
            db.add(segment)
            db.flush()

        existing = db.scalar(
            select(SegmentFact).where(
                SegmentFact.company_id == document.company_id,
                SegmentFact.period_id == document.period_id,
                SegmentFact.segment_id == segment.segment_id,
                SegmentFact.consolidation == consolidation,
            )
        )
        if existing:
            existing.segment_revenue = row.revenue
            existing.segment_profit = row.ebit
            existing.document_id = document.document_id
            existing.event_id = event.event_id
        else:
            db.add(
                SegmentFact(
                    company_id=document.company_id,
                    event_id=event.event_id,
                    document_id=document.document_id,
                    period_id=document.period_id,
                    segment_id=segment.segment_id,
                    consolidation=consolidation,
                    segment_revenue=row.revenue,
                    segment_profit=row.ebit,
                    confidence_score=75.0,
                )
            )
        written += 1
        if primary is None or row.revenue > primary.revenue:
            primary = row

    if primary:
        written += _write_primary_segment_values(
            db, document=document, event=event, row=primary
        )
    db.flush()
    return written


def _normalize_segment_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:64] or "segment"


def _write_primary_segment_values(
    db: Session,
    *,
    document: SourceDocument,
    event: CompanyEvent,
    row: _SegmentRow,
) -> int:
    pairs = [
        ("primary_segment_revenue", "Primary Segment Revenue", row.revenue, "crore"),
        ("primary_segment_ebit", "Primary Segment EBIT", row.ebit, "crore"),
    ]
    count = 0
    for code, label, value, unit in pairs:
        if value is None:
            continue
        db.add(
            ExtractedValue(
                document_id=document.document_id,
                event_id=event.event_id,
                company_id=document.company_id,
                period_id=document.period_id,
                raw_label=label,
                normalized_label=code,
                raw_value=str(value),
                numeric_value=float(value),
                unit=unit,
                source_text=f"{row.name}: {label}",
                confidence_score=74.0,
                confidence_level=ConfidenceLevel.MEDIUM,
                is_normalized=True,
            )
        )
        count += 1
    return count
