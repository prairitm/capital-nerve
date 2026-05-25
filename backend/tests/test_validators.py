"""Unit tests for the post-LLM validators.

These tests run without a database — they exercise pure functions on
`ExtractedLineItem` lists. Run with::

    cd backend && pytest tests/test_validators.py
"""
from __future__ import annotations

import pytest

from app.services.pipeline.llm import ExtractedLineItem
from app.services.pipeline.validators import (
    ValidatorReport,
    canonicalize_units,
    run_validators,
    validate_source_text,
    validate_totals,
)


def _item(
    code: str,
    value: float,
    *,
    unit: str = "crore",
    page: int | None = 1,
    src: str | None = None,
    conf: float = 90.0,
) -> ExtractedLineItem:
    return ExtractedLineItem(
        normalized_code=code,
        raw_label=code,
        value=value,
        unit=unit,
        page_number=page,
        source_text=src if src is not None else f"{code} {value}",
        confidence=conf,
    )


# ---------------------------------------------------------------------------
# Source-text anchor
# ---------------------------------------------------------------------------


def test_source_text_keeps_items_when_value_token_appears_on_page():
    pages = [(1, "Revenue from Operations 17,394 crore")]
    items = [_item("revenue_from_operations", 17394, src="Revenue from Operations 17,394")]
    report = ValidatorReport()
    kept = validate_source_text(items, pages=pages, report=report)
    assert len(kept) == 1
    assert not report.source_text_dropped


def test_source_text_drops_items_whose_value_is_not_on_the_claimed_page():
    pages = [(1, "Revenue from Operations 17,394 crore")]
    # Model hallucinated 99,999 — number not present on page 1.
    items = [_item("revenue_from_operations", 99999, src="Revenue 99,999")]
    report = ValidatorReport()
    kept = validate_source_text(items, pages=pages, report=report)
    assert kept == []
    assert report.source_text_dropped[0]["normalized_code"] == "revenue_from_operations"


def test_source_text_downgrades_when_page_text_unavailable():
    items = [_item("revenue_from_operations", 17394, page=999, conf=95.0)]
    report = ValidatorReport()
    kept = validate_source_text(items, pages=[(1, "...")], report=report)
    assert len(kept) == 1
    assert kept[0].confidence == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# Unit canonicalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Cr", "crore"),
        ("INR cr", "crore"),
        ("crores", "crore"),
        ("Rs.", "Rs"),
        ("₹", "Rs"),
        ("percent", "%"),
        ("%", "%"),
        ("bps", "bps"),
    ],
)
def test_unit_aliases_are_canonicalised(raw: str, expected: str):
    items = [_item("revenue_from_operations", 100.0, unit=raw)]
    report = ValidatorReport()
    kept = canonicalize_units(items, report=report)
    assert kept[0].unit == expected


def test_lakh_unit_is_rescaled_to_crore():
    items = [_item("revenue_from_operations", 100.0, unit="lakh")]
    report = ValidatorReport()
    kept = canonicalize_units(items, report=report)
    assert len(kept) == 1
    assert kept[0].unit == "crore"
    assert kept[0].value == pytest.approx(1.0)
    assert report.unit_dropped == []
    assert report.unit_rescaled
    entry = report.unit_rescaled[0]
    assert entry["from_unit"] == "lakh"
    assert entry["to_unit"] == "crore"
    assert entry["scale"] == pytest.approx(0.01)
    assert entry["from_value"] == pytest.approx(100.0)


def test_million_unit_is_rescaled():
    items = [_item("ebitda", 250.0, unit="million")]
    report = ValidatorReport()
    kept = canonicalize_units(items, report=report)
    assert kept[0].unit == "crore"
    assert kept[0].value == pytest.approx(25.0)


def test_billion_unit_is_rescaled():
    items = [_item("market_cap", 1.5, unit="billion")]
    report = ValidatorReport()
    kept = canonicalize_units(items, report=report)
    assert kept[0].unit == "crore"
    assert kept[0].value == pytest.approx(150.0)


