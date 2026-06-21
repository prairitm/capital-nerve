"""Smoke tests for regex supplemental extractors (no DB)."""
from __future__ import annotations

import re

from app.services.pipeline.announcement import _FIELDS as ANN_FIELDS
from app.services.pipeline.presentation import _FIELDS as PRES_FIELDS


def test_announcement_order_pattern_matches():
    spec = next(s for s in ANN_FIELDS if s.code == "new_order_value")
    text = "Company bagged order worth 1,250 crore from a PSU client."
    assert spec.pattern.search(text) is not None


def test_presentation_tam_pattern_matches():
    spec = next(s for s in PRES_FIELDS if s.code == "tam_market_size")
    text = "Total addressable market (TAM) estimated at 45,000 crore by FY28."
    assert spec.pattern.search(text) is not None


def test_segment_row_pattern_matches():
    from app.services.pipeline.segment import _SEGMENT_ROW

    text = "Telecom Services 12,500 3,200"
    m = _SEGMENT_ROW.search(text)
    assert m is not None
    assert m.group("name").strip() == "Telecom Services"
