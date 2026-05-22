"""Tests for investor-facing event summary composition."""

from app.models.intelligence import GeneratedSignal, IntelligenceCard
from app.db.enums import SeverityLevel, SignalDirection
from app.services.event_summary import (
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
