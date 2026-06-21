"""Investor-facing event summary text from pipeline signals and cards."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import SignalDirection
from app.models.events import CompanyEvent
from app.models.intelligence import GeneratedSignal, IntelligenceCard, SignalDefinition

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


# ---------------------------------------------------------------------------
# Themed analyst summary
# ---------------------------------------------------------------------------


# Maps a signal's `signal_category` (from `SIGNAL_DEFS`) to one of the four
# analyst themes. Anything unmapped falls into "Other / management tone".
_THEME_BY_SIGNAL_CATEGORY: dict[str, str] = {
    "growth": "Topline",
    "market_opportunity": "Topline",
    "order_book": "Topline",
    "margin": "Margins",
    "profit_quality": "Margins",
    "earnings_quality": "Margins",
    "expense": "Margins",
    "segment": "Segments",
    "business_quality": "Segments",
    "operations": "Segments",
    "cashflow": "Capex / management tone",
    "working_capital": "Capex / management tone",
    "debt": "Capex / management tone",
    "cash_quality": "Capex / management tone",
    "guidance": "Capex / management tone",
    "management": "Capex / management tone",
    "management_tone": "Capex / management tone",
    "execution": "Capex / management tone",
    "governance": "Capex / management tone",
    "strategic": "Capex / management tone",
    "valuation": "Capex / management tone",
    "market_reaction": "Capex / management tone",
    "red_flag": "Capex / management tone",
}


# Also map `intelligence_cards.card_type` so themes survive even when a card
# has no underlying signal (e.g. `result_verdict`, narrative cards).
_THEME_BY_CARD_TYPE: dict[str, str] = {
    "revenue_growth": "Topline",
    "growth_signal": "Topline",
    "order_book": "Topline",
    "margin_movement": "Margins",
    "profit_quality": "Margins",
    "earnings_quality": "Margins",
    "expense_pressure": "Margins",
    "cost_pressure": "Margins",
    "segment_performance": "Segments",
    "cash_quality": "Capex / management tone",
    "cashflow_signal": "Capex / management tone",
    "working_capital": "Capex / management tone",
    "debt_signal": "Capex / management tone",
    "solvency_signal": "Capex / management tone",
    "guidance_signal": "Capex / management tone",
    "guidance_tracker": "Capex / management tone",
    "management_signal": "Capex / management tone",
    "management_tone": "Capex / management tone",
    "analyst_concern": "Capex / management tone",
    "governance_signal": "Capex / management tone",
    "valuation_signal": "Capex / management tone",
    "market_reaction": "Capex / management tone",
    "red_flag": "Capex / management tone",
}


_ANALYST_THEMES: tuple[str, ...] = (
    "Topline",
    "Margins",
    "Segments",
    "Capex / management tone",
)


def _theme_for_signal(
    sig: GeneratedSignal,
    *,
    category_by_def_id: dict[int, str] | None = None,
) -> str:
    category = (category_by_def_id or {}).get(sig.signal_def_id, "")
    return _THEME_BY_SIGNAL_CATEGORY.get(category, "Capex / management tone")


def _theme_for_card(card: IntelligenceCard) -> str:
    return _THEME_BY_CARD_TYPE.get(card.card_type or "", "Capex / management tone")


def _direction_to_tone(direction: SignalDirection | None) -> str:
    if direction == SignalDirection.POSITIVE:
        return "positive"
    if direction == SignalDirection.NEGATIVE:
        return "negative"
    if direction == SignalDirection.MIXED:
        return "mixed"
    return "neutral"


def _tone_from_counts(counts: Counter[str]) -> str:
    if not counts:
        return "neutral"
    pos = counts.get("positive", 0)
    neg = counts.get("negative", 0)
    mix = counts.get("mixed", 0)
    if mix and (pos == 0 or neg == 0):
        return "mixed"
    if pos > 0 and neg > 0:
        return "mixed"
    if pos > 0:
        return "positive"
    if neg > 0:
        return "negative"
    return "neutral"


def _verdict_tone(sigs: list[GeneratedSignal], cards: list[IntelligenceCard]) -> str:
    counts: Counter[str] = Counter()
    for sig in sigs:
        counts[_direction_to_tone(sig.signal_direction)] += 1
    for card in cards:
        if card.card_type == "result_verdict":
            counts[_direction_to_tone(card.signal_direction)] += 2  # verdict weighs more
            continue
        counts[_direction_to_tone(card.signal_direction)] += 1
    return _tone_from_counts(counts)


def _load_signal_categories(
    db: "Session | None", sigs: list[GeneratedSignal]
) -> dict[int, str]:
    if db is None or not sigs:
        return {}
    def_ids = sorted({s.signal_def_id for s in sigs if s.signal_def_id is not None})
    if not def_ids:
        return {}
    rows = db.execute(
        select(SignalDefinition.signal_def_id, SignalDefinition.signal_category).where(
            SignalDefinition.signal_def_id.in_(def_ids)
        )
    ).all()
    return {def_id: cat for def_id, cat in rows}


def build_analyst_summary(
    sigs: list[GeneratedSignal],
    cards: list[IntelligenceCard],
    *,
    db: "Session | None" = None,
) -> dict[str, Any] | None:
    """Build the structured `AnalystSummary` payload pinned on the event page.

    Bins fired signals / published cards into four themes (Topline, Margins,
    Segments, Capex / management tone), picks the highest-priority claim per
    theme, and assigns a tone derived from the constituent directions. The
    returned shape is the dict serialized into
    ``result_verdict.calculations_json["analyst_summary"]`` and is also surfaced
    on ``EventDetailV1.analyst_summary`` for the frontend renderer.

    Signal categories live on ``SignalDefinition`` so a ``db`` session is
    required to map fired signals → theme. Without it, signals fall into the
    catch-all "Capex / management tone" bucket; cards still bin correctly
    because their ``card_type`` maps to a theme directly.

    Returns ``None`` if the event has neither fired signals nor cards.
    """

    if not sigs and not cards:
        return None

    category_by_def_id = _load_signal_categories(db, sigs)

    sentences_by_theme: dict[str, list[tuple[float, str, list[int]]]] = defaultdict(list)
    counts_by_theme: dict[str, Counter[str]] = defaultdict(Counter)

    for sig in sigs:
        theme = _theme_for_signal(sig, category_by_def_id=category_by_def_id)
        line = _signal_sentence(sig)
        if not line:
            continue
        score = float(sig.signal_score or 0)
        evidence = [sig.signal_id] if sig.signal_id else []
        sentences_by_theme[theme].append((score, line, evidence))
        counts_by_theme[theme][_direction_to_tone(sig.signal_direction)] += 1

    for card in cards:
        if card.card_type == "result_verdict":
            continue
        theme = _theme_for_card(card)
        # Cards are scored on `card_priority` (0-100); rescale into a roughly
        # comparable signal_score band so the highest-priority card and the
        # highest-scoring signal compete fairly.
        priority = float(card.card_priority or 0)
        score = priority / 4.0  # signals scores typically 5–35
        headline = card.headline or card.one_line_summary or ""
        line = _sentence(headline)
        if not line:
            continue
        sentences_by_theme[theme].append((score, line, [card.card_id]))
        counts_by_theme[theme][_direction_to_tone(card.signal_direction)] += 1

    themes_payload: list[dict[str, Any]] = []
    for theme in _ANALYST_THEMES:
        rows = sentences_by_theme.get(theme, [])
        if not rows:
            continue
        rows.sort(key=lambda r: r[0], reverse=True)
        _, sentence, evidence_ids = rows[0]
        tone = _tone_from_counts(counts_by_theme.get(theme, Counter()))
        themes_payload.append(
            {
                "label": theme,
                "tone": tone,
                "sentence": sentence,
                "evidence_ids": evidence_ids,
            }
        )

    if not themes_payload:
        return None

    return {
        "verdict": _verdict_tone(sigs, cards),
        "themes": themes_payload,
    }


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
