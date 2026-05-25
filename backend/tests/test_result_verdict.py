"""Pipeline `result_verdict` card generation (no seed dependency)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.db.enums import EventType, SeverityLevel, SignalDirection
from app.models.events import CompanyEvent, SourceDocument
from app.models.intelligence import GeneratedSignal
from app.services.pipeline.cards import _verdict_headline, run_result_verdict


def _signal(
    *,
    direction: SignalDirection = SignalDirection.NEGATIVE,
    severity: SeverityLevel = SeverityLevel.HIGH,
) -> GeneratedSignal:
    return GeneratedSignal(
        signal_id=1,
        company_id=1,
        signal_def_id=1,
        event_id=10,
        document_id=20,
        signal_direction=direction,
        severity=severity,
        headline="Margin Pressure: -120 bps",
        explanation="EBITDA margin compressed.",
        confidence_score=88.0,
        signal_score=75.0,
    )


def test_run_result_verdict_skips_non_quarterly_events() -> None:
    event = CompanyEvent(
        event_id=10,
        company_id=1,
        period_id=1,
        event_type=EventType.CONCALL_TRANSCRIPT,
        event_title="Concall",
        event_date=date.today(),
    )
    doc = SourceDocument(
        document_id=20,
        event_id=10,
        company_id=1,
        period_id=1,
        document_type="CONCALL_TRANSCRIPT",
        document_title="Concall",
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    assert run_result_verdict(db, document=doc, event=event, signals=[_signal()], publish=True) is None


def test_run_result_verdict_builds_summary_card_fields() -> None:
    event = CompanyEvent(
        event_id=10,
        company_id=1,
        period_id=1,
        event_type=EventType.QUARTERLY_RESULT,
        event_title="Q4 Results",
        event_date=date.today(),
        overall_signal=SignalDirection.NEGATIVE,
        overall_severity=SeverityLevel.HIGH,
    )
    doc = SourceDocument(
        document_id=20,
        event_id=10,
        company_id=1,
        period_id=1,
        document_type="FINANCIAL_RESULT",
        document_title="Q4 Results",
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    card = run_result_verdict(
        db,
        document=doc,
        event=event,
        signals=[_signal()],
        publish=True,
    )
    assert card is not None
    assert card.card_type == "result_verdict"
    assert card.signal_id is None
    assert card.is_published is True
    assert card.one_line_summary
    assert "Pipeline-generated brief" not in (card.one_line_summary or "")


def test_verdict_headline_separates_tone_from_materiality() -> None:
    event = CompanyEvent(
        event_id=10,
        company_id=1,
        event_type=EventType.QUARTERLY_RESULT,
        event_title="Q4 Results",
        event_date=date.today(),
    )

    constructive_critical = _verdict_headline(
        SignalDirection.POSITIVE, SeverityLevel.CRITICAL, event
    )
    weak_critical = _verdict_headline(
        SignalDirection.NEGATIVE, SeverityLevel.CRITICAL, event
    )
    in_line_low = _verdict_headline(
        SignalDirection.NEUTRAL, SeverityLevel.LOW, event
    )

    # POSITIVE + CRITICAL should never read "Critical-risk" — that combo was
    # the broken case the Phase 3 split fixes.
    assert "Critical-risk" not in constructive_critical
    assert constructive_critical.startswith("Constructive quarter")
    assert "market-moving" in constructive_critical
    # NEGATIVE + CRITICAL still leads with the weak tone, not severity.
    assert weak_critical.startswith("Weak quarter")
    assert "market-moving" in weak_critical
    # NEUTRAL + LOW shows the materiality qualifier "routine".
    assert in_line_low.startswith("In-line quarter")
    assert "routine" in in_line_low
