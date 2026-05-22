"""Investor-facing event summary text from pipeline signals and cards."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.events import CompanyEvent
from app.models.intelligence import GeneratedSignal, IntelligenceCard

_PLACEHOLDER_RE = re.compile(r"^pipeline-generated brief:", re.I)


def is_pipeline_placeholder_summary(summary: str | None) -> bool:
    return bool(summary and _PLACEHOLDER_RE.match(summary.strip()))


def _strip_trigger_suffix(text: str) -> str:
    """Remove boilerplate appended by ``signals._signal_copy``."""
    idx = text.find(" Triggered at ")
    if idx > 0:
        return text[:idx].strip()
    return text.strip()


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _signal_sentence(sig: GeneratedSignal) -> str:
    if sig.explanation:
        return _sentence(_strip_trigger_suffix(sig.explanation))
    if sig.headline:
        return _sentence(sig.headline)
    return ""


def _join_sentences(parts: list[str]) -> str:
    clean = [p for p in parts if p]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} {clean[1]}"
    return f"{clean[0]} {clean[1]} {clean[2]}"


def build_event_summary_text(
    sigs: list[GeneratedSignal],
    cards: list[IntelligenceCard],
) -> str | None:
    """Compose a readable event summary from cards and signals."""
    for card in sorted(cards, key=lambda c: float(c.card_priority or 0), reverse=True):
        if card.card_type == "result_verdict":
            if card.detailed_explanation and card.detailed_explanation.strip():
                return _sentence(card.detailed_explanation.strip())
            summary = (card.one_line_summary or "").strip()
            if summary and "triggers " not in summary.lower():
                return _sentence(summary)

    ordered_sigs = sorted(sigs, key=lambda s: float(s.signal_score or 0), reverse=True)
    sig_parts: list[str] = []
    for sig in ordered_sigs[:3]:
        line = _signal_sentence(sig)
        if line and line not in sig_parts:
            sig_parts.append(line)

    if sig_parts:
        return _join_sentences(sig_parts)

    if cards:
        top = max(cards, key=lambda c: float(c.card_priority or 0))
        if top.detailed_explanation and top.detailed_explanation.strip():
            return _sentence(top.detailed_explanation.strip())
        if top.one_line_summary and "triggers " not in top.one_line_summary.lower():
            return _sentence(top.one_line_summary)
        return _sentence(top.headline)

    return None


def pick_main_issue(
    sigs: list[GeneratedSignal],
    cards: list[IntelligenceCard],
) -> str | None:
    negative = [s for s in sigs if s.signal_direction.value == "NEGATIVE"]
    pool = negative if negative else sigs
    if pool:
        top = max(pool, key=lambda s: float(s.signal_score or 0))
        if top.headline:
            return top.headline
    for card in sorted(cards, key=lambda c: float(c.card_priority or 0), reverse=True):
        if card.card_type in ("red_flag", "profit_quality", "margin_movement", "debt_signal"):
            return card.headline
    return None


def pick_watch_next(cards: list[IntelligenceCard]) -> str | None:
    with_watch = [c for c in cards if c.watch_next and c.watch_next.strip()]
    if not with_watch:
        return None
    top = max(with_watch, key=lambda c: float(c.card_priority or 0))
    return top.watch_next.strip()


def resolve_event_summary_text(
    event: CompanyEvent,
    sigs: list[GeneratedSignal],
    cards: list[IntelligenceCard],
) -> str | None:
    """Return stored summary or rebuild when the pipeline placeholder was persisted."""
    if is_pipeline_placeholder_summary(event.summary_text):
        return build_event_summary_text(sigs, cards)
    return event.summary_text


def load_signals_and_cards_by_event(
    db: Session,
    event_ids: list[int],
) -> tuple[dict[int, list[GeneratedSignal]], dict[int, list[IntelligenceCard]]]:
    if not event_ids:
        return {}, {}
    sigs = list(
        db.scalars(select(GeneratedSignal).where(GeneratedSignal.event_id.in_(event_ids))).all()
    )
    cards = list(
        db.scalars(
            select(IntelligenceCard)
            .where(IntelligenceCard.event_id.in_(event_ids))
            .where(IntelligenceCard.card_type != "watch_next")
        ).all()
    )
    sigs_by: dict[int, list[GeneratedSignal]] = defaultdict(list)
    cards_by: dict[int, list[IntelligenceCard]] = defaultdict(list)
    for sig in sigs:
        if sig.event_id is not None:
            sigs_by[sig.event_id].append(sig)
    for card in cards:
        if card.event_id is not None:
            cards_by[card.event_id].append(card)
    return dict(sigs_by), dict(cards_by)
