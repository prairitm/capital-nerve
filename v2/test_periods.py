"""Tests for Indian FY period utilities."""

from __future__ import annotations

from datetime import date

from periods import (
    ReportingPeriod,
    detect_period_from_filename,
    format_fy_label,
    format_quarterly_label,
    fy_start_year_from_date,
    legacy_fy_end_to_start,
    reporting_period_from_date,
    resolve_period_label,
)


def test_fy_start_year_from_date():
    assert fy_start_year_from_date(date(2024, 12, 31)) == 2024
    assert fy_start_year_from_date(date(2025, 3, 31)) == 2024
    assert fy_start_year_from_date(date(2025, 6, 30)) == 2025


def test_format_fy_label():
    assert format_fy_label(2024) == "FY2024-25"
    assert format_quarterly_label(3, 2024) == "Q3 FY2024-25"


def test_detect_period_from_filename():
    rp = detect_period_from_filename("Q3_FY2024-25.pdf")
    assert rp is not None
    assert rp.quarter == 3
    assert rp.fy_start_year == 2024
    assert rp.fy_label == "FY2024-25"
    assert rp.label == "Q3 FY2024-25"
    assert rp.quarter_end == "2024-12-31"


def test_resolve_period_label_canonical():
    rp = resolve_period_label("Q3 FY2024-25")
    assert rp is not None
    assert rp.fy_start_year == 2024


def test_resolve_period_label_legacy_short():
    rp = resolve_period_label("Q1 FY25")
    assert rp is not None
    assert rp.fy_start_year == 2024


def test_reporting_period_from_dict_legacy():
    rp = ReportingPeriod.from_dict(
        {"quarter": 4, "fiscal_year": 26, "quarter_end": "2026-03-31"}
    )
    assert rp.fy_start_year == 2025
    assert rp.fy_label == "FY2025-26"


def test_legacy_fy_end_to_start():
    assert legacy_fy_end_to_start(25) == 2024
    assert legacy_fy_end_to_start(26) == 2025
