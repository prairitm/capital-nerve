from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from periods import ReportingPeriod
from quarter_column import extract_facts_from_quarter_column


class QuarterColumnExtractionTest(unittest.TestCase):
    def test_cross_page_statement_disagreement_routes_document_to_review(self) -> None:
        markdown = """
# Page 3
Statement of Consolidated Financial Results
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 10,000.00 |
| Profit before tax | 1,000.00 |
| Profit for the period | 750.00 |

# Page 8
Statement of Financial Results
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 6,000.00 |
| Profit before tax | 600.00 |
| Profit for the period | 450.00 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        self.assertTrue(rows)
        self.assertEqual({row["decision"] for row in rows}, {"review"})
        self.assertTrue(all(row["has_unresolved_conflict"] for row in rows))
        self.assertEqual(
            {row["conflict_reason"] for row in rows},
            {"material_cross_page_statement_disagreement"},
        )

    def test_basis_detects_statement_of_profit_and_loss(self) -> None:
        markdown = """
# Page 12
Standalone Statement of Profit and Loss for the quarter ended 30 June 2025
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 31,014.36 |
| Profit before tax | 4,557.76 |
| Net profit for the period | 3,523.25 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        self.assertEqual({row["basis"] for row in rows}, {"standalone"})

    def test_profit_margin_ratio_does_not_replace_pat_amount(self) -> None:
        markdown = """
# Page 14
Consolidated Statement of Profit and Loss for the quarter ended 30 June 2025
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 53,178.12 |
| Profit before tax | 3,067.08 |
| Net profit for the period | 2,007.36 |
| Net profit margin (%) (Net profit after tax / Turnover) | 3.77 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["pat"]["numeric_value"], 2007.36)
        self.assertEqual(by_key["pat"]["source_page"], 14)

    def test_slash_loss_pat_and_spelled_out_eps_aliases(self) -> None:
        markdown = """
# Page 14
Consolidated Statement of Profit and Loss for the quarter ended 30 June 2025
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 53,178.12 |
| Profit before tax | 3,067.08 |
| Net Profit / (Loss) for the period | 2,007.36 |
| Basic earnings per share (not annualised) - in Rupees | 1.67 |
| Diluted earnings per share (not annualised) - in Rupees | 1.67 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["pat"]["numeric_value"], 2007.36)
        self.assertEqual(by_key["eps_basic"]["numeric_value"], 1.67)
        self.assertEqual(by_key["eps_diluted"]["numeric_value"], 1.67)

    def test_total_group_pat_precedes_after_nci_attribution(self) -> None:
        markdown = """
# Page 12
Statement of Unaudited Consolidated Financial Results for the Quarter ended June 30, 2025
(₹ in Million)
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Total revenue from operations | 138,514.0 |
| Profit before tax | 31,727.7 |
| Net Profit after taxes and share of associates but before non-controlling interests | 22,928.7 |
| Net Profit after taxes, share of associates and non-controlling interests | 22,786.3 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        pat = {row["fact_key"]: row for row in rows}["pat"]
        self.assertEqual(pat["numeric_value"], 2292.87)
        self.assertIn("before non-controlling", pat["evidence"])

    def test_normalized_evidence_retains_exact_large_decimal(self) -> None:
        markdown = """
# Page 12
Statement of Unaudited Consolidated Financial Results for the Quarter ended June 30, 2025
(₹ in Million)
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 138,514.0 |
| Total income | 143,158.6 |
| Profit before tax | 31,727.7 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        total_income = {row["fact_key"]: row for row in rows}["total_income"]
        self.assertEqual(total_income["numeric_value"], 14315.86)
        self.assertIn("14315.86 crore", total_income["evidence"])

    def test_multiple_operation_scope_tax_rows_are_withheld(self) -> None:
        markdown = """
# Page 10
Statement of Consolidated Financial Results for the Quarter ended 31 March 2025
| Particulars | 3 Months ended 31.03.2025 |
| --- | --- |
| CONTINUING OPERATIONS | |
| Revenue from operations | 20,376.36 |
| Profit before tax | 6,836.12 |
| Tax expense | 1,680.85 |
| Profit for the period from continuing operations | 5,155.27 |
| DISCONTINUED OPERATIONS | |
| Tax expense of discontinued operations | 492.57 |
| Profit for the period | 19,807.88 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "tax_expense": {"name": "Tax Expense", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=4, fy_start_year=2024, quarter_end="2025-03-31"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        self.assertNotIn("tax_expense", {row["fact_key"] for row in rows})

    def test_uses_particulars_column_instead_of_section_label(self) -> None:
        markdown = """
