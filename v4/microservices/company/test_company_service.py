import sqlite3
import unittest

from company_service import company_id_for_symbol, register_company


class CompanyServiceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_directory_metadata_survives_later_symbol_only_registration(self):
        first = register_company(
            self.conn,
            "TCS",
            name="Tata Consultancy Services Limited",
            isin="INE467B01029",
        )
        second = register_company(self.conn, "TCS")
        self.assertEqual(company_id_for_symbol("TCS"), first["id"])
        self.assertEqual("Tata Consultancy Services Limited", second["name"])
        self.assertEqual("INE467B01029", second["isin"])


if __name__ == "__main__":
    unittest.main()
