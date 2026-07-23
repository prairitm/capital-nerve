from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from periods import detect_reporting_period
from values_service import detect_period


class ReportingPeriodDetectionTest(unittest.TestCase):
    def test_repeated_current_period_beats_stale_cover_page_typo(self) -> None:
        markdown = """
        Financial Results for the quarter and year ended March 31, 2023
        Approved results for the quarter and year ended March 31, 2024.
        Auditor report for the quarter ended March 31, 2024.
        Results for the quarter ended March 31, 2024.
        """

        period = detect_reporting_period(markdown)

        self.assertIsNotNone(period)
        self.assertEqual(period.label, "Q4 FY2023-24")
        self.assertEqual(period.quarter_end, "2024-03-31")

    def test_explicit_announcement_title_overrides_document_conflict(self) -> None:
        period = detect_reporting_period(
            "Financial Results for the quarter and year ended March 31, 2023",
            title="Financial results for the period ended March 31, 2024",
        )

        self.assertIsNotNone(period)
        self.assertEqual(period.label, "Q4 FY2023-24")
        self.assertEqual(period.source, "title")

    def test_short_fy_quarter_label_is_detected_in_presentation(self) -> None:
        period = detect_reporting_period(
            "# Investor Presentation\nPerformance highlights — Q1 FY25"
        )

        self.assertIsNotNone(period)
        self.assertEqual(period.label, "Q1 FY2024-25")
        self.assertEqual(period.quarter_end, "2024-06-30")

    def test_announcement_fallback_uses_previous_completed_quarter(self) -> None:
        cases = (
            ("2024-05-07", "Q4 FY2023-24", "2024-03-31"),
            ("2024-07-26", "Q1 FY2024-25", "2024-06-30"),
            ("2024-11-04", "Q2 FY2024-25", "2024-09-30"),
            ("2025-02-03", "Q3 FY2024-25", "2024-12-31"),
        )
        for event_date, label, quarter_end in cases:
            with self.subTest(event_date=event_date):
                period = detect_period(
                    "# Investor Presentation\nBusiness highlights",
                    title="Company has informed the Exchange about Investor Presentation",
                    event_row={"event_date": event_date},
                )

                self.assertEqual(period.label, label)
                self.assertEqual(period.quarter_end, quarter_end)
                self.assertEqual(
                    period.source, "previous_completed_quarter_fallback"
                )


if __name__ == "__main__":
    unittest.main()