# Page 6
Statement of Audited Standalone Financial Results (Rs in Crores)
| Sr. No. | Particulars | Quarter Ended 30.06.2025 | Year Ended 31.03.2025 |
| --- | --- | --- | --- |
| 1 | Revenue from operations | 7,868.45 | 29,552.65 |
| 7 | Profit before tax | 1,468.17 | 4,897.18 |
| Tax expense | a) Current Tax | 363.42 | 1,306.70 |
| | b) Deferred Tax | 5.12 | 5.60 |
| 8 | Total tax expense | 368.54 | 1,312.30 |
| 9 | Profit for the period | 1,099.63 | 3,584.88 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "tax_expense": {"name": "Tax Expense", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["tax_expense"]["numeric_value"], 368.54)
        self.assertIn("Total tax expense", by_key["tax_expense"]["evidence"])

    def test_normalizes_million_to_crore_without_scaling_eps(self) -> None:
        markdown = """
# Page 2
Statement of Standalone Unaudited Financial Results
(INR in million, except per share data)
| Particulars | Quarter ended June 30, 2025 |
| --- | --- |
| Revenue from operations | 384,136 |
| Profit before tax | 48,342 |
| Profit for the period | 37,117 |
| Earnings per equity share - Basic | 118.06 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["revenue_from_operations"]["numeric_value"], 38413.6)
        self.assertEqual(by_key["pbt"]["numeric_value"], 4834.2)
        self.assertEqual(by_key["eps_basic"]["numeric_value"], 118.06)
        self.assertIn("38413.6 crore", by_key["revenue_from_operations"]["evidence"])

    def test_normalizes_indian_rupees_millions_wording(self) -> None:
        markdown = """
# Page 20
Statement of Unaudited Consolidated Financial Results
All amounts in Indian Rupees millions
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 85,721 |
| Profit before tax | 19,050 |
| Net profit for the period | 14,099 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        rows = extract_facts_from_quarter_column(
            markdown,
            target=ReportingPeriod(
                quarter=1, fy_start_year=2025, quarter_end="2025-06-30"
            ),
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["revenue_from_operations"]["numeric_value"], 8572.1)
        self.assertEqual(by_key["pat"]["numeric_value"], 1409.9)

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
        self.assertEqual(by_key["pat"]["period_end"], "2025-06-30")
        self.assertEqual(
            by_key["pat"]["extraction_method"], "deterministic_quarter_column"
        )

    def test_preserves_pdf_page_number(self) -> None:
        markdown = """
# Page 7

Statement of Unaudited Consolidated Financial Results

|             | Three months ended |
| --- | --- |
|             | June 30, 2025 |
| Revenue from operations | 1,234.50 |
| Profit before tax | 100.00 |
| Profit for the period | 75.00 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(quarter=1, fy_start_year=2025, quarter_end="2025-06-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        self.assertEqual({row["source_page"] for row in rows}, {7})

    def test_keeps_consolidated_and_standalone_values_separate(self) -> None:
        markdown = """
# Page 8
Audited Consolidated Interim Statement of Financial Results
| | Three months ended |
| --- | --- |
| | June 30, 2025 |
| Revenue from operations | 1,234 |
| Profit before tax | 100 |
| Profit for the period | 75 |

