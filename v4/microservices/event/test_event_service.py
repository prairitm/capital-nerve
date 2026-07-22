from __future__ import annotations

import sqlite3
import unittest

from event_service import persist_announcements


class EventDiscoveryPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.announcement = {
            "desc": "Financial Results",
            "attchmntText": "Unaudited financial results for the quarter",
            "attchmntFile": "https://example.com/results.pdf",
            "sort_date": "2026-07-18 16:30:00",
            "dt": "18-Jul-2026 16:30:00",
            "sm_name": "Example Ltd",
        }

    def tearDown(self) -> None:
        self.conn.close()

    def test_repeated_announcement_is_not_counted_as_new(self) -> None:
        first = persist_announcements(self.conn, "EXAMPLE", [self.announcement])
        second = persist_announcements(self.conn, "EXAMPLE", [self.announcement])

        self.assertEqual(1, first["stored_count"])
        self.assertTrue(first["events"][0]["inserted"])
        self.assertEqual("Financial Results", first["events"][0]["normalized_event_type"])
        self.assertEqual("2026-07-18 16:30:00", first["events"][0]["published_at"])
        self.assertEqual(0, second["stored_count"])
        self.assertFalse(second["events"][0]["inserted"])

    def test_intimation_is_not_treated_as_financial_results(self) -> None:
        item = {
            **self.announcement,
            "attchmntFile": "https://example.com/intimation.pdf",
            "attchmntText": "Board meeting scheduled to be held to consider financial results",
        }
        result = persist_announcements(self.conn, "EXAMPLE", [item])
        self.assertIsNone(result["events"][0]["normalized_event_type"])

    def test_presentation_filename_overrides_financial_results_description(self) -> None:
        item = {
            **self.announcement,
            "attchmntFile": "https://example.com/Presentation_with_PPT_Signed.pdf",
        }
        result = persist_announcements(self.conn, "EXAMPLE", [item])
        self.assertEqual(
            "Investor Presentation", result["events"][0]["normalized_event_type"]
        )

    def test_presentation_announcement_text_overrides_financial_results_description(self) -> None:
        item = {
            **self.announcement,
            "attchmntFile": "https://example.com/attachment.pdf",
            "attchmntText": "Presentation made by Company on the Unaudited Financial Results",
        }
        result = persist_announcements(self.conn, "EXAMPLE", [item])
        self.assertEqual(
            "Investor Presentation", result["events"][0]["normalized_event_type"]
        )


if __name__ == "__main__":
    unittest.main()
