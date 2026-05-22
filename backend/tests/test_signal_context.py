"""Unit tests for signal detail enrichment helpers."""

from app.services.signal_context import (
    _build_rule_leaves,
    _collect_rule_metric_codes,
    _format_rule,
    _format_rule_tree,
)


def test_format_rule_simple_leaf():
    rule = {"metric": "pat_growth_yoy", "operator": ">", "threshold": 10}
    assert _format_rule(rule) == "Fires when pat growth yoy is above 10"


def test_format_rule_tree_composite():
    rule = {
        "all": [
            {"metric": "pat_growth_yoy", "operator": ">", "threshold": 10},
            {
                "any": [
                    {"metric": "other_income_to_pbt", "operator": ">", "threshold": 20},
                    {"metric": "exceptional_to_pat", "operator": ">", "threshold": 15},
                ]
            },
        ]
    }
    summary = _format_rule_tree(rule)
    assert summary is not None
    assert "pat growth yoy" in summary
    assert "other income to pbt" in summary
    assert " or " in summary


def test_collect_rule_metric_codes():
    rule = {
        "all": [
            {"metric": "pat_growth_yoy", "operator": ">", "threshold": 10},
            {"any": [{"metric": "other_income_to_pbt", "operator": ">", "threshold": 20}]},
        ]
    }
    assert _collect_rule_metric_codes(rule) == ["pat_growth_yoy", "other_income_to_pbt"]


def test_build_rule_leaves_pass_fail():
    comparisons = [
        {
            "metric_code": "pat_growth_yoy",
            "metric_name": "PAT Growth YoY",
            "current_value": 75.8,
            "previous_value": 10.0,
            "change_percent": 75.8,
            "change_bps": None,
            "unit": "%",
            "comparison_type": None,
        },
        {
            "metric_code": "other_income_to_pbt",
            "metric_name": "Other Income / PBT",
            "current_value": 28.0,
            "previous_value": 12.0,
            "change_percent": None,
            "change_bps": None,
            "unit": "%",
            "comparison_type": None,
        },
    ]
    metric_refs = [
        {
            "metric_code": "pat_growth_yoy",
            "value": 75.8,
            "unit": "%",
            "op": ">",
            "threshold": 10,
        }
    ]
    rule = {
        "all": [
            {"metric": "pat_growth_yoy", "operator": ">", "threshold": 10},
            {"metric": "other_income_to_pbt", "operator": ">", "threshold": 20},
        ]
    }
    leaves = _build_rule_leaves(metric_refs, comparisons, rule)
    assert len(leaves) == 2
    assert leaves[0]["passed"] is True
    assert leaves[1]["passed"] is True