# Page 14
Audited Standalone Interim Statement of Financial Results
| | Three months ended |
| --- | --- |
| | June 30, 2025 |
| Revenue from operations | 999 |
| Profit before tax | 80 |
| Profit for the period | 60 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(quarter=1, fy_start_year=2025, quarter_end="2025-06-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        revenues = {
            row["basis"]: (row["numeric_value"], row["source_page"])
            for row in rows
            if row["fact_key"] == "revenue_from_operations"
        }
        self.assertEqual(revenues["consolidated"], (1234.0, 8))
        self.assertEqual(revenues["standalone"], (999.0, 14))

    def test_reads_eps_from_detached_continuation_table(self) -> None:
        markdown = """
# Page 8
Audited Consolidated Interim Statement of Financial Results
| | Three months ended | |
| --- | --- | --- |
| | June 30, 2025 | March 31, 2025 |
| Revenue from operations | 1,234 | 1,100 |
| Profit before tax | 100 | 90 |
| Profit for the period | 75 | 70 |

| Earnings per equity share:- Basic and diluted (Rs) | 7.50 | 7.00 |
| --- | --- | --- |
| Dividend per share | 1.00 | 1.00 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        target = ReportingPeriod(quarter=1, fy_start_year=2025, quarter_end="2025-06-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        eps = {row["fact_key"]: row for row in rows if row["fact_key"].startswith("eps_")}
        self.assertEqual(eps["eps_basic"]["numeric_value"], 7.5)
        self.assertEqual(eps["eps_diluted"]["numeric_value"], 7.5)
        self.assertEqual(eps["eps_basic"]["source_page"], 8)

    def test_parses_short_indian_date_and_split_eps_rows(self) -> None:
        markdown = """
