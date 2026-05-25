"""Sanity-bounds quarantine in the metrics stage.

Pure-function check on ``_bounds_breach_reason`` and a small stub run that
exercises the quarantine path through ``run_metrics`` would normally need
a DB. We use ``_bounds_breach_reason`` directly to lock the threshold
behaviour described in [seed_catalog._m bounds=](../app/seed/seed_catalog.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.pipeline.metrics import _bounds_breach_reason


@dataclass
class _StubMetricDef:
    metric_code: str
    unit: str
    validation_min: float | None
    validation_max: float | None


def _md(code: str, unit: str, *, lo: float | None, hi: float | None) -> _StubMetricDef:
    return _StubMetricDef(metric_code=code, unit=unit, validation_min=lo, validation_max=hi)


def test_value_inside_bounds_is_not_quarantined():
    md = _md("ebitda_margin", "%", lo=-50.0, hi=100.0)
    assert _bounds_breach_reason(md, 25.0) is None


def test_value_above_max_is_quarantined():
    md = _md("ebitda_margin", "%", lo=-50.0, hi=100.0)
    reason = _bounds_breach_reason(md, 138.6)
    assert reason is not None
    assert "above plausible maximum" in reason
    assert "100" in reason


def test_value_below_min_is_quarantined():
    md = _md("pat_margin", "%", lo=-50.0, hi=100.0)
    reason = _bounds_breach_reason(md, -90.0)
    assert reason is not None
    assert "below plausible minimum" in reason


def test_unbounded_metric_never_quarantines():
    md = _md("fcf", "crore", lo=None, hi=None)
    assert _bounds_breach_reason(md, 1_000_000.0) is None


def test_user_reported_segment_margin_is_quarantined():
    """Regression: 1927% Segment Margin from the analyst review must be quarantined."""
    md = _md("primary_segment_margin", "%", lo=-100.0, hi=100.0)
    reason = _bounds_breach_reason(md, 1927.3)
    assert reason is not None


def test_user_reported_revenue_qoq_is_quarantined():
    """Regression: 708.7% Revenue Growth QoQ must be quarantined."""
    md = _md("revenue_qoq_growth", "%", lo=-100.0, hi=300.0)
    reason = _bounds_breach_reason(md, 708.7)
    assert reason is not None
