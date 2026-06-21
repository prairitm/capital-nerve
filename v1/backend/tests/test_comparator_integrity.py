"""Comparator-integrity guard in `InputResolver`.

Pure-function tests of ``_is_aggregate_column``. The integration with
``InputResolver._comparator_value`` is exercised end-to-end by the pipeline
tests; here we lock the heuristic.
"""
from __future__ import annotations

import pytest

from app.services.pipeline.inputs import _is_aggregate_column


@pytest.mark.parametrize(
    "label",
    [
        "9M FY24-25",
        "Nine Months Ended",
        "nine-month",
        "YTD",
        "Year to Date",
        "Year-To-Date",
        "H1 FY25",
        "half year",
        "Full Year",
        "FY 2024-25",
        "Annual",
    ],
)
def test_aggregate_columns_are_flagged(label: str) -> None:
    assert _is_aggregate_column(label), f"{label!r} should be flagged"


@pytest.mark.parametrize(
    "label",
    [
        "Quarter Ended",
        "Q3 FY24-25",
        "Q2 FY25",
        "Three Months Ended",
        None,
        "",
    ],
)
def test_quarter_columns_are_allowed(label: str | None) -> None:
    assert not _is_aggregate_column(label), f"{label!r} should NOT be flagged"
