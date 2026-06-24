"""Tests for markdown-table quarter column extraction."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from periods import reporting_period_from_date
from quarter_column import extract_facts_from_quarter_column

FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"
CATALOG = json.loads((Path(__file__).resolve().parent / "catalog" / "facts.json").read_text())


def test_railtel_q3_revenue_from_quarter_column():
    md = (FIXTURES / "railtel_q3_pl_table.md").read_text(encoding="utf-8")
    target = reporting_period_from_date(date(2025, 12, 31), "test")
    facts = extract_facts_from_quarter_column(
        md,
        target=target,
        fact_keys=set(CATALOG.keys()),
        facts_catalog=CATALOG,
    )
    by_key = {row["fact_key"]: row for row in facts}
    assert by_key["revenue_from_operations"]["numeric_value"] == 91345
    assert by_key["pat"]["numeric_value"] == 6240
    assert by_key["pbt"]["numeric_value"] == 8500
    assert by_key["eps_basic"]["numeric_value"] == 1.94


def test_ignores_nine_months_column_for_same_row():
    md = (FIXTURES / "railtel_q3_pl_table.md").read_text(encoding="utf-8")
    target = reporting_period_from_date(date(2025, 12, 31), "test")
    facts = extract_facts_from_quarter_column(
        md,
        target=target,
        fact_keys={"revenue_from_operations"},
        facts_catalog=CATALOG,
    )
    assert len(facts) == 1
    assert facts[0]["numeric_value"] != 260862  # nine months ended value


if __name__ == "__main__":
    test_railtel_q3_revenue_from_quarter_column()
    test_ignores_nine_months_column_for_same_row()
    print("ok")
