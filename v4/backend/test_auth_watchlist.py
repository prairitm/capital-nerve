import hashlib
import sqlite3
import tempfile
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app_db import get_app_conn, migrate_app_db, utc_iso, utc_now
from config import settings
from main import app
from security import bootstrap_admin, hash_password


class AuthWatchlistApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = {
            "db_path": settings.db_path,
            "app_db_path": settings.app_db_path,
            "admin_email": settings.admin_email,
            "admin_password": settings.admin_password,
            "cookie_secure": settings.cookie_secure,
            "nse_refresh_on_startup": settings.nse_refresh_on_startup,
        }
        settings.db_path = Path(self.temp.name) / "analytics.db"
        settings.app_db_path = Path(self.temp.name) / "app.db"
        settings.admin_email = None
        settings.admin_password = None
        settings.cookie_secure = False
        settings.nse_refresh_on_startup = False
        self._create_analytics_db()
        migrate_app_db()
        self.admin_id = self._create_user(
            "admin@example.com", "Administrator", "ADMIN", "AdminPassword123!", False
        )
        self.member_id = self._create_user(
            "member@example.com", "Member", "MEMBER", "MemberPassword123!", False
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        for key, value in self.original.items():
            setattr(settings, key, value)
        self.temp.cleanup()

    def _create_analytics_db(self):
        conn = sqlite3.connect(settings.db_path)
        conn.executescript(
            """
            CREATE TABLE companies (
                id TEXT PRIMARY KEY, name TEXT, ticker TEXT, exchange TEXT,
                sector TEXT, industry TEXT, isin TEXT
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY, company_id TEXT, event_type TEXT,
                event_date TEXT, fiscal_year INTEGER, fiscal_quarter INTEGER,
                title TEXT, source_url TEXT, document_id TEXT, status TEXT
            );
            CREATE TABLE documents (
                id TEXT PRIMARY KEY, company_id TEXT, source_url TEXT,
                storage_path TEXT, sha256 TEXT, title TEXT,
                document_kind TEXT, file_size INTEGER, status TEXT,
                error_message TEXT, ingested_at TEXT
            );
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY, company_id TEXT, event_id TEXT,
                signal_code TEXT, severity TEXT, direction TEXT,
                supporting_metric_ids TEXT, supporting_fact_ids TEXT
            );
            INSERT INTO companies VALUES
                ('alpha-id', 'Alpha Ltd', 'ALPHA', 'NSE', 'Technology', 'Software', NULL),
                ('beta-id', 'Beta Ltd', 'BETA', 'NSE', 'Industrials', 'Engineering', NULL);
            INSERT INTO events VALUES
                ('event-1', 'alpha-id', 'Financial Results', '2026-05-10', 2025, 4,
                 'Results', NULL, 'document-1', 'processed'),
                ('event-2', 'beta-id', 'Investor Presentation', '2026-05-11', 2025, 4,
                 'Presentation', NULL, 'document-2', 'processed');
            INSERT INTO documents VALUES
                ('document-1', 'alpha-id', NULL, '/tmp/alpha.pdf', 'sha-alpha',
                 'Results', 'financial_result', 100, 'processed', NULL, '2026-05-10'),
                ('document-2', 'beta-id', NULL, '/tmp/beta.pdf', 'sha-beta',
                 'Presentation', 'investor_presentation', 100, 'processed', NULL, '2026-05-11');
            INSERT INTO signals VALUES
                ('signal-1', 'alpha-id', 'event-1', 'revenue_growth', 'HIGH', 'POSITIVE', '[]', '[]');
            """
        )
        conn.close()

    def _create_user(self, email, name, role, password, must_change):
        user_id = str(uuid.uuid4())
        now = utc_iso()
        with get_app_conn() as conn:
            conn.execute(
                """
                INSERT INTO users(
                    id, email, full_name, password_hash, role, is_active,
                    must_change_password, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (user_id, email, name, hash_password(password), role, int(must_change), now, now),
            )
            conn.commit()
        return user_id

    def _login(self, email="member@example.com", password="MemberPassword123!"):
        response = self.client.post("/auth/login", json={"email": email, "password": password})
        self.assertEqual(200, response.status_code, response.text)
        return response

    def test_login_cookie_logout_and_protected_routes(self):
        self.assertEqual(401, self.client.get("/companies").status_code)
        bad = self.client.post(
            "/auth/login", json={"email": "missing@example.com", "password": "wrong"}
        )
        self.assertEqual(401, bad.status_code)
        self.assertEqual("invalid_credentials", bad.json()["detail"]["code"])

        login = self._login()
        cookie = login.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertEqual("MEMBER", self.client.get("/auth/me").json()["role"])
        self.assertEqual(200, self.client.get("/companies").status_code)
        logout = self.client.post("/auth/logout")
        self.assertEqual(204, logout.status_code)
        self.assertEqual(401, self.client.get("/auth/me").status_code)

    def test_forced_password_change_and_session_expiry(self):
        self._create_user(
            "temporary@example.com", "Temporary", "MEMBER", "TemporaryPass123!", True
        )
        self._login("temporary@example.com", "TemporaryPass123!")
        blocked = self.client.get("/companies")
        self.assertEqual(403, blocked.status_code)
        self.assertEqual("password_change_required", blocked.json()["detail"]["code"])
        changed = self.client.post(
            "/auth/change-password",
            json={"current_password": "TemporaryPass123!", "new_password": "PermanentPass123!"},
        )
        self.assertEqual(200, changed.status_code, changed.text)
        self.assertFalse(changed.json()["must_change_password"])
        self.assertEqual(200, self.client.get("/companies").status_code)

        with get_app_conn() as conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ?",
                (utc_iso(utc_now() - timedelta(seconds=1)),),
            )
            conn.commit()
        self.assertEqual(401, self.client.get("/auth/me").status_code)

    def test_admin_lifecycle_and_member_forbidden(self):
        self._login()
        self.assertEqual(403, self.client.get("/admin/users").status_code)
        self.client.post("/auth/logout")
        self._login("admin@example.com", "AdminPassword123!")
        created = self.client.post(
            "/admin/users",
            json={"email": "NewUser@Example.com", "full_name": "New User", "role": "MEMBER"},
        )
        self.assertEqual(201, created.status_code, created.text)
        payload = created.json()
        self.assertGreaterEqual(len(payload["temporary_password"]), 20)
        user_id = payload["user"]["id"]
        duplicate = self.client.post(
            "/admin/users", json={"email": "newuser@example.com", "role": "MEMBER"}
        )
        self.assertEqual(409, duplicate.status_code)
        updated = self.client.patch(
            f"/admin/users/{user_id}",
            json={"full_name": "Updated User", "role": "ADMIN", "is_active": True},
        )
        self.assertEqual(200, updated.status_code, updated.text)
        self.assertEqual("ADMIN", updated.json()["role"])
        reset = self.client.post(f"/admin/users/{user_id}/reset-password")
        self.assertEqual(200, reset.status_code)
        self.assertTrue(reset.json()["user"]["must_change_password"])
        self_change = self.client.patch(
            f"/admin/users/{self.admin_id}", json={"role": "MEMBER"}
        )
        self.assertEqual(400, self_change.status_code)
        self.assertEqual("self_admin_change", self_change.json()["detail"]["code"])

    def test_watchlists_are_private_idempotent_and_enriched(self):
        self._login()
        first = self.client.put("/watchlist/companies/alpha-id")
        second = self.client.put("/watchlist/companies/alpha-id")
        self.assertTrue(first.json()["added"])
        self.assertFalse(second.json()["added"])
        self.assertEqual(404, self.client.put("/watchlist/companies/missing").status_code)
        watched = self.client.get("/watchlist").json()
        self.assertEqual(1, watched["count"])
        self.assertEqual("ALPHA", watched["companies"][0]["ticker"])
        self.assertTrue(watched["companies"][0]["watchlist_status"])
        companies = self.client.get("/companies").json()
        self.assertTrue(next(row for row in companies if row["id"] == "alpha-id")["watchlist_status"])
        analytics = sqlite3.connect(settings.db_path)
        analytics.execute(
            "INSERT INTO companies VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("gamma-id", "Gamma Ltd", "GAMMA", "NSE", None, None, None),
        )
        analytics.commit()
        analytics.close()
        search = self.client.get("/companies", params={"search": "gamma"}).json()
        self.assertEqual(["GAMMA"], [row["ticker"] for row in search])

        self.client.post("/auth/logout")
        self._login("admin@example.com", "AdminPassword123!")
        self.assertEqual(0, self.client.get("/watchlist").json()["count"])
        self.client.post("/auth/logout")
        self._login()
        removed = self.client.delete("/watchlist/companies/alpha-id")
        self.assertTrue(removed.json()["removed"])
        self.assertFalse(self.client.delete("/watchlist/companies/alpha-id").json()["removed"])
        with get_app_conn() as conn:
            conn.execute(
                "UPDATE company_poll_state SET baseline_at = '2000-01-01' WHERE company_id = 'alpha-id'"
            )
            conn.commit()
        self.assertTrue(self.client.put("/watchlist/companies/alpha-id").json()["added"])
        with get_app_conn() as conn:
            baseline = conn.execute(
                "SELECT baseline_at FROM company_poll_state WHERE company_id = 'alpha-id'"
            ).fetchone()["baseline_at"]
        self.assertNotEqual("2000-01-01", baseline)

    def test_nse_directory_search_and_watch_by_symbol(self):
        with get_app_conn() as conn:
            now = utc_iso()
            conn.executemany(
                """
                INSERT INTO nse_listings(
                    symbol, company_name, series, listing_date, isin, is_active, refreshed_at
                ) VALUES (?, ?, 'EQ', NULL, ?, 1, ?)
                """,
                [
                    ("TCS", "Tata Consultancy Services Limited", "INE467B01029", now),
                    ("TATAMOTORS", "Tata Motors Limited", "INE155A01022", now),
                ],
            )
            conn.commit()
        self._login()
        results = self.client.get("/nse-companies/search", params={"q": "tata"})
        self.assertEqual(200, results.status_code, results.text)
        self.assertEqual(["TATAMOTORS", "TCS"], [row["symbol"] for row in results.json()])
        self.assertTrue(all(row["coverage_status"] == "available" for row in results.json()))

        company_id = hashlib.sha256("TCS:NSE".encode()).hexdigest()

        def register(listing):
            analytics = sqlite3.connect(settings.db_path)
            analytics.execute(
                "INSERT INTO companies VALUES (?, ?, ?, 'NSE', NULL, NULL, ?)",
                (company_id, listing["company_name"], listing["symbol"], listing["isin"]),
            )
            analytics.commit()
            analytics.close()
            return {
                "id": company_id,
                "name": listing["company_name"],
                "ticker": listing["symbol"],
                "exchange": "NSE",
                "sector": None,
                "industry": None,
                "isin": listing["isin"],
            }

        with patch("routers.watchlist.register_company_for_listing", side_effect=register):
            watched = self.client.put("/watchlist/companies/by-symbol/tcs")
        self.assertEqual(200, watched.status_code, watched.text)
        self.assertTrue(watched.json()["added"])
        self.assertEqual("TCS", watched.json()["company"]["ticker"])
        refreshed = self.client.get("/nse-companies/search", params={"q": "TCS"}).json()
        self.assertEqual("watched", refreshed[0]["coverage_status"])

        missing = self.client.put("/watchlist/companies/by-symbol/not-listed")
        self.assertEqual(404, missing.status_code)

    def test_stale_watchlist_company_is_omitted(self):
        self._login()
        self.client.put("/watchlist/companies/beta-id")
        analytics = sqlite3.connect(settings.db_path)
        analytics.execute("DELETE FROM companies WHERE id = 'beta-id'")
        analytics.commit()
        analytics.close()
        response = self.client.get("/watchlist")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"companies": [], "count": 0}, response.json())

    def test_feed_is_watchlist_scoped_and_includes_zero_signal_filings(self):
        self._login()
        self.client.put("/watchlist/companies/alpha-id")
        member_feed = self.client.get("/feed")
        self.assertEqual(200, member_feed.status_code, member_feed.text)
        self.assertEqual(["event-1"], [item["event"]["id"] for item in member_feed.json()])
        self.assertIn("signals", member_feed.json()[0])

        self.client.post("/auth/logout")
        self._login("admin@example.com", "AdminPassword123!")
        self.client.put("/watchlist/companies/alpha-id")
        self.assertEqual(["event-1"], [item["event"]["id"] for item in self.client.get("/feed").json()])
        self.client.put("/watchlist/companies/beta-id")
        admin_feed = self.client.get("/feed")
        self.assertEqual(["event-2", "event-1"], [item["event"]["id"] for item in admin_feed.json()])
        self.assertEqual([], next(item for item in admin_feed.json() if item["event"]["id"] == "event-2")["signals"])
        self.assertEqual([], self.client.get("/feed", params={"offset": 2}).json())

        now = utc_iso()
        with get_app_conn() as conn:
            conn.execute(
                """
                INSERT INTO pipeline_jobs(
                    id, event_id, canonical_event_id, pipeline_version, company_id,
                    symbol, event_type, source_url, published_at, from_date, to_date,
                    status, attempts, max_attempts, available_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'v4-1', ?, 'BETA', 'Investor Presentation',
                          'https://example.com/beta.pdf', ?, '10-05-2026', '11-05-2026',
                          'queued', 0, 5, ?, ?, ?)
                """,
                ("job-2", "event-2", "event-2", "beta-id", now, now, now, now),
            )
            conn.commit()
        self.assertEqual(["event-1"], [item["event"]["id"] for item in self.client.get("/feed").json()])
        with get_app_conn() as conn:
            conn.execute("UPDATE pipeline_jobs SET status = 'succeeded' WHERE id = 'job-2'")
            conn.commit()
        self.assertEqual(["event-2", "event-1"], [item["event"]["id"] for item in self.client.get("/feed").json()])
        summary = self.client.get("/feed/summary").json()
        self.assertEqual(2, summary["processed_filings"])
        self.assertEqual(0, summary["total_signals"])

        self.client.delete("/watchlist/companies/beta-id")
        self.assertEqual(["event-1"], [item["event"]["id"] for item in self.client.get("/feed").json()])

    def test_migration_and_admin_bootstrap_are_idempotent(self):
        migrate_app_db()
        with get_app_conn() as conn:
            versions = conn.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()[
                "count"
            ]
        self.assertEqual(3, versions)
        settings.admin_email = "bootstrap@example.com"
        settings.admin_password = "BootstrapPassword123!"
        bootstrap_admin()
        bootstrap_admin()
        with get_app_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE email = 'bootstrap@example.com'"
            ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("ADMIN", rows[0]["role"])

    def test_inactive_user_sessions_are_revoked(self):
        self._login()
        with get_app_conn() as conn:
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (self.member_id,))
            conn.commit()
        response = self.client.get("/auth/me")
        self.assertEqual(403, response.status_code)
        self.assertEqual("inactive_account", response.json()["detail"]["code"])
        with get_app_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM sessions WHERE user_id = ?", (self.member_id,)
            ).fetchone()["count"]
        self.assertEqual(0, count)


if __name__ == "__main__":
    unittest.main()
