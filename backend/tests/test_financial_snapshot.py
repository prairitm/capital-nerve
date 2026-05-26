"""Unit tests for snapshot YoY delta semantics and margin resolution."""

import pytest

from app.services.financial_snapshot import (
    margin_from_facts,
    snapshot_yoy_delta,
)


def test_margin_yoy_is_bps_not_relative_pct():
    cur, prev = 17.8, 12.7
    yoy_pct, yoy_bps = snapshot_yoy_delta("ebitda_margin", "%", cur, prev)
    assert yoy_pct is None
    assert yoy_bps == pytest.approx(510.0)


def test_revenue_yoy_is_relative_pct():
    cur, prev = 265000.0, 239000.0
    yoy_pct, yoy_bps = snapshot_yoy_delta("revenue_from_operations", "Cr", cur, prev)
    assert yoy_bps is None
    assert yoy_pct is not None
    assert 10.0 < yoy_pct < 11.0


def test_margin_from_facts():
    facts = {"ebitda": 47150.0, "revenue_from_operations": 265000.0}
    assert margin_from_facts(facts, "ebitda_margin") == pytest.approx(17.7925, rel=1e-3)
