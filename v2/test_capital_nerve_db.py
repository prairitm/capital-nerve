"""Tests for FactStore signal persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

from capital_nerve_db import FactStore, NO_MATERIAL_SIGNAL


def _store() -> FactStore:
    tmp = tempfile.mkdtemp()
    return FactStore(Path(tmp) / "test.db")


def test_get_trend_alias_aware_finds_canonical_key():
    store = _store()
    store.upsert_fact(
        company_ticker="TCS",
        quarter=1,
        fy_start_year=2025,
        quarter_end="2025-06-30",
        fact_key="revenue_from_operations",
        basis="consolidated",
        numeric_value=100.0,
        unit="crore",
        evidence="rev",
        source_document_id="doc_1",
    )
    series = store.get_trend_alias_aware("TCS", "revenue", "consolidated", n=4)
    assert len(series) == 1
    assert series[0]["value"] == 100.0
    assert series[0]["label"] == "Q1 FY2025-26"


def test_persist_and_load_signals():
    store = _store()
    store.upsert_filing(
        document_id="doc_1",
        company_ticker="TCS",
        sha256="abc",
        title="Q4",
        quarter=4,
        fy_start_year=2025,
        quarter_end="2026-03-31",
        ingested_at="2026-01-01T00:00:00+00:00",
    )
    for quarter, fy_start_year, quarter_end, revenue in (
        (3, 2025, "2025-12-31", 950.0),
        (4, 2025, "2026-03-31", 900.0),
    ):
        store.upsert_fact(
            company_ticker="TCS",
            quarter=quarter,
            fy_start_year=fy_start_year,
            quarter_end=quarter_end,
            fact_key="revenue_from_operations",
            basis="consolidated",
            numeric_value=revenue,
            unit="crore",
            evidence=None,
            source_document_id="doc_1",
        )
    signals = [
        {
            "signal_key": "revenue_decline_qoq",
            "severity": "watch",
            "headline": "Revenue Decline (QoQ)",
            "rationale": "Revenue contracted. (revenue_qoq_growth=-5.26)",
            "metric_keys": ["revenue_qoq_growth"],
            "category": "growth",
            "direction": "NEGATIVE",
        }
    ]
    metrics = [
        {
            "metric_key": "revenue_qoq_growth",
            "value": -5.26,
            "formula_evaluated": "(revenue - revenue_pq) / revenue_pq * 100",
        }
    ]

    result = store.persist_period_signals(
        company_ticker="TCS",
        quarter=4,
        fy_start_year=2025,
        quarter_end="2026-03-31",
        basis="consolidated",
        signals=signals,
        metrics=metrics,
        catalog_version="0.1.0",
    )

    assert result["persisted_count"] == 1
    assert result["primary_signal_key"] == "revenue_decline_qoq"

    loaded = store.load_signals("TCS", 4, 2025, "consolidated")
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0]["signal_key"] == "revenue_decline_qoq"
    assert loaded[0]["metric_keys"] == ["revenue_qoq_growth"]
    assert loaded[0]["trigger_values"] == {"revenue_qoq_growth": -5.26}
    snapshot = loaded[0]["metric_snapshots"]["revenue_qoq_growth"]
    assert snapshot["value"] == -5.26
    assert snapshot["inputs"] == [
        {
            "var": "revenue",
            "fact_key": "revenue_from_operations",
            "scope": "CURRENT",
            "value": 900.0,
        },
        {
            "var": "revenue_pq",
            "fact_key": "revenue_from_operations",
            "scope": "PQ",
            "value": 950.0,
        },
    ]
    assert loaded[0]["rule"] == {
        "metric_key": "revenue_qoq_growth",
        "op": "<",
        "value": 0,
    }
    assert loaded[0]["rule_text"] == "revenue_qoq_growth < 0"


def test_skips_no_material_change_and_clears_stale():
    store = _store()
    signals = [
        {
            "signal_key": "margin_expansion",
            "severity": "watch",
            "headline": "Margin Expansion",
            "rationale": "Expanded.",
            "metric_keys": ["ebitda_margin_change_yoy_bps"],
            "category": "margin",
            "direction": "POSITIVE",
        }
    ]
    store.persist_period_signals(
        company_ticker="TCS",
        quarter=4,
        fy_start_year=2025,
        quarter_end="2026-03-31",
        basis="consolidated",
        signals=signals,
        metrics=[],
        catalog_version="0.1.0",
    )
    assert store.load_signals("TCS", 4, 2025, "consolidated")

    store.persist_period_signals(
        company_ticker="TCS",
        quarter=4,
        fy_start_year=2025,
        quarter_end="2026-03-31",
        basis="consolidated",
        signals=[
            {
                "signal_key": NO_MATERIAL_SIGNAL,
                "severity": "info",
                "headline": "No material signals",
                "rationale": "None fired",
                "metric_keys": [],
                "category": "general",
                "direction": "NEUTRAL",
            }
        ],
        metrics=[],
        catalog_version="0.1.0",
    )
    assert store.load_signals("TCS", 4, 2025, "consolidated") is None


def test_load_signals_none_when_never_persisted():
    store = _store()
    assert store.load_signals("TCS", 1, 2025, "consolidated") is None
