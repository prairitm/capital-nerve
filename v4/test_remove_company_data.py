from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


V4_DIR = Path(__file__).resolve().parent
SCRIPT = V4_DIR / "remove_company_data.py"


class RemoveCompanyDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.analytics_db = self.root / "analytics.db"
        self.app_db = self.root / "app.db"
        self.documents_dir = self.root / "documents"
        self.parsed_dir = self.root / "parsed"
        self.documents_dir.mkdir()
        self.parsed_dir.mkdir()

        with sqlite3.connect(self.analytics_db) as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE companies (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, ticker TEXT, isin TEXT
                );
                CREATE TABLE events (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL REFERENCES companies(id)
                );
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL REFERENCES companies(id),
                    storage_path TEXT NOT NULL
                );
                CREATE TABLE signals (
                    signal_id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL REFERENCES companies(id),
                    event_id TEXT NOT NULL REFERENCES events(id)
                );
                """
            )
            conn.executemany(
                "INSERT INTO companies VALUES (?, ?, ?, ?)",
                [
                    ("alpha-id", "Alpha Ltd", "ALPHA", "INE000A"),
                    ("beta-id", "Beta Ltd", "BETA", "INE000B"),
                ],
            )
            conn.executemany(
                "INSERT INTO events VALUES (?, ?)",
                [("alpha-event", "alpha-id"), ("beta-event", "beta-id")],
            )
            conn.executemany(
                "INSERT INTO documents VALUES (?, ?, ?)",
                [
                    ("alpha-doc", "alpha-id", str(self.documents_dir / "alpha-doc.pdf")),
                    ("beta-doc", "beta-id", str(self.documents_dir / "beta-doc.pdf")),
                ],
            )
            conn.executemany(
                "INSERT INTO signals VALUES (?, ?, ?)",
                [
                    ("alpha-signal", "alpha-id", "alpha-event"),
                    ("beta-signal", "beta-id", "beta-event"),
                ],
            )

        with sqlite3.connect(self.app_db) as conn:
            conn.executescript(
                """
                CREATE TABLE watchlist_companies (user_id TEXT, company_id TEXT);
                CREATE TABLE pipeline_jobs (id TEXT PRIMARY KEY, company_id TEXT);
                """
            )
            conn.executemany(
                "INSERT INTO watchlist_companies VALUES (?, ?)",
                [("user", "alpha-id"), ("user", "beta-id")],
            )
            conn.executemany(
                "INSERT INTO pipeline_jobs VALUES (?, ?)",
                [("alpha-job", "alpha-id"), ("beta-job", "beta-id")],
            )

        for name in ("alpha-doc.pdf", "beta-doc.pdf"):
            (self.documents_dir / name).write_bytes(b"pdf")
        for name in ("alpha-doc.md", "alpha-doc.meta.json", "beta-doc.md"):
            (self.parsed_dir / name).write_text("parsed", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--symbol",
                "alpha",
                "--analytics-db",
                str(self.analytics_db),
                "--app-db",
                str(self.app_db),
                "--documents-dir",
                str(self.documents_dir),
                "--parsed-dir",
                str(self.parsed_dir),
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_dry_run_changes_nothing(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run only", result.stdout)
        with sqlite3.connect(self.analytics_db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0], 2)
        self.assertTrue((self.documents_dir / "alpha-doc.pdf").exists())

    def test_confirm_removes_only_selected_company(self) -> None:
        result = self.run_script("--confirm")
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(self.analytics_db) as conn:
            for table in ("companies", "events", "documents", "signals"):
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                self.assertEqual(len(rows), 1, table)
                self.assertIn("beta", " ".join(map(str, rows[0])).lower(), table)
        with sqlite3.connect(self.app_db) as conn:
            for table in ("watchlist_companies", "pipeline_jobs"):
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                self.assertEqual(len(rows), 1, table)
                self.assertIn("beta-id", rows[0], table)
        self.assertFalse((self.documents_dir / "alpha-doc.pdf").exists())
        self.assertFalse((self.parsed_dir / "alpha-doc.md").exists())
        self.assertFalse((self.parsed_dir / "alpha-doc.meta.json").exists())
        self.assertTrue((self.documents_dir / "beta-doc.pdf").exists())
        self.assertTrue((self.parsed_dir / "beta-doc.md").exists())


if __name__ == "__main__":
    unittest.main()
