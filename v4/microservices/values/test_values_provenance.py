from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from values_db import bootstrap_schema
from values_service import (
    canonicalize_facts,
    is_multi_issuer_newspaper,
    persist_extracted_values,
)


class ValuesProvenanceTest(unittest.TestCase):
    def test_upstream_statement_conflict_remains_review_required(self) -> None:
        rows = canonicalize_facts(
            [
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": 1000.0,
                    "unit": "crore",
                    "basis": "consolidated",
                    "evidence": "Revenue from operations 1,000.00",
                    "source_page": 3,
                    "period_end": "2025-06-30",
                    "period_type": "quarter",
                    "extraction_method": "deterministic_quarter_column",
                    "confidence": 0.92,
                    "decision": "review",
                    "has_unresolved_conflict": True,
                    "conflict_reason": "material_cross_page_statement_disagreement",
                }
            ],
            facts_catalog={
                "revenue_from_operations": {"name": "Revenue", "unit": "crore"}
            },
            storage_to_fact={"revenue_from_operations": "revenue_from_operations"},
        )
        self.assertEqual(rows[0]["decision"], "review")
        self.assertTrue(rows[0]["has_unresolved_conflict"])
        self.assertEqual(
            rows[0]["conflict_reason"],
            "material_cross_page_statement_disagreement",
        )

    def test_multi_issuer_newspaper_is_withheld(self) -> None:
        markdown = """
Financial Express newspaper publication
# Sun Pharmaceutical Industries Limited
Scan the QR code for Sun Pharma's financial results.
# Neuland Laboratories Limited
## Unaudited Financial Results
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Total income | 30,060.86 |
"""
        self.assertTrue(is_multi_issuer_newspaper(markdown))

    def test_normal_filing_is_not_treated_as_multi_issuer_newspaper(self) -> None:
        markdown = """
# Example Industries Limited
Statement of Unaudited Consolidated Financial Results
National Stock Exchange of India Limited
| Particulars | Quarter ended 30.06.2025 |
| --- | --- |
| Revenue from operations | 1,234.50 |
"""
        self.assertFalse(is_multi_issuer_newspaper(markdown))

    def test_canonicalization_preserves_provenance(self) -> None:
        rows = canonicalize_facts(
            [
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": "1,234.50",
                    "unit": "crore",
                    "basis": "consolidated",
                    "period_end": "2025-06-30",
                    "source_page": 7,
                    "evidence": "Revenue from operations | 1,234.50",
                    "extraction_method": "deterministic_quarter_column",
                    "confidence": 0.92,
                }
            ],
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
            storage_to_fact={"revenue_from_operations": "revenue_from_operations"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_page"], 7)
        self.assertEqual(rows[0]["period_end"], "2025-06-30")
        self.assertEqual(
            rows[0]["extraction_method"], "deterministic_quarter_column"
        )

    def test_equal_confidence_disagreement_routes_to_review(self) -> None:
        rows = canonicalize_facts(
            [
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": 1234.5,
                    "unit": "crore",
                    "basis": "consolidated",
                    "period_end": "2025-06-30",
                    "source_page": 7,
                    "evidence": "Revenue from operations | 1,234.50",
                    "confidence": 0.92,
                },
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": 999.0,
                    "unit": "crore",
                    "basis": "consolidated",
                    "period_end": "2025-06-30",
                    "source_page": 12,
                    "evidence": "Revenue from operations | 999.00",
                    "confidence": 0.90,
                },
            ],
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
            storage_to_fact={"revenue_from_operations": "revenue_from_operations"},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "review")
        self.assertTrue(rows[0]["has_unresolved_conflict"])
        self.assertEqual(rows[0]["conflict_values"], [999.0, 1234.5])
        self.assertEqual(rows[0]["conflict_source_pages"], [7, 12])

    def test_clear_confidence_winner_remains_publishable(self) -> None:
        rows = canonicalize_facts(
            [
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": 1234.5,
                    "basis": "consolidated",
                    "period_end": "2025-06-30",
                    "source_page": 7,
                    "evidence": "Revenue from operations | 1,234.50",
                    "confidence": 0.92,
                },
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": 999.0,
                    "basis": "consolidated",
                    "period_end": "2025-06-30",
                    "source_page": 12,
                    "evidence": "Revenue from operations | 999.00",
                    "confidence": 0.70,
                },
            ],
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
            storage_to_fact={"revenue_from_operations": "revenue_from_operations"},
        )
        self.assertEqual(rows[0]["numeric_value"], 1234.5)
        self.assertEqual(rows[0]["decision"], "publish")
        self.assertFalse(rows[0]["has_unresolved_conflict"])

    def test_incomplete_evidence_routes_to_review(self) -> None:
        catalog = {
            "revenue_from_operations": {
                "name": "Revenue From Operations",
                "unit": "crore",
            }
        }
        aliases = {"revenue_from_operations": "revenue_from_operations"}
        cases = (
            ({"evidence": "Revenue from operations | 1,234.50"}, "missing page"),
            ({"source_page": 7}, "missing source text"),
        )
        for source_fields, label in cases:
            with self.subTest(label=label):
                rows = canonicalize_facts(
                    [
                        {
                            "fact_key": "revenue_from_operations",
                            "numeric_value": 1234.5,
                            "basis": "consolidated",
                            "period_end": "2025-06-30",
                            "confidence": 0.92,
                            **source_fields,
                        }
                    ],
                    facts_catalog=catalog,
                    storage_to_fact=aliases,
                )
                self.assertEqual(rows[0]["decision"], "review")
                self.assertEqual(rows[0]["evidence_status"], "incomplete")

    def test_missing_evidence_abstains(self) -> None:
        rows = canonicalize_facts(
            [
                {
                    "fact_key": "revenue_from_operations",
                    "numeric_value": 1234.5,
                    "basis": "consolidated",
                    "period_end": "2025-06-30",
                    "confidence": 0.92,
                }
            ],
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
            storage_to_fact={"revenue_from_operations": "revenue_from_operations"},
        )
        self.assertEqual(rows[0]["decision"], "abstain")
        self.assertEqual(rows[0]["evidence_status"], "missing")

    def test_persistence_keeps_page_on_value_and_observation(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        bootstrap_schema(connection)
        connection.execute(
            "INSERT INTO companies (id, name, ticker) VALUES ('company', 'Test', 'TEST')"
        )
        connection.execute(
            """INSERT INTO events (id, company_id, event_type, event_date)
               VALUES ('event', 'company', 'Financial Results', '2025-07-01')"""
        )
        connection.execute(
            """INSERT INTO documents (id, company_id, storage_path, sha256)
               VALUES ('document', 'company', '/tmp/test.pdf', 'sha')"""
        )
        rows = [
            {
                "fact_key": "revenue_from_operations",
                "numeric_value": 1234.5,
                "unit": "crore",
                "basis": "consolidated",
                "period_end": "2025-06-30",
                "source_page": 7,
                "evidence": "Revenue from operations | 1,234.50",
                "source_text": "Revenue from operations | 1,234.50",
                "extraction_method": "deterministic_quarter_column",
                "confidence": 0.92,
            }
        ]
        persist_extracted_values(
            connection,
            company_id="company",
            event_id="event",
            document_id="document",
            period_quarter=1,
            period_fy_start=2025,
            period_end="2025-06-30",
            rows=rows,
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
        )
        value = connection.execute(
            "SELECT source_page FROM extracted_values"
        ).fetchone()
        observation = connection.execute(
            "SELECT source_page, extraction_method FROM fact_observations"
        ).fetchone()
        self.assertEqual(value["source_page"], 7)
        self.assertEqual(observation["source_page"], 7)
        self.assertEqual(
            observation["extraction_method"], "deterministic_quarter_column"
        )
        connection.close()

    def test_resolution_identity_keeps_statement_bases_separate(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        bootstrap_schema(connection)
        connection.execute(
            "INSERT INTO companies (id, name, ticker) VALUES ('company', 'Test', 'TEST')"
        )
        connection.execute(
            """INSERT INTO events (id, company_id, event_type, event_date)
               VALUES ('event', 'company', 'Financial Results', '2026-01-20')"""
        )
        connection.execute(
            """INSERT INTO documents (id, company_id, storage_path, sha256)
               VALUES ('document', 'company', '/tmp/test.pdf', 'sha')"""
        )
        rows = [
            {
                "fact_key": "revenue_from_operations",
                "numeric_value": value,
                "unit": "crore",
                "basis": basis,
                "period_end": "2025-12-31",
                "period_type": "nine_months",
                "source_page": page,
                "source_text": f"Revenue from operations | {value}",
                "confidence": 0.92,
                "decision": "publish",
            }
            for basis, value, page in (
                ("consolidated", 1500.0, 6),
                ("standalone", 1200.0, 12),
            )
        ]
        persist_extracted_values(
            connection,
            company_id="company",
            event_id="event",
            document_id="document",
            period_quarter=3,
            period_fy_start=2025,
            period_end="2025-12-31",
            rows=rows,
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
        )
        resolutions = connection.execute(
            "SELECT basis, period, period_type FROM resolved_facts ORDER BY basis"
        ).fetchall()
        observations = connection.execute(
            "SELECT basis, period_type FROM fact_observations ORDER BY basis"
        ).fetchall()
        self.assertEqual(
            [(row["basis"], row["period"], row["period_type"]) for row in resolutions],
            [
                ("consolidated", "2025-12-31", "nine_months"),
                ("standalone", "2025-12-31", "nine_months"),
            ],
        )
        self.assertEqual(
            [(row["basis"], row["period_type"]) for row in observations],
            [("consolidated", "nine_months"), ("standalone", "nine_months")],
        )
        connection.close()

    def test_unresolved_conflict_is_not_auto_published(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        bootstrap_schema(connection)
        connection.execute(
            "INSERT INTO companies (id, name, ticker) VALUES ('company', 'Test', 'TEST')"
        )
        connection.execute(
            """INSERT INTO events (id, company_id, event_type, event_date)
               VALUES ('event', 'company', 'Financial Results', '2025-07-01')"""
        )
        connection.execute(
            """INSERT INTO documents (id, company_id, storage_path, sha256)
               VALUES ('document', 'company', '/tmp/test.pdf', 'sha')"""
        )
        rows = [
            {
                "fact_key": "revenue_from_operations",
                "numeric_value": 1234.5,
                "unit": "crore",
                "basis": "consolidated",
                "period_end": "2025-06-30",
                "source_page": 7,
                "source_text": "Conflicting revenue observations",
                "extraction_method": "deterministic_period_column",
                "confidence": 0.92,
                "decision": "review",
                "has_unresolved_conflict": True,
            }
        ]
        persist_extracted_values(
            connection,
            company_id="company",
            event_id="event",
            document_id="document",
            period_quarter=1,
            period_fy_start=2025,
            period_end="2025-06-30",
            rows=rows,
            facts_catalog={
                "revenue_from_operations": {
                    "name": "Revenue From Operations",
                    "unit": "crore",
                }
            },
        )
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM extracted_values").fetchone()[0],
            0,
        )
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM fact_observations").fetchone()[0],
            1,
        )
        resolution = connection.execute(
            "SELECT resolution_status FROM resolved_facts"
        ).fetchone()
        self.assertEqual(resolution["resolution_status"], "review_required")
        connection.close()


if __name__ == "__main__":
    unittest.main()
