"""Tests for v2 signal-detail projection consumed by SignalDetailPage."""

from serve.mapper import (
    _build_rule_leaves,
    _clean_rationale,
    _metric_comparisons,
    _trigger_metric_row,
)


def test_clean_rationale_strips_metric_parenthetical():
    assert _clean_rationale("Revenue grew. (revenue_qoq_growth=10.71)") == "Revenue grew."


def test_human_rule_formula():
    from serve.mapper import _human_rule_formula

    rule = {"metric_key": "revenue_qoq_growth", "op": ">", "value": 5}
    assert _human_rule_formula(rule) == "Revenue QoQ Growth > 5.0%"


def test_build_rule_leaves_enriched_shape():
    rule = {"metric_key": "revenue_qoq_growth", "op": ">", "value": 5}
    comparisons = [
        {
            "metric_code": "revenue_qoq_growth",
            "metric_name": "Revenue QoQ",
            "current_value": 10.71,
            "previous_value": None,
            "change_percent": 10.71,
            "change_bps": None,
            "unit": "%",
            "comparison_type": "qoq",
        }
    ]
    by_key = {"revenue_qoq_growth": {"metric_key": "revenue_qoq_growth", "value": 10.71}}

    leaves = _build_rule_leaves(["revenue_qoq_growth"], comparisons, by_key, rule)

    assert len(leaves) == 1
    leaf = leaves[0]
    assert leaf["metric_code"] == "revenue_qoq_growth"
    assert leaf["metric_name"] == "Revenue QoQ"
    assert leaf["current_value"] == 10.71
    assert leaf["unit"] == "%"
    assert leaf["passed"] is True
    assert leaf["rule_text"] == "Requires above 5"


def test_metric_comparisons_use_growth_metric_code():
    built_metrics = [
        {
            "metric_key": "revenue_qoq_growth",
            "derivation": "qoq",
            "value": 10.71,
            "inputs": ["revenue_from_operations"],
            "input_details": [],
        }
    ]

    class _Built:
        metrics = built_metrics

    rows = _metric_comparisons(_Built())
    assert rows[0]["metric_code"] == "revenue_qoq_growth"
    assert rows[0]["current_value"] == 10.71
    assert rows[0]["unit"] == "%"


def test_trigger_metric_row_matches_signal_metric():
    comparisons = [
        {"metric_code": "revenue_qoq_growth", "metric_name": "Revenue QoQ", "current_value": 10.71, "unit": "%"},
        {"metric_code": "ebitda_growth_yoy", "metric_name": "EBITDA YoY", "current_value": 8.0, "unit": "%"},
    ]
    row = _trigger_metric_row(comparisons, "revenue_qoq_growth")
    assert row is not None
    assert row["metric_code"] == "revenue_qoq_growth"


def test_company_badges_format_cr():
    from serve.mapper import _company_badges

    class _Built:
        metrics = [
            {"metric_key": "revenue_yoy_pct", "value": 12.5, "derivation": "yoy"},
            {"metric_key": "ebitda_margin", "value": 14.9, "derivation": "margin"},
            {"metric_key": "pat", "value": 20616.0, "derivation": "raw", "fact_key": "pat"},
        ]

    badges = _company_badges(None, _Built())  # type: ignore[arg-type]
    pat_badge = next(b for b in badges if b["label"] == "Profit Quality")
    assert pat_badge["value"] == "20,616.00 Cr"


def test_io_metrics_includes_all_raw_facts_not_card_subset():
    from serve.mapper import _io_metrics

    class _Built:
        metrics = [
            {"fact_key": "revenue_from_operations", "value": 100, "derivation": "raw"},
            {"fact_key": "pat", "value": 10, "derivation": "raw"},
            {"fact_key": "eps_basic", "value": 1.2, "unit": "Rs", "derivation": "raw"},
            {"metric_key": "ebitda_margin", "value": 12, "derivation": "formula"},
        ]
        card_metrics = [
            {"fact_key": "revenue_from_operations", "value": 100, "derivation": "raw"},
            {"metric_key": "ebitda_margin", "value": 12, "derivation": "formula"},
        ]

    rows = _io_metrics(_Built())  # type: ignore[arg-type]
    extracted = [r for r in rows if r["source_kind"] == "extracted"]
    computed = [r for r in rows if r["source_kind"] == "computed"]
    assert len(extracted) == 3
    assert len(computed) == 1
    assert "Revenue from Operations" in {r["name"] for r in extracted}
    assert "Profit After Tax" in {r["name"] for r in extracted}


def test_has_material_signals():
    from serve.mapper import _has_material_signals

    class _Built:
        def __init__(self, signals):
            self.signals = signals

    assert _has_material_signals(_Built([{"signal_key": "revenue_growth_qoq"}]))
    assert not _has_material_signals(_Built([{"signal_key": "no_material_change"}]))
    assert _has_material_signals(
        _Built([{"signal_key": "no_material_change"}, {"signal_key": "revenue_growth_qoq"}])
    )
