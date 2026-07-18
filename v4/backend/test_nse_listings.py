import tempfile
import unittest
from pathlib import Path

from app_db import get_app_conn, migrate_app_db
from config import settings
from nse_listings import parse_nse_equity_csv, replace_nse_listings


SAMPLE = """SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, ISIN NUMBER
TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,INE467B01029
AAREYDRUGS,Aarey Drugs & Pharmaceuticals Limited,BE,06-AUG-2021,INE198H01019
"""


class NseListingsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = settings.app_db_path
        settings.app_db_path = Path(self.temp.name) / "app.db"
        migrate_app_db()

    def tearDown(self):
        settings.app_db_path = self.original_path
        self.temp.cleanup()

    def test_parse_normalizes_official_headers_and_series(self):
        rows = parse_nse_equity_csv(SAMPLE)
        self.assertEqual(["TCS", "AAREYDRUGS"], [row["symbol"] for row in rows])
        self.assertEqual("BE", rows[1]["series"])
        self.assertEqual("INE467B01029", rows[0]["isin"])

    def test_replace_keeps_missing_symbols_as_inactive(self):
        rows = parse_nse_equity_csv(SAMPLE)
        replace_nse_listings(rows)
        replace_nse_listings(rows[:1])
        with get_app_conn() as conn:
            state = {
                row["symbol"]: row["is_active"]
                for row in conn.execute(
                    "SELECT symbol, is_active FROM nse_listings ORDER BY symbol"
                ).fetchall()
            }
        self.assertEqual({"AAREYDRUGS": 0, "TCS": 1}, state)

    def test_empty_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_nse_equity_csv("SYMBOL,NAME OF COMPANY\n")
        with self.assertRaises(ValueError):
            replace_nse_listings([])


if __name__ == "__main__":
    unittest.main()
