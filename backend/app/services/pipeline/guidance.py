"""Stage 1c: forward guidance extractor.

Investor presentations and concall transcripts call out forward guidance in
predictable phrasings ("revenue growth of 12-15%", "EBITDA margin of 18-20%",
"capex of Rs 800-1,000 Cr"). The LLM extractor handles these via the
extended `normalized_code` allow-list, but the mock provider can't infer
them from regex on financial statements alone — it never sees the
forward-looking text.

This module fills that gap when the LLM provider isn't configured. It runs
after the standard extraction stage, scans the parsed pages, and writes
``ExtractedValue`` rows for the guidance line items if it finds them.

The metric engine reads these values via ``revenue_guidance_lower/upper``
and ``ebitda_margin_guidance_lower/upper`` to compute
``revenue_guidance_midpoint`` and the QoQ revision percentage (see seeds).
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
class _Guidance:
    lower_code: str
    upper_code: str
    raw_label: str
    unit: str


# Each pattern captures (lower, upper) and binds to a guidance bucket. The
# regexes are deliberately conservative — false positives create noisy
# signals downstream.
_PATTERNS: list[tuple[re.Pattern[str], _Guidance]] = [
    (
        re.compile(
            r"revenue\s+(?:growth\s+)?(?:guidance|target|outlook)[^\d-]*"
            r"(?P<lower>-?\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(?P<upper>-?\d+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
        _Guidance("revenue_guidance_lower", "revenue_guidance_upper", "Revenue Guidance", "%"),
    ),
    (
        re.compile(
            r"EBITDA\s*margin[^\d-]*(?P<lower>-?\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(?P<upper>-?\d+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
        _Guidance(
            "ebitda_margin_guidance_lower",
            "ebitda_margin_guidance_upper",
            "EBITDA Margin Guidance",
            "%",
        ),
    ),
]


_DOCUMENT_TYPES_WITH_GUIDANCE = {
    "INVESTOR_PRESENTATION",
    "CONCALL_TRANSCRIPT",
    "ANNUAL_REPORT",
    "PRESS_RELEASE",
}


def is_guidance_document(document: SourceDocument | None) -> bool:
    if not document or not document.document_type:
        return False
    return document.document_type.value in _DOCUMENT_TYPES_WITH_GUIDANCE


def run_guidance_extraction(
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

    written = 0
    seen: set[str] = set()
    for page in pages:
        text = page.page_text or ""
        for regex, spec in _PATTERNS:
            if spec.lower_code in seen:
                continue
            m = regex.search(text)
            if not m:
                continue
            try:
                lower = float(m.group("lower"))
                upper = float(m.group("upper"))
            except (TypeError, ValueError):
                continue
            line_start = max(0, m.start() - 80)
            source_line = text[line_start : min(len(text), m.end() + 20)].strip()
            db.add(
                ExtractedValue(
                    document_id=document.document_id,
                    event_id=event.event_id,
                    company_id=document.company_id,
                    period_id=document.period_id,
                    raw_label=f"{spec.raw_label} (lower)",
                    normalized_label=spec.lower_code,
                    raw_value=str(lower),
                    numeric_value=lower,
                    unit=spec.unit,
                    page_number=page.page_number,
                    source_text=source_line,
                    confidence_score=82.0,
                    confidence_level=ConfidenceLevel.MEDIUM,
                    is_normalized=True,
                )
            )
            db.add(
                ExtractedValue(
                    document_id=document.document_id,
                    event_id=event.event_id,
                    company_id=document.company_id,
                    period_id=document.period_id,
                    raw_label=f"{spec.raw_label} (upper)",
                    normalized_label=spec.upper_code,
                    raw_value=str(upper),
                    numeric_value=upper,
                    unit=spec.unit,
                    page_number=page.page_number,
                    source_text=source_line,
                    confidence_score=82.0,
                    confidence_level=ConfidenceLevel.MEDIUM,
                    is_normalized=True,
                )
            )
            seen.add(spec.lower_code)
            seen.add(spec.upper_code)
            written += 2
    if written:
        db.flush()
    return written
