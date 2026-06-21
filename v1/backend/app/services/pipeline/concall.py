"""Stage 1d: lexicon-based concall transcript scoring.

For Management-Tone cards we need numeric scores the metric/signal engine
can compare quarter-over-quarter. ML-grade sentiment is overkill for V1
(too brittle, requires GPU, opaque to analysts) — instead we count word
hits from a small lexicon, normalize to 0..100, and write the result as
``ExtractedValue`` rows the engine treats like any other fact.

Scores produced:
- ``concall_confidence_score``     — assertive / decisive language.
- ``concall_uncertainty_score``    — hedged / vague language.
- ``concall_evasive_score``        — questions sidestepped or deflected.
- ``concall_demand_score``         — references to demand strength / visibility.
- ``concall_cost_pressure_score``  — references to inflation / wage / commodity.
- ``concall_pricing_power_score``  — references to price hikes / pass-through.
- ``concall_capex_intent_score``   — expansionary capex language.
- ``concall_margin_tone_score``    — margin confidence / expansion commentary.

Each score is the count of lexicon hits divided by the count of
hard-coded "page units" (every 1000 characters), capped at 100. The
absolute value isn't comparable across companies — only QoQ and YoY
deltas are. The seed exposes those via the ``management_confidence_change_qoq``
metric.

Lexicons live as module constants so analysts can iterate on them with a
single PR; moving them into a JSON config is a follow-up.
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


# Words / phrases per axis. Compiled once at import time.
_LEX_CONFIDENCE = [
    "confident", "confidence", "we are seeing", "strong demand", "very strong",
    "robust", "record", "clearly", "decisively", "accelerate", "accelerating",
    "well positioned", "no concerns", "comfortable", "on track",
]
_LEX_UNCERTAINTY = [
    "may", "might", "could", "expect", "expects", "expected", "uncertain",
    "uncertainty", "challenging", "headwind", "softer", "subdued", "weakness",
    "moderation", "cautious", "monitor", "watching",
]
_LEX_EVASIVE = [
    "we'll come back", "not at this stage", "we don't disclose", "competitive reasons",
    "won't share", "premature", "too early", "no comment", "let me come back",
    "circle back", "on a different forum",
]
_LEX_DEMAND = [
    "order book", "deal pipeline", "deal wins", "demand environment", "demand outlook",
    "tendering pipeline", "RFP", "client adds", "new clients", "ramp up",
]
_LEX_COST_PRESSURE = [
    "wage inflation", "salary hike", "commodity inflation", "input cost",
    "supply chain", "shipping cost", "logistics cost", "fuel cost", "raw material",
]
_LEX_PRICING_POWER = [
    "price hike", "price increase", "pricing action", "pass through", "pass-through",
    "pricing power", "renewals at higher", "rate hike", "rate revision",
]
_LEX_CAPEX = [
    "capex", "capital expenditure", "capacity expansion", "greenfield", "brownfield",
    "new plant", "new facility", "investment cycle", "spend on capacity",
]
_LEX_MARGIN_TONE = [
    "margin expansion", "margin improvement", "margin recovery", "pricing discipline",
    "cost control", "operating leverage", "ebitda margin improvement", "profitable growth",
]


@dataclass(frozen=True)
class _Axis:
    code: str
    raw_label: str
    keywords: list[str]


_AXES: list[_Axis] = [
    _Axis("concall_confidence_score", "Management Confidence (concall)", _LEX_CONFIDENCE),
    _Axis("concall_uncertainty_score", "Management Uncertainty (concall)", _LEX_UNCERTAINTY),
    _Axis("concall_evasive_score", "Management Evasive (concall)", _LEX_EVASIVE),
    _Axis("concall_demand_score", "Concall Demand (concall)", _LEX_DEMAND),
    _Axis("concall_cost_pressure_score", "Concall Cost Pressure (concall)", _LEX_COST_PRESSURE),
    _Axis("concall_pricing_power_score", "Concall Pricing Power (concall)", _LEX_PRICING_POWER),
    _Axis("concall_capex_intent_score", "Concall Capex Intent (concall)", _LEX_CAPEX),
    _Axis("concall_margin_tone_score", "Concall Margin Tone (concall)", _LEX_MARGIN_TONE),
]


def is_concall_document(document: SourceDocument | None) -> bool:
    if not document or not document.document_type:
        return False
    return document.document_type.value == "CONCALL_TRANSCRIPT"


def run_concall_scoring(
    db: Session, *, document: SourceDocument, event: CompanyEvent
) -> int:
    """Score the transcript and persist axis values as `ExtractedValue` rows."""
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document.document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    if not pages:
        return 0

    full_text = "\n".join(p.page_text or "" for p in pages)
    if not full_text.strip():
        return 0
    page_units = max(1, len(full_text) // 1000)

    written = 0
    for axis in _AXES:
        hits = _count_hits(full_text, axis.keywords)
        score = min(100.0, hits / page_units * 50.0)
        # Pick the page with the highest individual hit count for evidence.
        best_page = max(
            pages,
            key=lambda p: _count_hits(p.page_text or "", axis.keywords),
            default=pages[0],
        )
        db.add(
            ExtractedValue(
                document_id=document.document_id,
                event_id=event.event_id,
                company_id=document.company_id,
                period_id=document.period_id,
                raw_label=axis.raw_label,
                normalized_label=axis.code,
                raw_value=f"{score:.1f}",
                numeric_value=score,
                unit="score",
                page_number=best_page.page_number,
                source_text=_excerpt_for(best_page.page_text or "", axis.keywords),
                confidence_score=72.0,
                confidence_level=ConfidenceLevel.MEDIUM,
                is_normalized=True,
            )
        )
        written += 1
    db.flush()
    return written


def _count_hits(text: str, keywords: list[str]) -> int:
    if not text:
        return 0
    lowered = text.lower()
    n = 0
    for kw in keywords:
        # word-boundary for short keywords; substring for multi-word phrases
        if " " in kw or "-" in kw or "'" in kw:
            n += lowered.count(kw)
        else:
            n += len(re.findall(rf"\b{re.escape(kw)}\b", lowered))
    return n


def _excerpt_for(text: str, keywords: list[str], *, span: int = 200) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    for kw in keywords:
        idx = lowered.find(kw)
        if idx >= 0:
            start = max(0, idx - span)
            end = min(len(text), idx + len(kw) + span)
            return text[start:end].strip()
    return None
