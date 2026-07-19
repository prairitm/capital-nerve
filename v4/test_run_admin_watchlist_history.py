from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from run_admin_watchlist_history import (
    BatchError,
    completed_quarters,
    resolve_admin,
    resolve_companies,
    watchlist_company_ids,
)


class QuarterWindowTests(unittest.TestCase):
    def test_returns_eight_completed_quarters_oldest_first(self) -> None:
        windows = completed_quarters(date(2026, 7, 19), 8)

        self.assertEqual(date(2024, 7, 1), windows[0].start)
        self.assertEqual(date(2024, 9, 30), windows[0].end)
        self.assertEqual(date(2026, 4, 1), windows[-1].start)
        self.assertEqual(date(2026, 6, 30), windows[-1].end)
        self.assertEqual("01-04-2026", windows[-1].from_date)
        self.assertEqual("30-06-2026", windows[-1].to_date)

    def test_includes_quarter_on_its_last_day(self) -> None:
        window = completed_quarters(date(2026, 6, 30), 1)[0]
        self.assertEqual("2026 Q2", window.label)


class WatchlistResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.app_db = self.root / "app.db"
        self.analytics_db = self.root / "analytics.db"

        with sqlite3.connect(self.app_db) as conn:
            conn.executescript(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY, email TEXT, role TEXT, is_active INTEGER,
                    created_at TEXT
                );
                CREATE TABLE watchlist_companies (
                    user_id TEXT, company_id TEXT, added_at TEXT
                );
                INSERT INTO users VALUES
                    ('admin', 'admin@example.com', 'ADMIN', 1, '2026-01-01'),
                    ('member', 'member@example.com', 'MEMBER', 1, '2026-01-02');
                INSERT INTO watchlist_companies VALUES
                    ('admin', 'company-b', '2026-02-02'),
                    ('admin', 'company-a', '2026-02-01'),
                    ('member', 'company-c', '2026-02-01');
                """
            )
        with sqlite3.connect(self.analytics_db) as conn:
            conn.executescript(
                """
                CREATE TABLE companies (id TEXT PRIMARY KEY, ticker TEXT, name TEXT);
                INSERT INTO companies VALUES
                    ('company-a', 'aaa', 'Company A'),
                    ('company-b', 'BBB', 'Company B');
                """
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_only_admin_watchlist_in_added_order(self) -> None:
        with sqlite3.connect(self.app_db) as conn:
            conn.row_factory = sqlite3.Row
            admin = resolve_admin(conn, None)
            ids = watchlist_company_ids(conn, admin["id"])

        companies = resolve_companies(self.analytics_db, ids)
        self.assertEqual(["AAA", "BBB"], [company.symbol for company in companies])

    def test_requires_email_when_multiple_active_admins_exist(self) -> None:
        with sqlite3.connect(self.app_db) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "INSERT INTO users VALUES ('admin-2', 'second@example.com', 'ADMIN', 1, '2026-01-03')"
            )
            with self.assertRaisesRegex(BatchError, "Multiple active administrators"):
                resolve_admin(conn, None)
            selected = resolve_admin(conn, "SECOND@example.com")
        self.assertEqual("admin-2", selected["id"])


if __name__ == "__main__":
    unittest.main()
