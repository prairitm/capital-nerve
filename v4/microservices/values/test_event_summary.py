from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from values_config import settings
from values_db import bootstrap_schema
from values_service import generate_event_summary_for_event


class EventSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original_parsed_dir = settings.parsed_dir
        settings.parsed_dir = Path(self.temp.name)
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        bootstrap_schema(self.conn)
        self.conn.execute(
            "INSERT INTO companies (id, name, ticker) VALUES ('company', 'Example Ltd', 'EXAMPLE')"
        )
        self.conn.execute(
            """
            INSERT INTO events (
                id, company_id, event_type, event_date, title, document_id
            ) VALUES (
                'event', 'company', 'Financial Results', '2026-07-22',
                'Q1 financial results', 'document'
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO documents (
                id, company_id, storage_path, sha256, title, document_kind
            ) VALUES (
                'document', 'company', '/tmp/example.pdf', 'sha',
                'Q1 financial results', 'FINANCIAL_RESULT'
            )
            """
        )
        (settings.parsed_dir / "document.md").write_text(
            "# Page 1\nRevenue increased 20% to INR 500 crore. PAT was INR 40 crore.",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.conn.close()
        settings.parsed_dir = self.original_parsed_dir
        self.temp.cleanup()

    def test_generates_strict_structured_summary_once_then_uses_cache(self) -> None:
        client = MagicMock()
        client.responses.create.return_value = SimpleNamespace(
            output_text=(
                '{"headline":"Revenue growth anchors a stronger quarter",'
                '"summary":"Revenue rose 20% to INR 500 crore while PAT reached INR 40 crore. '
                'The filing points to improved operating momentum.",'
                '"key_points":["Revenue increased 20%.","Revenue reached INR 500 crore.",'
                '"PAT was INR 40 crore."],'
                '"investor_takeaway":"Growth and profitability improved together during the quarter."}'
            )
        )

        first = generate_event_summary_for_event(
            self.conn,
            client=client,
            model="gpt-5-nano",
            event_id="event",
        )
        second = generate_event_summary_for_event(
            self.conn,
            client=client,
            model="gpt-5-nano",
            event_id="event",
        )

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(1, client.responses.create.call_count)
        response_format = client.responses.create.call_args.kwargs["text"]["format"]
        self.assertEqual("json_schema", response_format["type"])
        self.assertTrue(response_format["strict"])
        self.assertEqual(3, len(first["key_points"]))


if __name__ == "__main__":
    unittest.main()
