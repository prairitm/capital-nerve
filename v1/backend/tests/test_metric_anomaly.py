"""Historical-anomaly check in ``services/pipeline/metric_anomaly``.

The real DB schema uses Postgres JSONB columns so we cannot stand up the
metrics models on SQLite. Instead these tests fake the session interface
``check_anomaly`` actually relies on — ``db.execute(select(...))`` returning
scalars over the historical metric_value rows — and exercise the decision
logic directly. The goal is to keep the analyst-trust regression (RELIANCE
Q2 FY25 60.8 % PAT margin) wired to a green test.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.pipeline.metric_anomaly import (
    AnomalyReport,
    _MIN_HISTORY,
    check_anomaly,
    _median,
)


@dataclass
class _StubMetricDef:
    metric_code: str
    unit: str = "%"
    metric_def_id: int = 1


class _StubScalars:
    """Mimics the ``Result.scalars()`` iterator over metric values."""

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def __iter__(self):
        return iter(self._values)


class _StubResult:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def scalars(self) -> _StubScalars:
        return _StubScalars(self._values)


class _StubSession:
    """Tiny session-like object that returns a canned history.

    ``check_anomaly`` calls ``db.execute(select(...)).scalars()``; we only
    need to honour that one shape.
    """

    def __init__(self, history: list[float]) -> None:
        self._history = history

    def execute(self, _stmt):
        return _StubResult(self._history)


def test_median_handles_even_and_odd_lengths():
    assert _median([1, 2, 3]) == 2
    assert _median([1, 2, 3, 4]) == 2.5
    assert _median([]) == 0.0


def test_below_minimum_history_returns_none():
    md = _StubMetricDef(metric_code="pat_margin")
    db = _StubSession(history=[7.5])  # only 1 prior, _MIN_HISTORY is 3
    assert _MIN_HISTORY >= 3  # contract guard
    report = check_anomaly(db, company_id=42, metric_def=md, value=60.8, current_period_id=999)
    assert report is None


def test_reliance_q2_60_8_pat_margin_is_flagged():
    """Regression: PAT margin 60.8 % vs ~7 % company history must trip the check."""
    md = _StubMetricDef(metric_code="pat_margin")
    db = _StubSession(history=[7.5, 7.8, 6.3, 8.0, 7.9, 11.3, 6.8, 7.5])
    report = check_anomaly(db, company_id=46, metric_def=md, value=60.8, current_period_id=999)
    assert isinstance(report, AnomalyReport)
    assert report.sample_size == 8
    assert "historical median" in report.reason.lower()


def test_in_band_margin_value_is_not_flagged():
    md = _StubMetricDef(metric_code="pat_margin")
    db = _StubSession(history=[7.5, 7.8, 6.3, 8.0, 7.9, 11.3])
    report = check_anomaly(db, company_id=46, metric_def=md, value=10.5, current_period_id=999)
    assert report is None


def test_growth_blow_out_is_flagged():
    md = _StubMetricDef(metric_code="revenue_qoq_growth")
    db = _StubSession(history=[2.5, -3.1, 4.0, 1.2, -0.8, 3.4])
    report = check_anomaly(db, company_id=46, metric_def=md, value=120.0, current_period_id=999)
    assert report is not None


def test_non_guarded_metric_returns_none_even_for_huge_value():
    md = _StubMetricDef(metric_code="effective_tax_rate")
    db = _StubSession(history=[20, 22, 19, 25, 21])
    report = check_anomaly(db, company_id=46, metric_def=md, value=95.0, current_period_id=999)
    assert report is None


def test_segment_margin_far_from_median_is_flagged():
    md = _StubMetricDef(metric_code="primary_segment_margin")
    db = _StubSession(history=[18.0, 19.5, 17.2, 20.1, 18.8])
    report = check_anomaly(db, company_id=46, metric_def=md, value=70.0, current_period_id=999)
    assert report is not None
