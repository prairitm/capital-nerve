"""Tests for investor-facing event summary composition."""

from app.models.intelligence import GeneratedSignal, IntelligenceCard
from app.db.enums import SeverityLevel, SignalDirection
from app.services.event_summary import (
    build_analyst_summary,
    build_event_summary_text,
    is_pipeline_placeholder_summary,
)


def _sig(headline: str, explanation: str | None = None, direction: SignalDirection = SignalDirection.NEGATIVE):
    return GeneratedSignal(
        signal_id=1,
        company_id=1,
        signal_def_id=1,
        signal_direction=direction,
        severity=SeverityLevel.HIGH,
        headline=headline,
        explanation=explanation,
        signal_score=90.0,
    )


def test_placeholder_detection():
    assert is_pipeline_placeholder_summary("Pipeline-generated brief: 1 cards covering debt_signal.")
    assert not is_pipeline_placeholder_summary("Revenue grew 12% YoY.")


def test_build_from_signal_explanation_strips_trigger():
    sig = _sig(
        "Debt Signal: 2.1x",
        explanation="Leverage elevated. Triggered at 2.1x (rule: debt_equity).",
    )
    text = build_event_summary_text([sig], [])
    assert text == "Leverage elevated."
    assert "Pipeline-generated" not in text
    assert "Triggered at" not in text


def test_build_from_multiple_signals():
    sigs = [
        _sig("Dirty Beat: 75.8%", "PAT growth flattered by other income.", SignalDirection.MIXED),
        _sig("Margin Pressure: -120 bps", "EBITDA margin compressed.", SignalDirection.NEGATIVE),
    ]
    text = build_event_summary_text(sigs, [])
    assert "PAT growth" in text
    assert "EBITDA margin" in text


def _card(card_type: str, headline: str, *, direction: SignalDirection, priority: int = 70):
    return IntelligenceCard(
        card_id=card_type.__hash__() & 0xFFFF,
        company_id=1,
        card_type=card_type,
        headline=headline,
        one_line_summary=headline,
        signal_direction=direction,
        severity=SeverityLevel.HIGH,
        card_priority=priority,
    )


def test_analyst_summary_groups_cards_by_theme():
    cards = [
        _card("revenue_growth", "Revenue grew 12% YoY", direction=SignalDirection.POSITIVE, priority=90),
        _card("margin_movement", "EBITDA margin compressed 180 bps", direction=SignalDirection.NEGATIVE, priority=85),
        _card("segment_performance", "Primary segment EBIT held 20%", direction=SignalDirection.POSITIVE, priority=70),
        _card("guidance_signal", "Management held FY guidance", direction=SignalDirection.NEUTRAL, priority=50),
    ]
    summary = build_analyst_summary([], cards)
    assert summary is not None
    labels = [t["label"] for t in summary["themes"]]
    assert labels == ["Topline", "Margins", "Segments", "Capex / management tone"]
    assert summary["themes"][0]["tone"] == "positive"
    assert summary["themes"][1]["tone"] == "negative"


def test_analyst_summary_verdict_mixed_when_directions_clash():
    cards = [
        _card("revenue_growth", "Revenue grew 8% YoY", direction=SignalDirection.POSITIVE, priority=80),
        _card("margin_movement", "EBITDA margin compressed", direction=SignalDirection.NEGATIVE, priority=80),
    ]
    summary = build_analyst_summary([], cards)
    assert summary is not None
    assert summary["verdict"] == "mixed"


def test_analyst_summary_returns_none_for_empty_event():
    assert build_analyst_summary([], []) is None


def test_analyst_summary_excludes_result_verdict_card():
    cards = [
        _card("result_verdict", "Solid quarter", direction=SignalDirection.POSITIVE, priority=99),
        _card("revenue_growth", "Revenue grew 12% YoY", direction=SignalDirection.POSITIVE, priority=80),
    ]
    summary = build_analyst_summary([], cards)
    assert summary is not None
    assert all("Solid quarter" not in t["sentence"] for t in summary["themes"])
