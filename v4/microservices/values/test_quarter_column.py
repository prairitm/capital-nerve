from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from periods import ReportingPeriod
from quarter_column import extract_facts_from_quarter_column


class QuarterColumnExtractionTest(unittest.TestCase):
    def test_picks_three_months_column_not_twelve_months_column(self) -> None:
        markdown = """
# ITC Limited
Statement of Unaudited Consolidated Financial Results for the Quarter ended 30th June, 2025

| Particulars | 3 Months ended 30.06.2025 (Unaudited) | Corresponding 3 Months ended 30.06.2024 (Unaudited) | Preceding 3 Months ended 31.03.2025 (Audited) | Twelve Months ended 31.03.2025 (Audited) |
|-------------|---------------------------------------|----------------------------------------------------|----------------------------------------------|-----------------------------------------|
| REVENUE FROM OPERATIONS [(i)+(ii)] | 23129.35 | 19350.08 | 20376.36 | 81612.78 |
| TOTAL INCOME (1+2) | 23811.56 | 20032.78 | 21016.62 | 84142.47 |
| TOTAL EXPENSES | 16752.31 | 13217.97 | 14278.91 | 57325.95 |
| PROFIT BEFORE TAX (6+7) | 7128.01 | 6818.57 | 6836.12 | 26926.94 |
| PROFIT FOR THE PERIOD (10+14) | 5343.41 | 5176.99 | 19807.88 | 35052.48 |
"""
        facts_catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "total_expenses": {"name": "Total Expenses", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(quarter=1, fy_start_year=2025, quarter_end="2025-06-30")

        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(facts_catalog),
            facts_catalog=facts_catalog,
        )

        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["pat"]["numeric_value"], 5343.41)
        self.assertEqual(by_key["pbt"]["numeric_value"], 7128.01)


if __name__ == "__main__":
    unittest.main()
