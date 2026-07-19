from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from replay_deterministic import replay


class DeterministicReplayTest(unittest.TestCase):
    def test_missing_parsed_document_becomes_explicit_abstention(self) -> None:
        gold = [
            {
                "label_id": "doc:pat:2025-03-31:consolidated:year",
                "document_id": "doc",
                "company_symbol": "TEST",
                "fact_code": "pat",
                "period_end": "2025-03-31",
                "period_type": "year",
                "basis": "consolidated",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            predictions = replay(gold, parsed_dir=Path(directory))
        self.assertEqual(1, len(predictions))
        self.assertEqual("abstain", predictions[0]["decision"])
        self.assertEqual(
            "missing_parsed_document", predictions[0]["extraction_method"]
        )
        self.assertEqual(0.0, predictions[0]["confidence"])


if __name__ == "__main__":
    unittest.main()
