"""Unit tests for the cross-statement + drift validator.

The full pipeline path is exercised in the integration suite; these tests
poke each of the three rules in isolation by stubbing out the
``Session.execute`` lookups so we do not need a live DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.pipeline import metric_validation


@dataclass
class _StubMetric:
    metric_value: float | None
    confidence_score: float | None = None
    is_quarantined: bool = False
    quarantine_reason: str | None = None


@dataclass
class _StubDef:
    metric_code: str
    unit: str | None


class _StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _StubSession:
    """Replays canned results for the two queries the validator runs."""

    def __init__(
        self,
        facts: dict[str, float],
        metrics: list[tuple[_StubMetric, _StubDef]],
    ) -> None:
        self._fact_rows = [(code, value) for code, value in facts.items()]
        self._metric_rows = metrics
        self._call = 0

    def execute(self, _stmt):  # noqa: ANN001 — runtime SQL statement
        self._call += 1
        if self._call == 1:
            return _StubResult(self._fact_rows)
        return _StubResult(self._metric_rows)


def test_pat_exceeds_revenue_is_flagged() -> None:
    """A segment-vs-consolidated mismatch yields PAT > Revenue."""
    db = _StubSession(
        facts={"revenue_from_operations": 1000.0, "pat": 1200.0},
        metrics=[],
    )
    report = metric_validation.validate_calculated_metrics(
        db, company_id=1, period_id=1
    )
    assert any(
        b["rule"] == "pat <= revenue"
        for b in report.cross_statement_breaches
    )


def test_clean_facts_pass_cross_statement_check() -> None:
    db = _StubSession(
        facts={
            "revenue_from_operations": 1000.0,
            "pat": 80.0,
            "ebitda": 200.0,
        },
        metrics=[],
    )
    report = metric_validation.validate_calculated_metrics(
        db, company_id=1, period_id=1
    )
    assert report.cross_statement_breaches == []


def test_recompute_drift_catches_stale_pat_margin() -> None:
    """Stored pat_margin must match facts within 2 pp tolerance."""
    db = _StubSession(
        facts={"revenue_from_operations": 1000.0, "pat": 80.0},
        metrics=[(_StubMetric(metric_value=60.8), _StubDef("pat_margin", "%"))],
    )
    report = metric_validation.validate_calculated_metrics(
        db, company_id=1, period_id=1
    )
    assert any(d["metric_code"] == "pat_margin" for d in report.recompute_drift)


def test_growth_review_gate_fires_on_extreme_value() -> None:
    db = _StubSession(
        facts={},
        metrics=[
            (
                _StubMetric(metric_value=-99.8),
                _StubDef("revenue_qoq_growth", "%"),
            ),
            (
                _StubMetric(metric_value=12.5),
                _StubDef("ebitda_margin", "%"),
            ),
        ],
    )
    db._fact_rows = [
        ("revenue_from_operations", 100.0),
    ]
    report = metric_validation.validate_calculated_metrics(
        db, company_id=1, period_id=1
    )
    # -99.8% is below the 500% review threshold — no growth_review entry.
    assert report.growth_review == []


def test_apply_validation_actions_quarantines_drifted_margin() -> None:
    cm = _StubMetric(metric_value=60.8)
    md = _StubDef("pat_margin", "%")

    class _MetricsOnlySession:
        def __init__(self, metrics: list[tuple[_StubMetric, _StubDef]]) -> None:
            self._metrics = metrics

        def execute(self, _stmt):  # noqa: ANN001
            return _StubResult(self._metrics)

        def flush(self) -> None:
            pass

    db = _MetricsOnlySession([(cm, md)])
    report = metric_validation.MetricValidationReport(
        recompute_drift=[
            {
                "metric_code": "pat_margin",
                "expected": 8.0,
                "actual": 60.8,
                "drift_pp": 52.8,
            }
        ]
    )
    n = metric_validation.apply_validation_actions(
        db, company_id=1, period_id=1, report=report
    )
    assert n == 1
    assert cm.is_quarantined is True
    assert cm.quarantine_reason is not None


def test_growth_review_gate_blocks_thousand_percent_jump() -> None:
    db = _StubSession(
        facts={},
        metrics=[
            (
                _StubMetric(metric_value=1500.0),
                _StubDef("revenue_qoq_growth", "%"),
            ),
        ],
    )
    report = metric_validation.validate_calculated_metrics(
        db, company_id=1, period_id=1
    )
    assert any(g["metric_code"] == "revenue_qoq_growth" for g in report.growth_review)
