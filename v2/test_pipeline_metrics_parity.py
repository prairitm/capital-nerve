"""Parity between notebook pipeline metrics and serve/builder."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from capital_nerve_db import FactStore
from capital_nerve_logic import compute_pipeline_metrics

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from serve.builder import Catalog, Period  # noqa: E402


def _seed_store(store: FactStore, ticker: str) -> None:
    periods = [
        (
            3,
            2025,
            "2025-12-31",
            {
                "revenue_from_operations": 110.0,
                "ebitda": 22.0,
                "pat": 15.0,
                "operating_profit": 20.0,
            },
        ),
        (
            3,
            2024,
            "2024-12-31",
            {
                "revenue_from_operations": 100.0,
                "ebitda": 20.0,
                "pat": 14.0,
                "operating_profit": 18.0,
            },
        ),
        (
            2,
            2025,
            "2025-09-30",
            {
                "revenue_from_operations": 105.0,
                "ebitda": 21.0,
                "pat": 14.5,
                "operating_profit": 19.0,
            },
        ),
    ]
    for quarter, fy_start_year, quarter_end, facts in periods:
        for fact_key, value in facts.items():
            store.upsert_fact(
                company_ticker=ticker,
                quarter=quarter,
                fy_start_year=fy_start_year,
                quarter_end=quarter_end,
                fact_key=fact_key,
                basis="consolidated",
                numeric_value=value,
                unit="crore",
                evidence="test",
                source_document_id="doc_1",
            )


def test_pipeline_metrics_parity_with_builder():
    tmp = tempfile.mkdtemp()
    store = FactStore(Path(tmp) / "test.db")
    ticker = "AXISBANK"
    _seed_store(store, ticker)

    builder = Catalog(store)
    period = Period(
        ticker=ticker,
        quarter=3,
        fy_start_year=2025,
        fy_label="FY2025-26",
        quarter_end="2025-12-31",
        label="Q3 FY2025-26",
    )
    built = builder.build_period(period)
    builder_metrics = {
        m["metric_key"]: m["value"]
        for m in built.metrics
        if m.get("metric_key")
    }

    base = store.load_facts(ticker, 3, 2025, "consolidated")
    prior_year = store.load_facts(ticker, 3, 2024, "consolidated")
    prior_quarter = store.load_facts(ticker, 2, 2025, "consolidated")
    raw_details = store.load_fact_details(ticker, 3, 2025, "consolidated")
    prior_year_details = store.load_fact_details(ticker, 3, 2024, "consolidated")
    prior_quarter_details = store.load_fact_details(ticker, 2, 2025, "consolidated")

    pipeline_metrics = compute_pipeline_metrics(
        base,
        prior_year,
        prior_quarter,
        period_label="Q3 FY2025-26",
        raw_details=raw_details,
        prior_year_details=prior_year_details,
        prior_quarter_details=prior_quarter_details,
    )
    pipeline_by_key = {
        m["metric_key"]: m["value"]
        for m in pipeline_metrics
        if m.get("metric_key")
    }

    for key, val in builder_metrics.items():
        assert key in pipeline_by_key, f"missing metric {key}"
        assert pipeline_by_key[key] == val, f"{key}: {pipeline_by_key[key]} != {val}"
