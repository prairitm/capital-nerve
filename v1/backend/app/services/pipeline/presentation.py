"""Stage 1h: investor-presentation fact extractor.

Deck slides quote TAM, client concentration, geographic mix, capacity
utilization, and management targets in semi-structured text. Regex
extraction writes ``ExtractedValue`` rows for the metric engine.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.enums import ConfidenceLevel
from app.models.events import CompanyEvent, DocumentPage, SourceDocument
from app.models.facts import ExtractedValue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Field:
    code: str
    raw_label: str
    unit: str
    pattern: re.Pattern[str]


_FIELDS: list[_Field] = [
    _Field(
        "tam_market_size",
        "TAM / Market Size",
        "crore",
        re.compile(
            r"(?:TAM|total\s+addressable\s+market|market\s+size)[^\d-]{0,40}"
            r"(?P<value>[\d,]+(?:\.\d+)?)\s*(?:cr|crore|bn|billion)?",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "tam_market_size_prior",
        "Prior TAM / Market Size",
        "crore",
        re.compile(
            r"(?:prior|previous|last\s+year)[^\d]{0,20}(?:TAM|market\s+size)[^\d-]{0,30}"
            r"(?P<value>[\d,]+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "high_margin_revenue_pct",
        "High-Margin Revenue %",
        "%",
        re.compile(
            r"(?:high[- ]margin|software|services)\s+(?:revenue|mix)[^\d-]{0,30}"
            r"(?P<value>[\d,]+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "top_client_revenue_pct",
        "Top Client Revenue %",
        "%",
        re.compile(
            r"top\s+(?:\d+\s+)?(?:client|customer)[^\d-]{0,40}(?P<value>[\d,]+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "region_revenue_pct",
        "Region Revenue %",
        "%",
        re.compile(
            r"(?:India|domestic|export|international|US|Europe)[^\d-]{0,30}"
            r"(?P<value>[\d,]+(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:revenue|sales)?",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "capacity_utilization_pct",
        "Capacity Utilization %",
        "%",
        re.compile(
            r"capacity\s+utili[sz]ation[^\d-]{0,20}(?P<value>[\d,]+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "management_target_value",
        "Management Target Value",
        "crore",
        re.compile(
            r"(?:target|guidance|aiming\s+for)[^\d-]{0,40}(?:revenue|sales)[^\d-]{0,20}"
            r"(?P<value>[\d,]+(?:\.\d+)?)\s*(?:cr|crore)?",
            re.IGNORECASE,
        ),
    ),
]


def is_investor_presentation_document(document: SourceDocument | None) -> bool:
    if not document or not document.document_type:
        return False
    return document.document_type.value == "INVESTOR_PRESENTATION"


def run_presentation_extraction(
    db: Session, *, document: SourceDocument, event: CompanyEvent
) -> int:
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document.document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        return 0

    seen: dict[str, tuple[float, int, str, str]] = {}
    for page in pages:
        text = page.page_text or ""
        for spec in _FIELDS:
            if spec.code in seen:
                continue
            m = spec.pattern.search(text)
            if not m:
                continue
            raw = (m.group("value") or "").replace(",", "")
            try:
                value = float(raw)
            except ValueError:
                continue
            line_start = max(0, m.start() - 80)
            source = text[line_start : min(len(text), m.end() + 20)].strip()
            seen[spec.code] = (value, page.page_number, spec.raw_label, source)

    written = 0
    for code, (value, page_no, raw_label, source) in seen.items():
        unit = next((s.unit for s in _FIELDS if s.code == code), "crore")
        db.add(
            ExtractedValue(
                document_id=document.document_id,
                event_id=event.event_id,
                company_id=document.company_id,
                period_id=document.period_id,
                raw_label=raw_label,
                normalized_label=code,
                raw_value=str(value),
                numeric_value=value,
                unit=unit,
                page_number=page_no,
                source_text=source,
                confidence_score=74.0,
                confidence_level=ConfidenceLevel.MEDIUM,
                is_normalized=True,
            )
        )
        written += 1
    if written:
        db.flush()
    return written
