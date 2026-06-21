"""Stage 1e: order-book extractor.

Capital-goods, EPC, and IT-services investor presentations report opening
and closing order book, inflow / executed / cancelled orders, plus a
top-customer concentration figure. The metric engine consumes the values
through ``order_book_growth_yoy``, ``book_to_bill``, etc.

Like the shareholding and guidance extractors, this runs after the LLM
extraction and writes ``ExtractedValue`` rows so downstream stages stay
unchanged. The patterns are conservative — false positives produce noisy
order-book-growth signals.
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
class _OrderField:
    code: str
    raw_label: str
    unit: str
    pattern: re.Pattern[str]


_AMOUNT = r"(?P<value>-?[\d,]+(?:\.\d+)?)\s*(?:Cr|crore|Rs)?"
_FIELDS: list[_OrderField] = [
    _OrderField(
        "opening_order_book", "Opening Order Book", "crore",
        re.compile(rf"opening\s+order\s+book[^\d-]{{0,30}}{_AMOUNT}", re.IGNORECASE),
    ),
    _OrderField(
        "closing_order_book", "Closing Order Book", "crore",
        re.compile(rf"closing\s+order\s+book[^\d-]{{0,30}}{_AMOUNT}", re.IGNORECASE),
    ),
    _OrderField(
        "order_inflow", "Order Inflow", "crore",
        re.compile(rf"order\s+inflow[^\d-]{{0,30}}{_AMOUNT}", re.IGNORECASE),
    ),
    _OrderField(
        "executed_orders", "Executed Orders", "crore",
        re.compile(rf"(?:orders?\s+)?execut(?:ed|ion)[^\d-]{{0,30}}{_AMOUNT}", re.IGNORECASE),
    ),
    _OrderField(
        "cancelled_orders", "Cancelled Orders", "crore",
        re.compile(rf"cancell?ed\s+orders[^\d-]{{0,30}}{_AMOUNT}", re.IGNORECASE),
    ),
    _OrderField(
        "top_customer_orders", "Top-Customer Orders", "crore",
        re.compile(rf"top\s+customer[^\d-]{{0,40}}{_AMOUNT}", re.IGNORECASE),
    ),
    _OrderField(
        "new_order_value", "New Order Value", "crore",
        re.compile(
            rf"(?:order\s+worth|order\s+value|new\s+order|bagged\s+order)[^\d-]{{0,40}}{_AMOUNT}",
            re.IGNORECASE,
        ),
    ),
]


_DOCUMENT_TYPES_WITH_ORDER_BOOK = {
    "INVESTOR_PRESENTATION",
    "CONCALL_TRANSCRIPT",
    "ANNUAL_REPORT",
    "FINANCIAL_RESULT",
    "PRESS_RELEASE",
}


def is_order_book_document(document: SourceDocument | None) -> bool:
    if not document or not document.document_type:
        return False
    return document.document_type.value in _DOCUMENT_TYPES_WITH_ORDER_BOOK


def run_order_book_extraction(
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
                confidence_score=78.0,
                confidence_level=ConfidenceLevel.MEDIUM,
                is_normalized=True,
            )
        )
        written += 1
    if written:
        db.flush()
    return written
