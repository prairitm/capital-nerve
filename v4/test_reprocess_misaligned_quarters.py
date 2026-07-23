from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reprocess_misaligned_quarters import (
    expected_reporting_period,
    find_misaligned_events,
)


class ReprocessMisalignedQuartersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "capital_nerve.db"
        self.parsed_dir = self.root / "parsed"
        self.parsed_dir.mkdir()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                ticker TEXT
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                event_type TEXT,
                event_date TEXT,
                fiscal_year INTEGER,
                fiscal_quarter INTEGER,
                title TEXT,
                source_url TEXT,
                document_id TEXT
            );
            CREATE TABLE documents (
                id TEXT PRIMARY KEY,
                title TEXT,
                source_url TEXT,
                storage_path TEXT
            );
            INSERT INTO companies VALUES ('company', 'KEC');
            """
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp.cleanup()

    def add_event(
        self,
        *,
        event_id: str,
        event_date: str,
        fiscal_year: int,
        fiscal_quarter: int,
        title: str,
        markdown: str | None = None,
        event_type: str = "Investor Presentation",
    ) -> None:
        document_id = f"document-{event_id}"
        self.conn.execute(
            """
            INSERT INTO events VALUES (?, 'company', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                event_date,
                fiscal_year,
                fiscal_quarter,
                title,
                f"https://example.test/{document_id}.pdf",
                document_id,
            ),
        )
        self.conn.execute(
            "INSERT INTO documents VALUES (?, ?, NULL, NULL)",
            (document_id, title),
        )
        if markdown is not None:
            (self.parsed_dir / f"{document_id}.md").write_text(
                markdown,
                encoding="utf-8",
            )
        self.conn.commit()

    def test_finds_only_events_whose_expected_period_differs(self) -> None:
        generic_title = (
            "KEC International Limited has informed the Exchange "
            "about Investor Presentation"
        )
        self.add_event(
            event_id="shifted",
            event_date="2024-07-26",
            fiscal_year=2024,
            fiscal_quarter=2,
            title=generic_title,
        )
        self.add_event(
            event_id="aligned",
            event_date="2024-07-26",
            fiscal_year=2024,
            fiscal_quarter=1,
            title=generic_title,
        )

        events = find_misaligned_events(self.conn, db_path=self.db_path)

        self.assertEqual([event.event_id for event in events], ["shifted"])
        self.assertEqual(events[0].stored_label, "Q2 FY2024-25")
        self.assertEqual(events[0].expected_label, "Q1 FY2024-25")
        self.assertEqual(
            events[0].detection_source,
            "previous_completed_quarter_fallback",
        )

    def test_uses_title_to_correct_stale_document_period(self) -> None:
        self.add_event(
            event_id="stale-cover",
            event_date="2024-05-07",
            fiscal_year=2022,
            fiscal_quarter=4,
            event_type="Financial Results",
            title="Financial results for the period ended March 31, 2024",
            markdown=(
                "Financial Results for the quarter and year "
                "ended March 31, 2023"
            ),
        )

        events = find_misaligned_events(self.conn, db_path=self.db_path)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].expected_label, "Q4 FY2023-24")
        self.assertEqual(events[0].detection_source, "title")

    def test_previous_quarter_fallback_crosses_fiscal_year(self) -> None:
        period = expected_reporting_period(
            markdown="Business highlights",
            title="Investor Presentation",
            event_date="2024-05-07",
        )

        self.assertEqual(period.label, "Q4 FY2023-24")
        self.assertEqual(period.quarter_end, "2024-03-31")


if __name__ == "__main__":
    unittest.main()
