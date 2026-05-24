"""Composite-rule signal evaluation tests.

The evaluator is a pure function of `rule_json` and a dict of
`metric_code -> CalculatedMetric`. We stub `CalculatedMetric` so we don't
need a database here.

Snapshot test: the four single-leaf signals seeded since v1
(`weak_profit_quality_other_income`, `margin_compression`, `revenue_acceleration`,
`finance_cost_pressure`) must continue to fire on values that previously
fired them in the demo.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.pipeline.signals import _evaluate_rule


@dataclass
class _StubCM:
    metric_id: int
    metric_value: float | None
    unit: str | None


def metrics_from(values: dict[str, float | None], unit: str = "%"):
    return {
        code: _StubCM(metric_id=i + 1, metric_value=val, unit=unit)
        for i, (code, val) in enumerate(values.items())
    }


# ---------------------------------------------------------------------------
# Snapshot — pre-existing single-leaf signals
# ---------------------------------------------------------------------------


def test_weak_profit_quality_fires_above_threshold():
    rule = {"metric": "other_income_to_pbt", "operator": ">", "threshold": 20}
    metrics = metrics_from({"other_income_to_pbt": 26.0})
    outcome = _evaluate_rule(rule, metrics)
    assert outcome.fired
    assert outcome.touched[0]["metric_code"] == "other_income_to_pbt"


def test_weak_profit_quality_does_not_fire_below_threshold():
    rule = {"metric": "other_income_to_pbt", "operator": ">", "threshold": 20}
    metrics = metrics_from({"other_income_to_pbt": 14.0})
    outcome = _evaluate_rule(rule, metrics)
    assert not outcome.fired


def test_margin_compression_fires_on_negative_breach():
    rule = {"metric": "ebitda_margin_change_yoy_bps", "operator": "<", "threshold": -100}
    metrics = metrics_from({"ebitda_margin_change_yoy_bps": -250}, unit="bps")
    outcome = _evaluate_rule(rule, metrics)
    assert outcome.fired


def test_revenue_acceleration_fires_above_15_pct():
    rule = {"metric": "revenue_yoy_growth", "operator": ">", "threshold": 15}
    metrics = metrics_from({"revenue_yoy_growth": 18.0})
    outcome = _evaluate_rule(rule, metrics)
    assert outcome.fired


def test_finance_cost_pressure_fires():
    rule = {"metric": "finance_cost_burden", "operator": ">", "threshold": 25}
    metrics = metrics_from({"finance_cost_burden": 32.0})
    outcome = _evaluate_rule(rule, metrics)
    assert outcome.fired


def test_weak_profit_quality_fires_at_tuned_threshold_18():
    rule = {"metric": "other_income_to_pbt", "operator": ">", "threshold": 18}
    metrics = metrics_from({"other_income_to_pbt": 18.41})
    assert _evaluate_rule(rule, metrics).fired


def test_elevated_other_income_band_15_to_18():
    rule = {
        "all": [
            {"metric": "other_income_to_pbt", "operator": ">", "threshold": 15},
            {"metric": "other_income_to_pbt", "operator": "<", "threshold": 18},
        ]
    }
    assert _evaluate_rule(rule, metrics_from({"other_income_to_pbt": 16.0})).fired
    assert not _evaluate_rule(rule, metrics_from({"other_income_to_pbt": 18.5})).fired


def test_strong_cash_conversion_fires():
    rule = {"metric": "cfo_to_pat", "operator": ">", "threshold": 1.0}
    metrics = metrics_from({"cfo_to_pat": 1.72}, unit="x")
    assert _evaluate_rule(rule, metrics).fired


def test_modest_revenue_growth_band():
    rule = {
        "all": [
            {"metric": "revenue_yoy_growth", "operator": ">", "threshold": 0},
            {"metric": "revenue_yoy_growth", "operator": "<", "threshold": 12},
        ]
    }
    assert _evaluate_rule(rule, metrics_from({"revenue_yoy_growth": 6.0})).fired
    assert not _evaluate_rule(rule, metrics_from({"revenue_yoy_growth": 14.0})).fired


# ---------------------------------------------------------------------------
# Composite rules
# ---------------------------------------------------------------------------


def test_dirty_beat_all_with_any_branch():
    rule = {
        "all": [
            {"metric": "pat_growth_yoy", "operator": ">", "threshold": 10},
            {"any": [
                {"metric": "other_income_to_pbt", "operator": ">", "threshold": 20},
                {"metric": "exceptional_to_pat", "operator": ">", "threshold": 15},
            ]},
        ]
    }
    metrics = metrics_from(
        {
            "pat_growth_yoy": 22.0,
            "other_income_to_pbt": 28.0,
            "exceptional_to_pat": 5.0,
        }
    )
    outcome = _evaluate_rule(rule, metrics)
    assert outcome.fired
    codes = {t["metric_code"] for t in outcome.touched}
    assert "pat_growth_yoy" in codes
    assert "other_income_to_pbt" in codes


def test_dirty_beat_does_not_fire_when_pat_growth_low():
    rule = {
        "all": [
            {"metric": "pat_growth_yoy", "operator": ">", "threshold": 10},
            {"any": [
                {"metric": "other_income_to_pbt", "operator": ">", "threshold": 20},
                {"metric": "exceptional_to_pat", "operator": ">", "threshold": 15},
            ]},
        ]
    }
    metrics = metrics_from({"pat_growth_yoy": 4.0, "other_income_to_pbt": 28.0, "exceptional_to_pat": 30.0})
    outcome = _evaluate_rule(rule, metrics)
    assert not outcome.fired


def test_metric_ref_comparison():
    # receivables_growth > revenue_yoy_growth — used by channel-stuffing risk.
    rule = {
        "metric": "receivables_growth_yoy",
        "operator": ">",
        "metric_ref": "revenue_yoy_growth",
    }
    fires = metrics_from({"receivables_growth_yoy": 30.0, "revenue_yoy_growth": 12.0})
    no_fire = metrics_from({"receivables_growth_yoy": 8.0, "revenue_yoy_growth": 12.0})
    assert _evaluate_rule(rule, fires).fired
    assert not _evaluate_rule(rule, no_fire).fired


def test_not_inverts():
    rule = {"not": {"metric": "revenue_yoy_growth", "operator": ">", "threshold": 0}}
    declining = metrics_from({"revenue_yoy_growth": -5.0})
    growing = metrics_from({"revenue_yoy_growth": 5.0})
    assert _evaluate_rule(rule, declining).fired
    assert not _evaluate_rule(rule, growing).fired


def test_missing_metric_skips_silently():
    rule = {"metric": "nonexistent_metric", "operator": ">", "threshold": 0}
    outcome = _evaluate_rule(rule, {})
    assert not outcome.fired
    assert outcome.reason == "metric_missing"


def test_low_quality_growth_composite():
    # revenue up + (cfo_to_pat low OR receivables vs revenue gap large)
    rule = {
        "all": [
            {"metric": "revenue_yoy_growth", "operator": ">", "threshold": 10},
            {"any": [
                {"metric": "cfo_to_pat", "operator": "<", "threshold": 0.6},
                {"metric": "receivables_growth_minus_revenue_growth_bps", "operator": ">", "threshold": 1500},
            ]},
        ]
    }
    metrics = metrics_from(
        {
            "revenue_yoy_growth": 22.0,
            "cfo_to_pat": 0.4,
            "receivables_growth_minus_revenue_growth_bps": 100,
        },
    )
    assert _evaluate_rule(rule, metrics).fired


def test_eps_growth_fires_above_threshold():
    rule = {"metric": "eps_growth_yoy", "operator": ">", "threshold": 10}
    assert _evaluate_rule(rule, metrics_from({"eps_growth_yoy": 14.0})).fired


def test_booking_momentum_fires():
    rule = {"metric": "order_inflow_growth_yoy", "operator": ">", "threshold": 15}
    assert _evaluate_rule(rule, metrics_from({"order_inflow_growth_yoy": 22.0})).fired


def test_demand_tone_positive_fires():
    rule = {"metric": "concall_demand_score", "operator": ">", "threshold": 45}
    assert _evaluate_rule(rule, metrics_from({"concall_demand_score": 50.0}, unit="score")).fired


def test_material_order_win_fires():
    rule = {"metric": "new_order_to_ttm_revenue", "operator": ">", "threshold": 0.05}
    assert _evaluate_rule(rule, metrics_from({"new_order_to_ttm_revenue": 0.08}, unit="x")).fired