def test_raw_rupees_unit_is_rescaled():
    items = [_item("revenue_from_operations", 1_000_000_000.0, unit="rupees")]
    report = ValidatorReport()
    kept = canonicalize_units(items, report=report)
    assert kept[0].unit == "crore"
    assert kept[0].value == pytest.approx(100.0)


def test_truly_unknown_unit_is_dropped():
    items = [_item("revenue_from_operations", 100.0, unit="furlongs")]
    report = ValidatorReport()
    kept = canonicalize_units(items, report=report)
    assert kept == []
    assert report.unit_dropped[0]["raw_unit"] == "furlongs"


# ---------------------------------------------------------------------------
# Totals math
# ---------------------------------------------------------------------------


def test_total_income_identity_passes_within_tolerance():
    items = [
        _item("revenue_from_operations", 100.0, conf=90.0),
        _item("other_income", 5.0, conf=90.0),
        _item("total_income", 105.0, conf=90.0),
    ]
    report = ValidatorReport()
    out = validate_totals(items, report=report)
    assert report.totals_breaches == []
    assert all(i.confidence == 90.0 for i in out)


def test_total_income_breach_downgrades_confidence():
    items = [
        _item("revenue_from_operations", 100.0, conf=90.0),
        _item("other_income", 5.0, conf=90.0),
        _item("total_income", 200.0, conf=90.0),  # way off
    ]
    report = ValidatorReport()
    out = validate_totals(items, report=report)
    assert len(report.totals_breaches) == 1
    by_code = {i.normalized_code: i for i in out}
    assert by_code["total_income"].confidence == pytest.approx(40.0)
    assert by_code["revenue_from_operations"].confidence == pytest.approx(40.0)
    assert by_code["other_income"].confidence == pytest.approx(40.0)


def test_pat_identity_breach():
    items = [
        _item("pbt", 100.0),
        _item("tax_expense", 25.0),
        _item("pat", 50.0),  # should be 75
    ]
    report = ValidatorReport()
    validate_totals(items, report=report)
    rules = [b["rule"] for b in report.totals_breaches]
    assert any("pat = pbt - tax_expense" in r for r in rules)


def test_ebitda_margin_identity_breach():
    items = [
        _item("revenue_from_operations", 1000.0),
        _item("ebitda", 200.0),
        _item("ebitda_margin", 30.0, unit="%"),  # expected ~20
    ]
    report = ValidatorReport()
    validate_totals(items, report=report)
    assert any("ebitda_margin" in b["rule"] for b in report.totals_breaches)


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------


def test_run_validators_combines_all_three_stages():
    # Page text contains every value so the source-text stage does not drop
    # anything — the bad unit on `inventory` is rescaled (lakh→crore), and
    # the unrecognisable unit on `cogs` is dropped.
    pages = [
        (
            1,
            "Revenue from Operations 100 Other Income 5 Total Income 105 "
            "Inventory 50 COGS 70",
        )
    ]
    items = [
        _item("revenue_from_operations", 100, src="Revenue from Operations 100"),
        _item("other_income", 5, src="Other Income 5"),
        _item("total_income", 105, src="Total Income 105"),
        _item("inventory", 50, unit="lakh", src="Inventory 50"),  # rescaled
        _item("cogs", 70, unit="furlongs", src="COGS 70"),  # dropped
    ]
    out, report = run_validators(items, pages=pages)
    codes = {i.normalized_code for i in out}
    assert "inventory" in codes  # rescaled, not dropped
    assert "cogs" not in codes  # dropped
    inventory = next(i for i in out if i.normalized_code == "inventory")
    assert inventory.unit == "crore"
    assert inventory.value == pytest.approx(0.5)
    assert len(report.unit_dropped) == 1
    assert report.unit_dropped[0]["raw_unit"] == "furlongs"
    assert report.unit_rescaled
    assert report.totals_breaches == []
    assert report.source_text_dropped == []
