"""Stage 1g: press-release fact extractor.

Exchange press releases announce orders, M&A, dividends, and capacity
additions in predictable phrasing. Regex extraction backstops the LLM when
``LLM_PROVIDER=mock`` and fills gaps on real runs.
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


_AMOUNT = r"(?P<value>-?[\d,]+(?:\.\d+)?)"
_FIELDS: list[_Field] = [
    _Field(
        "new_order_value",
        "New Order Value",
        "crore",
        re.compile(
            rf"(?:order\s+worth|order\s+value|new\s+order|bagged\s+order)[^\d-]{{0,40}}{_AMOUNT}",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "acquisition_value",
        "Acquisition Value",
        "crore",
        re.compile(
            rf"(?:acquisition|acquire|to\s+acquire)[^\d-]{{0,50}}{_AMOUNT}\s*(?:cr|crore|Rs)?",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "dividend_per_share",
        "Dividend Per Share",
        "Rs",
        re.compile(
            rf"dividend[^\d-]{{0,30}}{_AMOUNT}\s*(?:per\s+share|/share|Rs)?",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "revenue_contribution_pct",
        "Revenue Contribution %",
        "%",
        re.compile(
            r"revenue\s+contribution[^\d-]{0,30}(?P<value>-?[\d,]+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "new_capacity",
        "New Capacity",
        "unit",
        re.compile(
            r"(?:new|additional)\s+capacity[^\d-]{0,30}(?P<value>-?[\d,]+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ),
    _Field(
        "existing_capacity",
        "Existing Capacity",
        "unit",
        re.compile(
            r"(?:existing|current|total)\s+capacity[^\d-]{0,30}(?P<value>-?[\d,]+(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ),
]


def is_press_release_document(document: SourceDocument | None) -> bool:
    if not document or not document.document_type:
        return False
    return document.document_type.value == "PRESS_RELEASE"


def run_announcement_extraction(
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
                confidence_score=76.0,
                confidence_level=ConfidenceLevel.MEDIUM,
                is_normalized=True,
            )
        )
        written += 1
    if written:
        db.flush()
    return written
