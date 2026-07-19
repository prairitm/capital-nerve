from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from reviews import (
    AppliedReviewDecisionError,
    InvalidReviewDecisionError,
    list_review_items,
    record_review_decision,
    reopen_review,
    review_summary,
)


class ReviewQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.analytics = sqlite3.connect(":memory:")
        self.analytics.row_factory = sqlite3.Row
        self.app = sqlite3.connect(":memory:")
        self.app.row_factory = sqlite3.Row
        self.app.execute("PRAGMA foreign_keys = ON")
        self._seed_analytics()
        self._seed_app()

    def tearDown(self) -> None:
        self.analytics.close()
        self.app.close()

    def _seed_analytics(self) -> None:
        self.analytics.executescript(
            """
            CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT, ticker TEXT);
            CREATE TABLE events (
                id TEXT PRIMARY KEY, company_id TEXT, event_date TEXT, title TEXT
            );
            CREATE TABLE documents (id TEXT PRIMARY KEY, title TEXT);
            CREATE TABLE fact_definitions (fact_code TEXT PRIMARY KEY, fact_name TEXT);
            CREATE TABLE fact_observations (
                observation_id TEXT PRIMARY KEY, company_id TEXT, event_id TEXT,
                document_id TEXT, fact_code TEXT, value REAL, value_text TEXT,
                unit TEXT, period TEXT, period_type TEXT, basis TEXT,
                source_page INTEGER, source_text TEXT, extraction_method TEXT,
                confidence REAL
            );
            CREATE TABLE resolved_facts (
                resolved_fact_id TEXT PRIMARY KEY, company_id TEXT, event_id TEXT,
                fact_code TEXT, resolved_value REAL, resolved_value_text TEXT,
                unit TEXT, period TEXT, period_type TEXT, basis TEXT,
                selected_observation_id TEXT, resolution_status TEXT,
                confidence REAL
            );
            INSERT INTO companies VALUES ('company', 'Example Limited', 'EXAMPLE');
            INSERT INTO events VALUES ('event', 'company', '2026-01-20', 'Nine month results');
            INSERT INTO documents VALUES ('document', 'Results filing');
            INSERT INTO fact_definitions VALUES ('revenue_from_operations', 'Revenue from operations');
            INSERT INTO fact_observations VALUES
                ('obs-a', 'company', 'event', 'document', 'revenue_from_operations',
                 1234.5, NULL, 'crore', '2025-12-31', 'nine_months', 'consolidated',
                 7, 'Revenue from operations | 1,234.50', 'deterministic_period_column', 0.92),
                ('obs-b', 'company', 'event', 'document', 'revenue_from_operations',
                 999.0, NULL, 'crore', '2025-12-31', 'nine_months', 'consolidated',
                 12, 'Revenue from operations | 999.00', 'llm_financial_result', 0.90);
            INSERT INTO resolved_facts VALUES
                ('resolved', 'company', 'event', 'revenue_from_operations',
                 1234.5, NULL, 'crore', '2025-12-31', 'nine_months', 'consolidated',
                 'obs-a', 'review_required', 0.92);
            """
        )

    def _seed_app(self) -> None:
        self.app.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY, email TEXT, full_name TEXT
            );
            INSERT INTO users VALUES ('admin', 'admin@example.com', 'Admin');
            """
        )
        migrations = Path(__file__).resolve().parent / "migrations"
        self.app.executescript(
            (migrations / "002_fact_review_queue.sql").read_text(encoding="utf-8")
        )
        self.app.executescript(
            (migrations / "003_review_reconciliation.sql").read_text(encoding="utf-8")
        )

    def test_lists_open_item_with_matching_candidates(self) -> None:
        items = list_review_items(self.analytics, self.app)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["queue_status"], "open")
        self.assertEqual(items[0]["basis"], "consolidated")
        self.assertEqual(items[0]["period_type"], "nine_months")
        self.assertEqual(
            [candidate["observation_id"] for candidate in items[0]["candidates"]],
            ["obs-a", "obs-b"],
        )
        self.assertEqual(
            review_summary(self.analytics, self.app),
            {"open": 1, "approved": 0, "rejected": 0, "total": 1},
        )

    def test_approval_is_audited_and_can_be_reopened(self) -> None:
        with self.assertRaises(InvalidReviewDecisionError):
            record_review_decision(
                self.analytics,
                self.app,
                resolved_fact_id="resolved",
                decision="approved",
                selected_observation_id="not-a-candidate",
                reviewer_note=None,
                reviewed_by="admin",
                timestamp="2026-07-17T10:00:00+00:00",
            )
        item = record_review_decision(
            self.analytics,
            self.app,
            resolved_fact_id="resolved",
            decision="approved",
            selected_observation_id="obs-a",
            reviewer_note="Checked against PDF page 7.",
            reviewed_by="admin",
            timestamp="2026-07-17T10:00:00+00:00",
        )
        self.assertEqual(item["queue_status"], "approved")
        self.assertEqual(item["decision"]["reviewer_email"], "admin@example.com")
        self.assertEqual(item["decision"]["application_status"], "pending")
        self.assertEqual(len(list_review_items(self.analytics, self.app)), 0)
        self.assertTrue(reopen_review(self.app, "resolved"))
        self.assertEqual(len(list_review_items(self.analytics, self.app)), 1)

    def test_applied_approval_cannot_be_reopened(self) -> None:
        record_review_decision(
            self.analytics,
            self.app,
            resolved_fact_id="resolved",
            decision="approved",
            selected_observation_id="obs-a",
            reviewer_note=None,
            reviewed_by="admin",
            timestamp="2026-07-17T10:00:00+00:00",
        )
        self.app.execute(
            "UPDATE fact_review_decisions SET application_status = 'applied'"
        )
        self.app.commit()
        with self.assertRaises(AppliedReviewDecisionError):
            reopen_review(self.app, "resolved")

    def test_rejection_requires_a_note(self) -> None:
        with self.assertRaises(InvalidReviewDecisionError):
            record_review_decision(
                self.analytics,
                self.app,
                resolved_fact_id="resolved",
                decision="rejected",
                selected_observation_id=None,
                reviewer_note="",
                reviewed_by="admin",
                timestamp="2026-07-17T10:00:00+00:00",
            )


if __name__ == "__main__":
    unittest.main()
