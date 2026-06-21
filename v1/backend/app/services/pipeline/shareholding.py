"""Stage 1b: shareholding-pattern extractor.

Runs alongside the standard LLM extraction when the document is a SEBI / NSE /
BSE *shareholding pattern* filing. Those PDFs follow a near-identical layout
across companies, so a regex pass is reliable enough for V1 — and it's free.

Outputs are written as `ExtractedValue` rows keyed by the new normalized
codes (`promoter_holding_pct`, `promoter_pledge_pct`, `fii_holding_pct`,
`dii_holding_pct`, `public_holding_pct`). Downstream stages (normalization,
metrics, signals, cards) treat them exactly like any other extracted value
— a separate code path was avoided on purpose.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.db.enums import ConfidenceLevel
from app.models.events import CompanyEvent, DocumentPage, SourceDocument
from app.models.facts import ExtractedValue

logger = logging.getLogger(__name__)


# Each row is (regex, normalized_code, raw_label). The patterns capture a
# percentage value; the runtime ignores the rest of the line.
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"promoter[s']?\s+(?:and\s+promoter\s+group\s+)?holding\W{0,4}(?P<value>-?\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
        "promoter_holding_pct",
        "Promoter Holding %",
    ),
    (
        re.compile(r"promoter[s']?\s+(?:shares\s+)?pledged\W{0,4}(?P<value>-?\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
        "promoter_pledge_pct",
        "Promoter Pledge %",
    ),
    (
        re.compile(r"\bFII\b[^%\n]{0,30}(?P<value>-?\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
        "fii_holding_pct",
        "FII Holding %",
    ),
    (
        re.compile(r"\bDII\b[^%\n]{0,30}(?P<value>-?\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
        "dii_holding_pct",
        "DII Holding %",
    ),
    (
        re.compile(r"public\s+(?:shareholding|holding)[^%\n]{0,30}(?P<value>-?\d+(?:\.\d+)?)\s*%", re.IGNORECASE),
        "public_holding_pct",
        "Public Holding %",
    ),
]


def is_shareholding_document(event: CompanyEvent | None) -> bool:
    """The shareholding form is logged via `EventType.SHAREHOLDING_PATTERN`."""
    if not event or not event.event_type:
        return False
    return event.event_type.value == "SHAREHOLDING_PATTERN"


def run_shareholding_extraction(
    db: Session,
    *,
    document: SourceDocument,
    event: CompanyEvent,
) -> int:
    """Add shareholding values to `extracted_values`. Returns rows written.

    Idempotent: clears any prior shareholding rows for this document before
    writing the new ones (mirrors the pattern in `extraction.run_extraction`).
    """
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document.document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        return 0

    seen: dict[str, tuple[float, int, str, str]] = {}
    for p in pages:
        text = p.page_text or ""
        for pattern, code, raw_label in _PATTERNS:
            if code in seen:
                continue
            m = pattern.search(text)
            if not m:
                continue
            try:
                value = float(m.group("value"))
            except (TypeError, ValueError):
                continue
            line_start = max(0, m.start() - 60)
            source_line = text[line_start : min(len(text), m.end() + 20)].strip()
            seen[code] = (value, p.page_number, raw_label, source_line)

    written = 0
    for code, (value, page_no, raw_label, source_text) in seen.items():
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
                unit="%",
                page_number=page_no,
                source_text=source_text,
                confidence_score=85.0,
                confidence_level=ConfidenceLevel.HIGH,
                is_normalized=True,
            )
        )
        written += 1
    db.flush()
    return written