# Page 10
UNAUDITED CONSOLIDATED FINANCIAL RESULTS
| Particulars | Quarter Ended | Year Ended |
| --- | --- | --- |
| | 30th Jun'25 | 31st Mar'25 |
| Revenue from Operations | 2,000 | 7,000 |
| Sales, administration and other expenses | 250 | 900 |
| Profit Before Tax | 200 | 600 |
| Profit After Tax | 150 | 450 |
| Earnings per equity share | | |
| a) Basic (in Rs) | 10.50 | 31.50 |
| b) Diluted (in Rs) | 10.40 | 31.40 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        target = ReportingPeriod(quarter=1, fy_start_year=2025, quarter_end="2025-06-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["revenue_from_operations"]["numeric_value"], 2000.0)
        self.assertEqual(by_key["eps_basic"]["numeric_value"], 10.5)
        self.assertEqual(by_key["eps_diluted"]["numeric_value"], 10.4)

    def test_handles_profit_loss_and_explicit_diluted_eps_labels(self) -> None:
        markdown = """
# Page 22
STATEMENT OF UNAUDITED STANDALONE FINANCIAL RESULTS
| Particulars | Quarter ended September 30, 2025 | Six months ended September 30, 2025 |
| --- | --- | --- |
| Revenue from operations | 35,115.74 | 68,586.47 |
| Profit/(loss) before tax | (2,981.77) | 1,058.32 |
| Net profit/(loss) after tax | (3,591.17) | (105.87) |
| (a) Basic EPS (Rs) | (26.11) | (0.77) |
| (b) Diluted EPS (Rs) | (26.12) | (0.78) |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore", "aliases": ["revenue", "sales"]},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore", "aliases": ["net_profit"]},
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        target = ReportingPeriod(quarter=2, fy_start_year=2025, quarter_end="2025-09-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["pbt"]["numeric_value"], -2981.77)
        self.assertEqual(by_key["pat"]["numeric_value"], -3591.17)
        self.assertEqual(by_key["eps_basic"]["numeric_value"], -26.11)
        self.assertEqual(by_key["eps_diluted"]["numeric_value"], -26.12)

    def test_complete_statement_wins_over_later_compact_disclosure(self) -> None:
        markdown = """
# Page 9
STATEMENT OF UNAUDITED CONSOLIDATED FINANCIAL RESULTS
| Particulars | Quarter ended September 30, 2025 | Six months ended September 30, 2025 |
| --- | --- | --- |
| Revenue from operations | 67,983.53 | 131,662.45 |
| Total income | 69,367.81 | 134,403.51 |
| Finance cost of financial services business | 1,706.83 | 3,413.18 |
| Finance costs | 762.81 | 1,544.42 |
| Total expenses | 63,031.70 | 122,207.87 |
| Profit before tax | 6,336.11 | 12,195.64 |
| Net profit after tax | 4,687.09 | 9,012.66 |
| Net profit after tax and share in profit/(loss) of joint ventures/associates | 4,678.01 | 8,996.18 |

# Page 10
Consolidated Financial Results
| Particulars | Quarter ended September 30, 2025 | Six months ended September 30, 2025 |
| --- | --- | --- |
| Revenue from operations | 35,115.74 | 68,586.47 |
| Profit/(loss) before tax (after exceptional items) | (2,981.77) | 1,058.32 |
| Net profit/(loss) after tax (after exceptional items) | (3,591.17) | (105.87) |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "finance_cost": {"name": "Finance Cost", "unit": "crore"},
            "total_expenses": {"name": "Total Expenses", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(quarter=2, fy_start_year=2025, quarter_end="2025-09-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["revenue_from_operations"]["numeric_value"], 67983.53)
        self.assertEqual(by_key["pbt"]["numeric_value"], 6336.11)
        self.assertEqual(by_key["pat"]["numeric_value"], 4678.01)
        self.assertEqual(by_key["finance_cost"]["numeric_value"], 762.81)
        self.assertEqual(by_key["revenue_from_operations"]["source_page"], 9)

    def test_selects_annual_column_when_quarter_has_same_end_date(self) -> None:
        markdown = """
# Page 9
Consolidated Financial Results for the Quarter and Year ended March 31, 2024
| Particulars | Quarter ended | Year ended |
| --- | --- | --- |
| | March 31, 2024 | December 31, 2023 | March 31, 2023 | March 31, 2024 | March 31, 2023 |
| Revenue from operations | 6,164.83 | 5,006.72 | 5,525.01 | 19,914.17 | 17,281.71 |
| Total Income | 6,172.62 | 5,032.70 | 5,530.53 | 19,966.58 | 17,313.03 |
| Total expenses | 5,979.33 | 4,911.98 | 5,444.65 | 19,540.09 | 17,152.05 |
| Profit after exceptional items and before tax | 193.29 | 120.72 | 85.88 | 426.49 | 160.98 |
| Profit for the period | 151.75 | 96.87 | 72.17 | 346.78 | 176.03 |
| Basic / Diluted Earnings Per Share | 5.90 | 3.77 | 2.81 | 13.49 | 6.85 |

# Page 21
Standalone Financial Results for the Quarter and Year ended March 31, 2024
| Particulars | Quarter ended March 31, 2024 | Quarter ended December 31, 2023 | Quarter ended March 31, 2023 | Year ended March 31, 2024 | Year ended March 31, 2023 |
| --- | --- | --- | --- | --- | --- |
| Revenue from operations | 5,301.81 | 4,397.76 | 4,961.37 | 17,383.35 | 15,413.23 |
| Total Income | 5,313.56 | 4,426.93 | 4,969.67 | 17,445.40 | 15,449.94 |
| Total expenses | 5,192.69 | 4,371.01 | 4,922.65 | 17,253.82 | 15,124.22 |
| Profit after exceptional items and before tax | 120.87 | 55.92 | 47.02 | 191.58 | 250.15 |
| Profit for the period | 92.93 | 44.05 | 29.40 | 147.53 | 180.25 |
| Basic / Diluted Earnings Per Share | 3.61 | 1.71 | 1.14 | 5.74 | 7.01 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "total_expenses": {"name": "Total Expenses", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        target = ReportingPeriod(
            quarter=4,
            fy_start_year=2023,
            quarter_end="2024-03-31",
            period_type="year",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type="year",
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {(row["basis"], row["fact_key"]): row for row in rows}
        self.assertEqual(by_key[("consolidated", "revenue_from_operations")]["numeric_value"], 19914.17)
        self.assertEqual(by_key[("consolidated", "pbt")]["numeric_value"], 426.49)
        self.assertEqual(by_key[("consolidated", "pat")]["numeric_value"], 346.78)
        self.assertEqual(by_key[("consolidated", "eps_basic")]["numeric_value"], 13.49)
        self.assertEqual(by_key[("consolidated", "eps_diluted")]["numeric_value"], 13.49)
        self.assertEqual(by_key[("standalone", "revenue_from_operations")]["numeric_value"], 17383.35)
        self.assertEqual(by_key[("standalone", "pbt")]["numeric_value"], 191.58)
        self.assertEqual(by_key[("standalone", "pat")]["numeric_value"], 147.53)
        self.assertEqual(by_key[("standalone", "eps_diluted")]["numeric_value"], 5.74)
        self.assertEqual(by_key[("consolidated", "pat")]["period_type"], "year")
        self.assertEqual(
            by_key[("consolidated", "pat")]["extraction_method"],
            "deterministic_period_column",
        )

    def test_selects_half_year_column_when_quarter_has_same_end_date(self) -> None:
        markdown = """
# Page 10
UNAUDITED CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER / HALF YEAR ENDED 30TH SEPTEMBER, 2025
| Particulars | Quarter Ended | | | Half Year Ended | | Year Ended |
| --- | --- | --- | --- | --- | --- | --- |
| | 30th Sep'25 | 30th Jun'25 | 30th Sep'24 | 30th Sep'25 | 30th Sep'24 | 31st Mar'25 |
| Revenue from Operations | 258,898 | 248,660 | 235,481 | 507,558 | 471,698 | 980,136 |
| Total Income | 263,380 | 263,779 | 240,357 | 527,159 | 480,557 | 998,114 |
| Total Expenses | 234,256 | 226,633 | 215,320 | 460,889 | 432,286 | 892,097 |
| Profit Before Tax | 29,124 | 37,146 | 25,037 | 66,270 | 48,271 | 106,017 |
| Profit After Tax | 22,146 | 30,681 | 19,101 | 52,827 | 36,549 | 80,787 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "total_expenses": {"name": "Total Expenses", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(
            quarter=2,
            fy_start_year=2025,
            quarter_end="2025-09-30",
            period_type="half_year",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type="half_year",
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["revenue_from_operations"]["numeric_value"], 507558.0)
        self.assertEqual(by_key["pbt"]["numeric_value"], 66270.0)
        self.assertEqual(by_key["pat"]["numeric_value"], 52827.0)
        self.assertEqual(by_key["pat"]["period_type"], "half_year")

    def test_exceptional_reconciliation_overrides_pre_exceptional_tax(self) -> None:
        markdown = """
# Page 9
STATEMENT OF UNAUDITED CONSOLIDATED FINANCIAL RESULTS
| Particulars | Quarter ended December 31, 2025 | Nine months ended December 31, 2025 |
| --- | --- | --- |
| Revenue from operations | 71,449.70 | 203,112.18 |
| Total Income | 72,890.74 | 207,294.29 |
| Total Expenses | 65,729.76 | 187,937.65 |
| Total tax expense | 1,979.99 | 5,170.99 |
| Net profit after tax including share in profit/(loss) of joint ventures/associates | 3,824.65 | 12,820.83 |

| Particulars | Quarter ended December 31, 2025 | Nine months ended December 31, 2025 |
| --- | --- | --- |
| Profit before tax (including exceptional items) | 5,369.89 | 17,565.55 |
| Tax expense (including tax on exceptional items) | 1,540.66 | 4,723.66 |
| Net profit after tax including share in profit/(loss) of joint ventures/associates | 3,824.65 | 12,820.83 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "total_expenses": {"name": "Total Expenses", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "tax_expense": {"name": "Tax Expense", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(
            quarter=3,
            fy_start_year=2025,
            quarter_end="2025-12-31",
            period_type="nine_months",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type="nine_months",
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["pbt"]["numeric_value"], 17565.55)
        self.assertEqual(by_key["tax_expense"]["numeric_value"], 4723.66)
        self.assertEqual(by_key["pat"]["numeric_value"], 12820.83)

    def test_page_basis_survives_unrelated_consolidated_prose(self) -> None:
        markdown = """
# Page 21
STATEMENT OF UNAUDITED STANDALONE FINANCIAL RESULTS
| Particulars | Quarter ended December 31, 2025 | Nine months ended December 31, 2025 |
| --- | --- | --- |
| Revenue from operations | 37,902.84 | 106,489.31 |
| Total Income | 39,043.15 | 112,344.92 |
| Total Expenses | 36,025.66 | 101,379.96 |
| Total tax expense | 668.42 | 1,996.07 |
| Net profit after tax | 731.64 | 2,726.21 |

The Government consolidated 29 regulations into a new labour code.

| Particulars | Quarter ended December 31, 2025 | Nine months ended December 31, 2025 |
| --- | --- | --- |
| Profit before tax (including exceptional items) | 1,266.08 | 4,443.23 |
| Tax expense (including tax on exceptional items) | 534.44 | 1,717.02 |
| Net profit after tax | 731.64 | 2,726.21 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "total_income": {"name": "Total Income", "unit": "crore"},
            "total_expenses": {"name": "Total Expenses", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "tax_expense": {"name": "Tax Expense", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(
            quarter=3,
            fy_start_year=2025,
            quarter_end="2025-12-31",
            period_type="nine_months",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type="nine_months",
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {(row["basis"], row["fact_key"]): row for row in rows}
        self.assertEqual(
            by_key[("standalone", "tax_expense")]["numeric_value"], 1717.02
        )
        self.assertNotIn(("consolidated", "tax_expense"), by_key)

    def test_title_column_does_not_shift_nine_month_selection(self) -> None:
        markdown = """
# Page 6
| Statement of Consolidated Unaudited Financial Results for the Quarter and Nine months ended December 31, 2024 | Quarter ended | Nine months ended | Year ended |
| --- | --- | --- | --- | --- | --- | --- |
| Particulars | December 31, 2024 | September 30, 2024 | December 31, 2023 | December 31, 2024 | December 31, 2023 | March 31, 2024 |
| Revenue from operations | 5,349.38 | 5,113.31 | 5,006.72 | 14,974.58 | 13,749.34 | 19,914.17 |
| Profit before tax | 159.83 | 113.47 | 120.72 | 385.33 | 233.20 | 426.49 |
| Profit for the period | 129.56 | 85.41 | 96.87 | 302.55 | 195.04 | 346.78 |
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(
            quarter=3,
            fy_start_year=2024,
            quarter_end="2024-12-31",
            period_type="nine_months",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type="nine_months",
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["revenue_from_operations"]["numeric_value"], 14974.58)
        self.assertEqual(by_key["pbt"]["numeric_value"], 385.33)
        self.assertEqual(by_key["pat"]["numeric_value"], 302.55)

    def test_post_table_context_recovers_ocr_dropped_standalone_heading(self) -> None:
        markdown = """
# Page 12
# KEC International Limited
| Particulars | Quarter ended | Nine months ended | Year ended |
| --- | --- | --- | --- | --- | --- | --- |
| | December 31, 2024 | September 30, 2024 | December 31, 2023 | December 31, 2024 | December 31, 2023 | March 31, 2024 |
| Revenue from operations | 4,757.64 | 4,483.84 | 4,397.76 | 13,129.73 | 12,081.54 | 17,383.35 |
| Profit before tax | 93.33 | 73.90 | 55.92 | 210.31 | 70.71 | 191.58 |
| Profit for the period | 72.89 | 58.15 | 44.05 | 163.19 | 54.60 | 147.53 |

See accompanying notes forming part of the standalone financial results.
"""
        catalog = {
            "revenue_from_operations": {"name": "Revenue From Operations", "unit": "crore"},
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(
            quarter=3,
            fy_start_year=2024,
            quarter_end="2024-12-31",
            period_type="nine_months",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type="nine_months",
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {(row["basis"], row["fact_key"]): row for row in rows}
        self.assertEqual(
            by_key[("standalone", "revenue_from_operations")]["numeric_value"],
            13129.73,
        )
        self.assertNotIn(("consolidated", "revenue_from_operations"), by_key)

    def test_total_comprehensive_income_does_not_override_pat(self) -> None:
        markdown = """
# Page 2
# Extract of the consolidated audited financial results
| Particulars | Quarter ended June 30, 2025 | Year ended March 31, 2025 |
| --- | --- | --- |
| Revenue from operations | 42,279 | 1,62,990 |
| Profit before tax | 9,740 | 37,608 |
| Profit for the period | 6,924 | 26,750 |
| Total comprehensive income for the period (comprising profit for the period after tax and other comprehensive income after tax) | 8,037 | 27,209 |
| Earnings per share (par value Rs 5/- each) | | |
| Basic (in Rs per share) | 16.70 | 64.50 |
| Diluted (in Rs per share) | 16.68 | 64.34 |
"""
        catalog = {
            "revenue_from_operations": {
                "name": "Revenue From Operations",
                "unit": "crore",
            },
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
            "total_comprehensive_income": {
                "name": "Total Comprehensive Income",
                "unit": "crore",
            },
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        target = ReportingPeriod(
            quarter=1,
            fy_start_year=2025,
            quarter_end="2025-06-30",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["pat"]["numeric_value"], 6924.0)
        self.assertEqual(
            by_key["total_comprehensive_income"]["numeric_value"],
            8037.0,
        )
        self.assertEqual(by_key["eps_basic"]["numeric_value"], 16.70)
        self.assertEqual(by_key["eps_diluted"]["numeric_value"], 16.68)

    def test_basis_detects_parenthetical_standalone_after_financial_results(self) -> None:
        markdown = """
# Page 2
## Audited financial results of Example Limited (Standalone information)
| Particulars | Quarter ended June 30, 2025 | Year ended March 31, 2025 |
| --- | --- | --- |
| Revenue from operations | 35,275 | 1,36,592 |
| Profit before tax | 8,660 | 35,441 |
| Profit for the period | 6,114 | 25,568 |
"""
        catalog = {
            "revenue_from_operations": {
                "name": "Revenue From Operations",
                "unit": "crore",
            },
            "pbt": {"name": "PBT", "unit": "crore"},
            "pat": {"name": "PAT", "unit": "crore"},
        }
        target = ReportingPeriod(
            quarter=1,
            fy_start_year=2025,
            quarter_end="2025-06-30",
        )
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        self.assertEqual({row["basis"] for row in rows}, {"standalone"})
        self.assertEqual(
            {row["fact_key"]: row["numeric_value"] for row in rows},
            {
                "revenue_from_operations": 35275.0,
                "pbt": 8660.0,
                "pat": 6114.0,
            },
        )

    def test_reads_headered_eps_supplemental_table(self) -> None:
        markdown = """
# Page 11
# Particulars
| Particulars | Quarter Ended 30th Jun'25 | Quarter Ended 31st Mar'25 |
| --- | --- | --- |
| Earnings per equity share | | |
| a) Basic (in Rs) | 19.95 | 14.34 |
| b) Diluted (in Rs) | 19.95 | 14.34 |
"""
        catalog = {
            "eps_basic": {"name": "EPS Basic", "unit": "Rs"},
            "eps_diluted": {"name": "EPS Diluted", "unit": "Rs"},
        }
        target = ReportingPeriod(quarter=1, fy_start_year=2025, quarter_end="2025-06-30")
        rows = extract_facts_from_quarter_column(
            markdown,
            target=target,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        by_key = {row["fact_key"]: row for row in rows}
        self.assertEqual(by_key["eps_basic"]["numeric_value"], 19.95)
        self.assertEqual(by_key["eps_diluted"]["numeric_value"], 19.95)
        self.assertEqual(by_key["eps_basic"]["source_page"], 11)


if __name__ == "__main__":
    unittest.main()
