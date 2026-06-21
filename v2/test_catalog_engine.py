"""Tests for JSON catalog loading and evaluation."""

from __future__ import annotations

from catalog_engine import (
    ScopeContext,
    compute_catalog_metrics,
    evaluate_catalog_signals,
    rule_leaves,
    to_crore_equivalent,
)
from catalog_loader import allowed_extraction_keys, get_catalog, load_catalog


def test_catalog_loads():
    catalog = load_catalog(reload=True)
    assert catalog.version == "0.1.0"
    assert "revenue_from_operations" in catalog.facts
    assert "clean_beat" in catalog.signals
    assert "revenue" in allowed_extraction_keys()


def test_compute_revenue_yoy_and_margin():
    ctx = ScopeContext(
        current={"revenue": 110.0, "ebitda": 22.0},
        prior_year={"revenue": 100.0, "ebitda": 20.0},
        prior_quarter={"revenue": 105.0, "ebitda": 21.0},
    )
    metrics = compute_catalog_metrics(ctx, period_label="Q1 FY26")
    by_key = {m["metric_key"]: m for m in metrics if "metric_key" in m}
    assert by_key["revenue_yoy_growth"]["value"] == 10.0
    assert by_key["ebitda_margin"]["value"] == 20.0
    assert by_key["revenue_yoy_pct"]["value"] == 10.0


def test_raw_rows_use_fact_key():
    ctx = ScopeContext(
        current={"revenue": 110.0},
        prior_year={},
        prior_quarter={},
    )
    raw_details = {
        "revenue": {
            "numeric_value": 110.0,
            "unit": "crore",
            "evidence": "Revenue",
            "source_document_id": "doc_1",
        }
    }
    metrics = compute_catalog_metrics(
        ctx, period_label="Q1 FY26", raw_details=raw_details
    )
    raw = [m for m in metrics if m.get("derivation") == "raw"]
    assert len(raw) == 1
    assert raw[0]["fact_key"] == "revenue_from_operations"


def test_compute_revenue_yoy_with_mixed_units():
    ctx = ScopeContext.from_fact_details(
        current={
            "revenue_from_operations": {
                "numeric_value": 40898.41,
                "unit": "crore",
            }
        },
        prior_year={
            "revenue_from_operations": {
                "numeric_value": 3895917.0,
                "unit": "lacs",
            }
        },
        prior_quarter={},
    )
    metrics = compute_catalog_metrics(ctx, period_label="Q3 FY26")
    by_key = {m["metric_key"]: m for m in metrics if "metric_key" in m}
    assert by_key["revenue_yoy_growth"]["value"] == 4.98


def test_to_crore_equivalent_converts_lacs():
    assert to_crore_equivalent(3895917.0, "lacs") == 38959.17


def test_clean_beat_signal_fires():
    metrics = [
        {"metric_key": "revenue_yoy_growth", "value": 12.0},
        {"metric_key": "ebitda_growth_yoy", "value": 10.0},
        {"metric_key": "pat_growth_yoy", "value": 9.0},
        {"metric_key": "other_income_to_pbt", "value": 5.0},
    ]
    sigs = evaluate_catalog_signals(metrics, catalog=get_catalog())
    clean_beat = next(s for s in sigs if s["signal_key"] == "clean_beat")
    assert clean_beat["rule_text"]
    assert len(rule_leaves(clean_beat["rule"])) == 4
