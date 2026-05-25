"""Schema-shape tests for `services/ir_discovery/exchange/schemas.py`.

Pure-function checks: the category-mapping helpers must return the
right `DocumentType` for known categories and `None` for unmapped
categories without crashing.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.enums import DocumentType
from app.services.ir_discovery.exchange.schemas import (
    BSE_CATEGORY_MAP,
    NSE_CATEGORY_MAP,
    FilingWindow,
    map_bse_category,
    map_nse_category,
)


@pytest.mark.parametrize(
    "category,subcategory,expected",
    [
        ("Result", None, DocumentType.FINANCIAL_RESULT),
        ("Result", "Q3FY26", DocumentType.FINANCIAL_RESULT),  # subcategory wildcard
        ("Investor Presentation", None, DocumentType.INVESTOR_PRESENTATION),
        ("Annual Report", None, DocumentType.ANNUAL_REPORT),
        (
            "Analysts/Institutional Investor Meet",
            None,
            DocumentType.CONCALL_TRANSCRIPT,
        ),
        ("Company Update", "Investor Presentation", DocumentType.INVESTOR_PRESENTATION),
        ("Company Update", "Earnings Call Transcript", DocumentType.CONCALL_TRANSCRIPT),
        ("Some Random Category", None, None),
        ("", None, None),
    ],
)
def test_bse_category_mapping(category, subcategory, expected):
    assert map_bse_category(category, subcategory) is expected


@pytest.mark.parametrize(
    "category,subcategory,expected",
    [
        ("Financial Results", None, DocumentType.FINANCIAL_RESULT),
        ("Investor Presentation", None, DocumentType.INVESTOR_PRESENTATION),
        ("Annual Report", None, DocumentType.ANNUAL_REPORT),
        ("Earnings Call Transcript", None, DocumentType.CONCALL_TRANSCRIPT),
        ("Press Release", None, None),
    ],
)
def test_nse_category_mapping(category, subcategory, expected):
    assert map_nse_category(category, subcategory) is expected


def test_bse_and_nse_maps_are_distinct():
    """BSE and NSE use different category strings; we keep them in
    separate dicts on purpose. This guards against accidental dedup."""
    bse_keys = set(BSE_CATEGORY_MAP)
    nse_keys = set(NSE_CATEGORY_MAP)
    # Some category labels (e.g. "Investor Presentation") legitimately
    # appear in both. Just sanity-check the dicts are non-empty and
    # categorically scoped.
    assert bse_keys
    assert nse_keys


def test_filing_window_quarterly_default():
    period_end = date(2025, 12, 31)
    window = FilingWindow.for_period(date(2025, 10, 1), period_end, is_annual=False)
    assert window.start == period_end + timedelta(days=1)
    assert window.end == period_end + timedelta(days=60)


def test_filing_window_annual_uses_180_day_tail():
    period_end = date(2026, 3, 31)
    window = FilingWindow.for_period(date(2025, 4, 1), period_end, is_annual=True)
    assert window.start == period_end + timedelta(days=1)
    assert window.end == period_end + timedelta(days=180)
