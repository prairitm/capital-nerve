"""Unit tests for `services/ir_discovery/periods.expand_range` (no DB)."""
from __future__ import annotations

from datetime import date

import pytest

from app.db.enums import PeriodType
from app.services.ir_discovery.periods import PeriodRangeError, expand_range


def _labels(specs) -> list[str]:
    return [s.display_label for s in specs]


def _types(specs) -> list[PeriodType]:
    return [s.period_type for s in specs]


# ---------------------------------------------------------------------------
# Quarter range
# ---------------------------------------------------------------------------


def test_quarter_range_single_quarter():
    specs = expand_range(period_from="Q3 FY25-26", period_to="Q3 FY25-26")
    assert _labels(specs) == ["Q3 FY2025-26"]
    assert _types(specs) == [PeriodType.QUARTERLY]


def test_quarter_range_inclusive_ordering():
    specs = expand_range(period_from="Q1 FY25-26", period_to="Q4 FY25-26")
    assert _labels(specs) == [
        "Q1 FY2025-26",
        "Q2 FY2025-26",
        "Q3 FY2025-26",
        "Q4 FY2025-26",
    ]


def test_quarter_range_crosses_fiscal_year():
    specs = expand_range(period_from="Q3 FY24-25", period_to="Q2 FY25-26")
    assert _labels(specs) == [
        "Q3 FY2024-25",
        "Q4 FY2024-25",
        "Q1 FY2025-26",
        "Q2 FY2025-26",
    ]


def test_quarter_range_reversed_raises():
    with pytest.raises(PeriodRangeError):
        expand_range(period_from="Q3 FY25-26", period_to="Q1 FY25-26")


def test_quarter_range_unparseable_raises():
    with pytest.raises(PeriodRangeError):
        expand_range(period_from="garbage", period_to="Q3 FY25-26")


def test_quarter_range_partial_inputs_raise():
    with pytest.raises(PeriodRangeError):
        expand_range(period_from="Q1 FY25-26")


# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------


def test_date_range_full_fiscal_year():
    specs = expand_range(start_date=date(2024, 4, 1), end_date=date(2025, 3, 31))
    assert _labels(specs) == [
        "Q1 FY2024-25",
        "Q2 FY2024-25",
        "Q3 FY2024-25",
        "Q4 FY2024-25",
    ]


def test_date_range_partial_quarter_inclusion():
    # Mid-Q1 FY25 -> mid-Q3 FY25 picks up Q1, Q2, Q3.
    specs = expand_range(start_date=date(2025, 5, 15), end_date=date(2025, 11, 15))
    assert _labels(specs) == [
        "Q1 FY2025-26",
        "Q2 FY2025-26",
        "Q3 FY2025-26",
    ]


def test_date_range_reversed_raises():
    with pytest.raises(PeriodRangeError):
        expand_range(start_date=date(2025, 12, 31), end_date=date(2024, 4, 1))


# ---------------------------------------------------------------------------
# Last-N quarters
# ---------------------------------------------------------------------------


def test_last_n_quarters_walks_back_from_today():
    specs = expand_range(last_quarters=4, today=date(2026, 2, 15))  # mid Q4 FY25-26
    assert _labels(specs) == [
        "Q1 FY2025-26",
        "Q2 FY2025-26",
        "Q3 FY2025-26",
        "Q4 FY2025-26",
    ]


def test_last_n_quarters_zero_or_negative_raises():
    with pytest.raises(PeriodRangeError):
        expand_range(last_quarters=0)
    with pytest.raises(PeriodRangeError):
        expand_range(last_quarters=-1)


# ---------------------------------------------------------------------------
# Mode validation
# ---------------------------------------------------------------------------


def test_no_mode_raises():
    with pytest.raises(PeriodRangeError):
        expand_range()


def test_two_modes_raises():
    with pytest.raises(PeriodRangeError):
        expand_range(period_from="Q1 FY25-26", period_to="Q2 FY25-26", last_quarters=2)


# ---------------------------------------------------------------------------
# include_annual
# ---------------------------------------------------------------------------


def test_include_annual_inserts_after_q4():
    specs = expand_range(
        period_from="Q3 FY24-25", period_to="Q1 FY25-26", include_annual=True
    )
    labels = _labels(specs)
    types = _types(specs)
    # Q3 FY24-25, Q4 FY24-25, FY24-25 (annual), Q1 FY25-26
    assert labels == [
        "Q3 FY2024-25",
        "Q4 FY2024-25",
        "FY2024-25",
        "Q1 FY2025-26",
    ]
    assert types == [
        PeriodType.QUARTERLY,
        PeriodType.QUARTERLY,
        PeriodType.ANNUAL,
        PeriodType.QUARTERLY,
    ]


def test_include_annual_no_q4_in_range():
    specs = expand_range(
        period_from="Q1 FY25-26", period_to="Q3 FY25-26", include_annual=True
    )
    # No Q4 in window -> no annual spec injected.
    assert all(s.period_type == PeriodType.QUARTERLY for s in specs)
    assert len(specs) == 3


def test_include_annual_dedup_per_fy():
    # Two-FY window with both Q4s -> exactly one ANNUAL per FY, in the right slot.
    specs = expand_range(
        period_from="Q3 FY24-25", period_to="Q4 FY25-26", include_annual=True
    )
    labels = _labels(specs)
    assert labels.count("FY2024-25") == 1
    assert labels.count("FY2025-26") == 1
    assert labels.index("FY2024-25") == labels.index("Q4 FY2024-25") + 1
    assert labels.index("FY2025-26") == labels.index("Q4 FY2025-26") + 1
