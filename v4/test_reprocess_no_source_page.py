from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from reprocess_no_source_page import (
    find_affected_documents,
    local_document_path,
    remaining_missing_facts,
)


class ReprocessNoSourcePageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "analytics.db"
        self.pdf_path = Path(self.temp.name) / "filing.pdf"
        self.pdf_path.write_bytes(b"%PDF-test")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            f"""
            CREATE TABLE companies (id TEXT PRIMARY KEY, ticker TEXT);
            CREATE TABLE events (
                id TEXT PRIMARY KEY, company_id TEXT, event_type TEXT,
                event_date TEXT, source_url TEXT, document_id TEXT
            );
            CREATE TABLE documents (
                id TEXT PRIMARY KEY, document_kind TEXT, source_url TEXT,
                storage_path TEXT
            );
            CREATE TABLE fact_observations (
                observation_id TEXT PRIMARY KEY, document_id TEXT, source_page INTEGER
            );
            CREATE TABLE resolved_facts (
                resolved_fact_id TEXT PRIMARY KEY, event_id TEXT, fact_code TEXT,
                selected_observation_id TEXT, resolution_status TEXT
            );
            INSERT INTO companies VALUES ('company', 'TEST');
            INSERT INTO events VALUES (
                'event', 'company', 'Financial Results', '2026-07-22',
                'https://example.test/filing.pdf', 'document'
            );
            INSERT INTO documents VALUES (
                'document', 'FINANCIAL_RESULT', NULL, '{self.pdf_path}'
            );
            INSERT INTO fact_observations VALUES ('missing', 'document', NULL);
            INSERT INTO fact_observations VALUES ('complete', 'document', 7);
            INSERT INTO resolved_facts VALUES (
                'review', 'event', 'pat', 'missing', 'review_required'
            );
            INSERT INTO resolved_facts VALUES (
                'resolved', 'event', 'revenue', 'complete', 'resolved'
            );
            """
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp.cleanup()

    def test_finds_only_selected_review_facts_without_pages(self) -> None:
        documents = find_affected_documents(self.conn)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].document_id, "document")
        self.assertEqual(documents[0].missing_facts, 1)
        self.assertEqual(documents[0].fact_codes, "pat")
        self.assertEqual(remaining_missing_facts(self.conn, "document"), 1)

    def test_resolves_existing_document_storage_path(self) -> None:
        document = find_affected_documents(self.conn)[0]
        self.assertEqual(local_document_path(document, self.db_path), self.pdf_path.resolve())


if __name__ == "__main__":
    unittest.main()
