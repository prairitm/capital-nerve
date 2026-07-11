from __future__ import annotations

import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
try:
    import pydantic  # noqa: F401
except ImportError:
    HAS_PYDANTIC = False
else:
    HAS_PYDANTIC = True


def load_module(name: str, path: Path):
    module_dir = str(path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


event_type_models = (
    load_module("test_event_type_models", ROOT / "event_type" / "event_type_models.py")
    if HAS_PYDANTIC
    else None
)
values_models = (
    load_module("test_values_models", ROOT / "values" / "values_models.py")
    if HAS_PYDANTIC
    else None
)
values_db = load_module("test_values_db", ROOT / "values" / "values_db.py")
metrics_service = load_module(
    "test_metrics_service",
    ROOT / "metrics" / "metrics_service.py",
)
signals_service = load_module(
    "test_signals_service",
    ROOT / "signals" / "signals_service.py",
)


class UnifiedFlowContractsTest(unittest.TestCase):
    def test_document_request_normalization(self) -> None:
        if event_type_models is None:
            self.skipTest("pydantic is not installed")
        request = event_type_models.DocumentRequest(
            document_type="earnings transcript",
            source_mode="manual-url",
            source_url="https://example.com/transcript.txt",
        )
        self.assertEqual(request.document_type, "earnings_call_transcript")
        self.assertEqual(request.source_mode, "manual_url")

    def test_values_request_parses_resolved_documents_json(self) -> None:
        if values_models is None:
            self.skipTest("pydantic is not installed")
        request = values_models.ExtractValuesRequest(
            symbol="ITC",
            from_date="01-04-2026",
            to_date="30-06-2026",
            company_id="a" * 64,
            resolved_documents=(
                '[{"document_type":"investor_presentation",'
                '"event_type":"Investor Presentation",'
                '"event_id":"' + "b" * 64 + '",'
                '"source_url":"https://example.com/ip.pdf"}]'
            ),
        )
        self.assertEqual(len(request.resolved_documents), 1)
        self.assertEqual(request.resolved_documents[0].document_type, "investor_presentation")

    def test_schema_bootstrap_adds_unified_columns_and_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        values_db.bootstrap_schema(conn)
        extracted_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(extracted_values)").fetchall()
        }
        self.assertIn("product", extracted_cols)
        self.assertIn("scope_level", extracted_cols)
        self.assertIn("is_explicit_guidance", extracted_cols)
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("presentation_document_inventory", tables)
        self.assertIn("presentation_segments", tables)
        conn.close()

    def test_metrics_uses_presentation_catalog_for_presentations(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        company_id = metrics_service.company_id_for_symbol("ITC")
        with patch.object(metrics_service, "load_presentation_metrics_catalog", return_value={"m": {}}) as catalog, \
             patch.object(metrics_service, "load_presentation_fact_rows", return_value={}) as facts, \
             patch.object(metrics_service, "compute_presentation_metrics", return_value=[]) as compute, \
             patch.object(metrics_service, "persist_metric_values") as persist:
            result = metrics_service.compute_and_persist_metrics(
                conn,
                symbol="ITC",
                company_id=company_id,
                event_id="c" * 64,
                period_quarter=1,
                period_fy_start=2026,
                period_end="2026-06-30",
                event_type="Investor Presentation",
            )
        conn.close()
        self.assertEqual(result["metrics"], [])
        catalog.assert_called_once()
        self.assertTrue(facts.called)
        compute.assert_called_once()
        persist.assert_called_once()

    def test_signals_uses_earnings_catalog_for_transcripts(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        company_id = signals_service.company_id_for_symbol("ITC")
        with patch.object(signals_service, "load_earnings_call_signals_catalog", return_value={}) as catalog, \
             patch.object(signals_service, "load_presentation_metrics_by_key", return_value={}) as metrics, \
             patch.object(signals_service, "load_presentation_facts_by_key", return_value={}) as facts, \
             patch.object(signals_service, "evaluate_presentation_signal_rules", return_value=[]) as evaluate, \
             patch.object(signals_service, "persist_fired_signals") as persist:
            result = signals_service.evaluate_and_persist_signals(
                conn,
                symbol="ITC",
                company_id=company_id,
                event_id="d" * 64,
                period_end="2026-06-30",
                event_type="Earnings Call Transcript",
            )
        conn.close()
        self.assertEqual(result["signals"], [])
        catalog.assert_called_once()
        metrics.assert_called_once()
        facts.assert_called_once()
        evaluate.assert_called_once()
        persist.assert_called_once()


if __name__ == "__main__":
    unittest.main()
