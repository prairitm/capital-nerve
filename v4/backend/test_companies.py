import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from routers.companies import list_companies


class CompanyListTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE companies (
              id TEXT PRIMARY KEY, name TEXT, ticker TEXT, exchange TEXT,
              sector TEXT, industry TEXT, isin TEXT
            );
            CREATE TABLE events (
              id TEXT PRIMARY KEY, company_id TEXT, event_type TEXT,
              event_type_raw TEXT, event_date TEXT, fiscal_year INTEGER,
              fiscal_quarter INTEGER, title TEXT, source_url TEXT,
              document_id TEXT, status TEXT
            );
            CREATE TABLE signals (
              id TEXT PRIMARY KEY, company_id TEXT, severity TEXT
            );
            INSERT INTO companies VALUES ('a','Alpha Ltd','ALPHA','NSE',NULL,'Software',NULL);
            INSERT INTO companies VALUES ('b','Beta Ltd','BETA','NSE',NULL,NULL,NULL);
            INSERT INTO events VALUES ('e1','a','FINANCIAL_RESULT',NULL,'2026-05-10',2025,4,NULL,NULL,NULL,'processed');
            INSERT INTO signals VALUES ('s1','a','LOW');
            INSERT INTO signals VALUES ('s2','a','CRITICAL');
            """
        )
        conn.close()

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def test_enriched_fields_and_empty_company(self):
        with patch("routers.companies.get_conn", self.connection):
            rows = list_companies(limit=200)
        self.assertEqual(2, len(rows))
        self.assertEqual("Q4 FY2025-26", rows[0]["latest_period_label"])
        self.assertEqual(2, rows[0]["signal_count"])
        self.assertEqual("CRITICAL", rows[0]["highest_severity"])
        self.assertIsNone(rows[1]["latest_event_date"])
        self.assertEqual(0, rows[1]["signal_count"])

    def test_search_and_limit_remain_supported(self):
        with patch("routers.companies.get_conn", self.connection):
            rows = list_companies(search="beta", limit=1)
        self.assertEqual(["BETA"], [row["ticker"] for row in rows])


if __name__ == "__main__":
    unittest.main()
