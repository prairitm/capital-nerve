from __future__ import annotations

import sqlite3
import sys
import unittest
import hashlib
from pathlib import Path

MICROSERVICES_DIR = Path(__file__).resolve().parent
if str(MICROSERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(MICROSERVICES_DIR))

from reconcile_reviews import apply_approved_reviews, preview_approved_reviews, recompute_event


class ReviewReconciliationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.analytics = sqlite3.connect(":memory:")
        self.analytics.row_factory = sqlite3.Row
        self.app = sqlite3.connect(":memory:")
        self.app.row_factory = sqlite3.Row
        self._seed_analytics()
        self._seed_app()

    def tearDown(self) -> None:
        self.analytics.close()
        self.app.close()

    def _seed_analytics(self) -> None:
        self.analytics.executescript(
            """
            CREATE TABLE companies (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, ticker TEXT
            );
            CREATE TABLE events (
                id TEXT PRIMARY KEY, company_id TEXT NOT NULL, event_type TEXT,
                event_date TEXT, fiscal_year INTEGER, fiscal_quarter INTEGER,
                title TEXT
            );
            CREATE TABLE fact_observations (
                observation_id TEXT PRIMARY KEY, company_id TEXT, event_id TEXT,
                document_id TEXT, fact_code TEXT, value REAL, value_text TEXT,
                unit TEXT, period TEXT, period_type TEXT, basis TEXT,
                source_page INTEGER, source_text TEXT, confidence REAL,
                segment TEXT, geography TEXT, product TEXT, channel TEXT,
                project TEXT, customer_type TEXT, metric_context TEXT,
                scope_level TEXT, scope_name TEXT, fact_type TEXT,
                extraction_method TEXT, value_lower REAL, value_upper REAL,
                sentiment TEXT, is_explicit_guidance INTEGER
            );
            CREATE TABLE resolved_facts (
                resolved_fact_id TEXT PRIMARY KEY, company_id TEXT, event_id TEXT,
                fact_code TEXT, resolved_value REAL, resolved_value_text TEXT,
                unit TEXT, period TEXT, period_type TEXT, basis TEXT,
                segment TEXT, geography TEXT, product TEXT, channel TEXT,
                project TEXT, customer_type TEXT, metric_context TEXT,
                scope_level TEXT, scope_name TEXT, fact_type TEXT,
                value_lower REAL, value_upper REAL, sentiment TEXT,
                is_explicit_guidance INTEGER, selected_observation_id TEXT,
                resolution_status TEXT, confidence REAL
            );
            CREATE TABLE extracted_values (
                id TEXT PRIMARY KEY, company_id TEXT, event_id TEXT,
                value_code TEXT, value_numeric REAL, value_text TEXT, unit TEXT,
                period_type TEXT, period_start TEXT, period_end TEXT, basis TEXT,
                segment TEXT, geography TEXT, product TEXT, channel TEXT,
                project TEXT, customer_type TEXT, metric_context TEXT,
                scope_level TEXT, scope_name TEXT, fact_type TEXT,
                value_lower REAL, value_upper REAL, sentiment TEXT,
                is_explicit_guidance INTEGER, source_text TEXT,
                source_page INTEGER, confidence REAL
            );

            INSERT INTO companies VALUES ('company', 'Example Limited', 'EXAMPLE');
            INSERT INTO events VALUES (
                'event', 'company', 'FINANCIAL_RESULT', '2026-01-20',
                2025, 3, 'Nine month results'
            );
            INSERT INTO fact_observations VALUES
                ('obs-a', 'company', 'event', 'document', 'revenue_from_operations',
                 1234.5, NULL, 'crore', '2025-12-31', 'nine_months', 'consolidated',
                 7, 'Revenue from operations | 1,234.50', 0.92,
                 NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                 'numeric', 'deterministic_period_column', NULL, NULL, NULL, NULL),
                ('obs-b', 'company', 'event', 'document', 'revenue_from_operations',
                 999.0, NULL, 'crore', '2025-12-31', 'nine_months', 'consolidated',
                 12, 'Revenue from operations | 999.00', 0.90,
                 NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                 'numeric', 'llm_financial_result', NULL, NULL, NULL, NULL);
            INSERT INTO resolved_facts VALUES (
                'resolved', 'company', 'event', 'revenue_from_operations',
                1234.5, NULL, 'crore', '2025-12-31', 'nine_months', 'consolidated',
                NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                'numeric', NULL, NULL, NULL, NULL, 'obs-a', 'review_required', 0.92
            );
            """
        )

    def _seed_app(self) -> None:
        self.app.executescript(
            """
            CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, full_name TEXT);
            INSERT INTO users VALUES ('admin', 'admin@example.com', 'Admin');
            """
        )
        migrations = MICROSERVICES_DIR.parent / "backend" / "migrations"
        self.app.executescript(
            (migrations / "002_fact_review_queue.sql").read_text(encoding="utf-8")
        )
        self.app.executescript(
            (migrations / "003_review_reconciliation.sql").read_text(encoding="utf-8")
        )
        self.app.execute(
            """
            INSERT INTO fact_review_decisions (
                resolved_fact_id, company_id, event_id, fact_code, decision,
                selected_observation_id, reviewer_note, reviewed_by,
                reviewed_at, updated_at, application_status, recompute_status
            ) VALUES (
                'resolved', 'company', 'event', 'revenue_from_operations',
                'approved', 'obs-b', 'Checked page 12.', 'admin',
                '2026-07-17T10:00:00+00:00', '2026-07-17T10:00:00+00:00',
                'pending', 'not_applicable'
            )
            """
        )
        self.app.commit()

    def test_preview_is_read_only(self) -> None:
        results = preview_approved_reviews(self.analytics, self.app)
        self.assertEqual(["ready"], [result.status for result in results])
        self.assertFalse(
            self.analytics.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'fact_review_reconciliations'"
            ).fetchone()
        )
        fact = self.analytics.execute(
            "SELECT resolution_status, selected_observation_id FROM resolved_facts"
        ).fetchone()
        self.assertEqual(("review_required", "obs-a"), tuple(fact))

    def test_apply_promotes_fact_audits_and_recomputes_once(self) -> None:
        recomputed: list[str] = []

        def recompute(_conn: sqlite3.Connection, context: dict[str, object]) -> None:
            recomputed.append(str(context["id"]))

        results = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            timestamp="2026-07-17T11:00:00+00:00",
            recompute=recompute,
        )
        self.assertEqual(["applied"], [result.status for result in results])
        self.assertEqual(["succeeded"], [result.recompute_status for result in results])
        self.assertEqual(["event"], recomputed)

        fact = self.analytics.execute(
            "SELECT resolved_value, selected_observation_id, resolution_status FROM resolved_facts"
        ).fetchone()
        self.assertEqual((999.0, "obs-b", "resolved"), tuple(fact))
        value = self.analytics.execute(
            "SELECT value_numeric, period_type, basis, source_page FROM extracted_values"
        ).fetchone()
        self.assertEqual((999.0, "nine_months", "consolidated", 12), tuple(value))
        ledger = self.analytics.execute(
            "SELECT applied_by, recompute_status FROM fact_review_reconciliations"
        ).fetchone()
        self.assertEqual(("operator@example.com", "succeeded"), tuple(ledger))
        decision = self.app.execute(
            "SELECT application_status, recompute_status FROM fact_review_decisions"
        ).fetchone()
        self.assertEqual(("applied", "succeeded"), tuple(decision))

    def test_stale_candidate_is_blocked_without_analytics_write(self) -> None:
        self.analytics.execute(
            "UPDATE fact_observations SET basis = 'standalone' WHERE observation_id = 'obs-b'"
        )
        self.analytics.commit()
        results = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
        )
        self.assertEqual("invalid", results[0].status)
        self.assertIn("no longer matches", results[0].message or "")
        status = self.analytics.execute(
            "SELECT resolution_status FROM resolved_facts"
        ).fetchone()[0]
        self.assertEqual("review_required", status)
        self.assertEqual(
            "failed",
            self.app.execute(
                "SELECT application_status FROM fact_review_decisions"
            ).fetchone()[0],
        )

    def test_interrupted_app_status_is_resumable_and_idempotent(self) -> None:
        first = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            recompute=None,
        )
        self.assertEqual("applied", first[0].status)
        calls: list[str] = []

        second = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            recompute=lambda _conn, context: calls.append(str(context["id"])),
        )
        self.assertEqual("already_applied", second[0].status)
        self.assertEqual("succeeded", second[0].recompute_status)
        self.assertEqual(["event"], calls)
        self.assertEqual(
            1,
            self.analytics.execute(
                "SELECT COUNT(*) FROM fact_review_reconciliations"
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.analytics.execute("SELECT COUNT(*) FROM extracted_values").fetchone()[0],
        )
        self.assertEqual([], apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            recompute=lambda _conn, _context: self.fail("already-complete review reran"),
        ))

    def test_failed_recomputation_is_resumed_without_reapplying_fact(self) -> None:
        failed = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            recompute=lambda _conn, _context: (_ for _ in ()).throw(
                RuntimeError("metric refresh failed")
            ),
        )
        self.assertEqual("applied", failed[0].status)
        self.assertEqual("failed", failed[0].recompute_status)
        self.assertIn("metric refresh failed", failed[0].message or "")
        self.assertEqual(
            ("applied", "failed"),
            tuple(self.app.execute(
                "SELECT application_status, recompute_status FROM fact_review_decisions"
            ).fetchone()),
        )

        calls: list[str] = []
        resumed = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            recompute=lambda _conn, context: calls.append(str(context["id"])),
        )
        self.assertEqual("already_applied", resumed[0].status)
        self.assertEqual("succeeded", resumed[0].recompute_status)
        self.assertEqual(["event"], calls)
        self.assertEqual(
            1,
            self.analytics.execute(
                "SELECT COUNT(*) FROM fact_review_reconciliations"
            ).fetchone()[0],
        )

    def test_real_metrics_and_signals_recompute_entry_points_complete(self) -> None:
        company_id = hashlib.sha256(b"EXAMPLE:NSE").hexdigest()
        self.analytics.execute(
            "UPDATE companies SET id = ? WHERE id = 'company'", (company_id,)
        )
        for table in ("events", "fact_observations", "resolved_facts"):
            self.analytics.execute(
                f"UPDATE {table} SET company_id = ? WHERE company_id = 'company'",
                (company_id,),
            )
        self.app.execute(
            "UPDATE fact_review_decisions SET company_id = ?", (company_id,)
        )
        self.analytics.commit()
        self.app.commit()

        results = apply_approved_reviews(
            self.analytics,
            self.app,
            applied_by="operator@example.com",
            recompute=recompute_event,
        )
        self.assertEqual("applied", results[0].status)
        self.assertEqual("succeeded", results[0].recompute_status)
        self.assertTrue(
            self.analytics.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'metrics'"
            ).fetchone()
        )
        self.assertTrue(
            self.analytics.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'signals'"
            ).fetchone()
        )


if __name__ == "__main__":
    unittest.main()
