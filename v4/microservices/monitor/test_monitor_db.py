from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.monitor_db import (
    claim_due_company,
    claim_job,
    complete_job,
    enqueue_job,
    ensure_watch_states,
    fail_job,
    job_counts,
    reserve_canonical_job,
)


MIGRATION = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "002_filing_monitor.sql"


class MonitorDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "app.db"
        conn = sqlite3.connect(self.path)
        conn.executescript(
            """
            CREATE TABLE users (id TEXT PRIMARY KEY, is_active INTEGER NOT NULL);
            CREATE TABLE watchlist_companies (user_id TEXT, company_id TEXT, added_at TEXT);
            """
        )
        conn.executescript(MIGRATION.read_text(encoding="utf-8"))
        conn.close()
        self.event = {
            "event_id": "a" * 64,
            "company_id": "b" * 64,
            "symbol": "EXAMPLE",
            "event_type": "Financial Results",
            "source_url": "https://example.com/results.pdf",
            "title": "Results",
            "published_at": "2026-07-18T10:00:00+00:00",
            "from_date": "17-07-2026",
            "to_date": "18-07-2026",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_enqueue_claim_complete_is_idempotent(self) -> None:
        self.assertTrue(enqueue_job(self.path, pipeline_version="v4-1", max_attempts=5, event=self.event))
        self.assertFalse(enqueue_job(self.path, pipeline_version="v4-1", max_attempts=5, event=self.event))
        job = claim_job(self.path, "worker", 60)
        self.assertIsNotNone(job)
        self.assertEqual(1, job["attempts"])
        self.assertTrue(reserve_canonical_job(self.path, job["id"], "c" * 64))
        complete_job(self.path, job["id"], "c" * 64)
        self.assertEqual(1, job_counts(self.path)["succeeded"])

    def test_failed_job_is_requeued_before_attempt_limit(self) -> None:
        enqueue_job(self.path, pipeline_version="v4-1", max_attempts=2, event=self.event)
        job = claim_job(self.path, "worker", 60)
        fail_job(self.path, job, "temporary failure")
        counts = job_counts(self.path)
        self.assertEqual(1, counts["queued"])
        self.assertEqual(0, counts["failed"])

    def test_multiple_watchers_share_one_due_company(self) -> None:
        conn = sqlite3.connect(self.path)
        conn.executemany("INSERT INTO users(id, is_active) VALUES (?, 1)", [("u1",), ("u2",)])
        conn.executemany(
            "INSERT INTO watchlist_companies(user_id, company_id, added_at) VALUES (?, ?, ?)",
            [("u1", "company", "2026-07-18"), ("u2", "company", "2026-07-18")],
        )
        conn.commit()
        conn.close()
        ensure_watch_states(self.path)

        first = claim_due_company(self.path, 60)
        second = claim_due_company(self.path, 60)
        self.assertEqual("company", first["company_id"])
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
