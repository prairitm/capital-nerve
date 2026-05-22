"""Pipeline `result_verdict` card generation (no seed dependency)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.db.enums import EventType, SeverityLevel, SignalDirection
from app.models.events import CompanyEvent, SourceDocument
from app.models.intelligence import GeneratedSignal
from app.services.pipeline.cards import run_result_verdict


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
