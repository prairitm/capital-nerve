from __future__ import annotations

import ast
import importlib.util
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CATALOG_DIR = ROOT / "catalog"


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


metrics_service = load_module(
    "catalog_contract_metrics_service",
    ROOT / "metrics" / "metrics_service.py",
)
signals_service = load_module(
    "catalog_contract_signals_service",
    ROOT / "signals" / "signals_service.py",
)


FORMULA_HELPERS = {
    "abs",
    "average",
    "count",
    "count_distinct",
    "count_eq",
    "count_in",
    "count_true",
    "date_diff_days",
    "math",
    "max",
    "max_by_dimension",
    "min",
    "repeated_count",
    "sum",
    "sum_by_dimension",
    "support_rate",
    "top_share",
    "weighted_mean",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def walk_rule(rule: dict[str, Any]):
    yield rule
    for group in ("all", "any"):
        for child in rule.get(group, []):
            yield from walk_rule(child)


class CatalogContractsTest(unittest.TestCase):
    def catalog_sets(self):
        manifest = read_json(CATALOG_DIR / "manifest.json")
        base_facts = read_json(CATALOG_DIR / "facts.json")
        base_metrics = read_json(CATALOG_DIR / "metrics.json")
        for name, spec in manifest["files"].items():
            facts = read_json(CATALOG_DIR / spec["facts"])
            metrics = read_json(CATALOG_DIR / spec["metrics"])
            signals = read_json(CATALOG_DIR / spec["signals"])
            if spec.get("cross_document_fact_source") == "financial_results":
                facts = base_facts | facts
            shared_metrics = {
                key: base_metrics[key]
                for key in spec.get("shared_metrics", [])
                if key in base_metrics
            }
            yield name, (facts, shared_metrics | metrics, signals)

    def test_manifest_references_every_event_catalog(self) -> None:
        manifest = read_json(CATALOG_DIR / "manifest.json")
        self.assertEqual(manifest["catalog_version"], "0.3.0")
        self.assertTrue((CATALOG_DIR / manifest["display"]).is_file())
        for event_spec in manifest["files"].values():
            for key in ("facts", "metrics", "signals"):
                self.assertTrue((CATALOG_DIR / event_spec[key]).is_file())

    def test_display_catalog_only_references_known_entries(self) -> None:
        display = read_json(CATALOG_DIR / "display.json")
        manifest = read_json(CATALOG_DIR / "manifest.json")
        aliases = {
            "financial_results": "financial_results",
            "investor_presentation": "investor_presentation",
            "earnings_call_transcript": "earnings_call_transcript",
        }
        catalog_sets = {name: catalogs for name, catalogs in self.catalog_sets()}
        for display_key, event_name in aliases.items():
            facts, metrics, signals = catalog_sets[event_name]
            spec = display[display_key]
            with self.subTest(event=display_key):
                for fact_key in spec.get("headline_facts", []):
                    self.assertIn(fact_key, facts)
                for group in spec.get("fact_groups", []):
                    self.assertGreater(group.get("max_items", 0), 0)
                    for fact_key in group.get("fact_codes", []):
                        self.assertIn(fact_key, facts)
                for metric_key in spec.get("headline_metrics", []) + spec.get("metric_priority", []):
                    self.assertIn(metric_key, metrics)
                for signal_key in spec.get("signal_priority", []):
                    self.assertIn(signal_key, signals)
                self.assertLessEqual(spec.get("max_signals", 3), 3)

    def test_enabled_catalog_entries_have_valid_references_and_formulas(self) -> None:
        for event_name, (facts, metrics, signals) in self.catalog_sets():
            with self.subTest(event=event_name):
                for metric_key, spec in metrics.items():
                    if spec.get("enabled") is False:
                        continue
                    declared = {
                        inp["var"]
                        for inp in spec.get("inputs", [])
                        if inp.get("var")
                    }
                    for inp in spec.get("inputs", []):
                        if "fact_key" in inp:
                            self.assertIn(inp["fact_key"], facts, metric_key)
                        if "metric_key" in inp:
                            self.assertIn(inp["metric_key"], metrics, metric_key)
                            self.assertIsNot(metrics[inp["metric_key"]].get("enabled"), False, metric_key)
                    tree = ast.parse(spec["formula"], mode="eval")
                    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
                    self.assertEqual(referenced - declared - FORMULA_HELPERS, set(), metric_key)
                    self.assertEqual(declared - referenced, set(), metric_key)

                for signal_key, spec in signals.items():
                    if spec.get("enabled") is False:
                        continue
                    for leaf in walk_rule(spec.get("rule", {})):
                        self.assertTrue(
                            any(
                                key in leaf
                                for key in (
                                    "all",
                                    "any",
                                    "metric_key",
                                    "fact_key",
                                    "semantic_match",
                                )
                            ),
                            signal_key,
                        )
                        for field, catalog in (
                            ("metric_key", metrics),
                            ("compare_metric_key", metrics),
                            ("fact_key", facts),
                            ("compare_fact_key", facts),
                        ):
                            if field not in leaf:
                                continue
                            reference = leaf[field]
                            self.assertIn(reference, catalog, signal_key)
                            self.assertIsNot(catalog[reference].get("enabled"), False, signal_key)

    def test_earnings_metrics_resolve_dependencies_and_aggregations(self) -> None:
        full_catalog = read_json(CATALOG_DIR / "earnings-call" / "earnings_call_metrics.json")
        keys = {
            "revenue_guidance_midpoint",
            "revenue_guidance_revision_pct",
            "guidance_change_frequency",
            "guidance_withdrawal_count",
        }
        catalog = {key: full_catalog[key] for key in keys}

        def row(key: str, value: float | str) -> dict[str, Any]:
            return {
                "fact_key": key,
                "value": value,
                "numeric_value": value if isinstance(value, (int, float)) else None,
                "value_text": value if isinstance(value, str) else None,
                "unit": "crore" if isinstance(value, (int, float)) else "enum",
                "segment": None,
                "geography": None,
            }

        scope_pools = {
            "CURRENT_DISCLOSURE": {
                "revenue_guidance_low": [row("revenue_guidance_low", 100.0)],
                "revenue_guidance_high": [row("revenue_guidance_high", 120.0)],
            },
            "PREVIOUS_DISCLOSURE": {
                "revenue_guidance_low": [row("revenue_guidance_low", 80.0)],
                "revenue_guidance_high": [row("revenue_guidance_high", 100.0)],
            },
            "ROLLING_CALL_WINDOW": {
                "guidance_status": [
                    row("guidance_status", "RAISED"),
                    row("guidance_status", "WITHDRAWN"),
                    row("guidance_status", "MAINTAINED"),
                ]
            },
        }
        computed = metrics_service.compute_presentation_metrics(
            catalog,
            period_quarter=1,
            scope_pools=scope_pools,
        )
        by_key = {metric["metric_key"]: metric["value"] for metric in computed}
        self.assertEqual(by_key["revenue_guidance_midpoint"], 110.0)
        self.assertEqual(by_key["revenue_guidance_revision_pct"], 22.22)
        self.assertEqual(by_key["guidance_change_frequency"], 2.0)
        self.assertEqual(by_key["guidance_withdrawal_count"], 1.0)

    def test_metric_schema_persists_dimensions(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        metrics_service.bootstrap_schema(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(metrics)")}
        self.assertIn("segment", columns)
        self.assertIn("geography", columns)
        conn.close()

    def test_review_required_facts_do_not_feed_metrics_or_signals(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        metrics_service.bootstrap_schema(conn)
        conn.executemany(
            """
            INSERT INTO resolved_facts (
                resolved_fact_id, company_id, event_id, fact_code,
                resolved_value, unit, period, period_type, basis,
                resolution_status, confidence
            ) VALUES (?, 'company', 'event', ?, ?, 'crore', '2025-12-31',
                      'nine_months', ?, ?, 0.92)
            """,
            [
                ("review", "revenue_from_operations", 999.0, "consolidated", "review_required"),
                ("pat-standalone", "pat", 80.0, "standalone", "resolved"),
                ("pat-consolidated", "pat", 100.0, "consolidated", "resolved"),
            ],
        )
        metric_facts = metrics_service.load_facts(
            conn,
            company_id="company",
            event_id="event",
            period_end="2025-12-31",
        )
        signal_facts = signals_service.load_facts_by_key(
            conn,
            company_id="company",
            event_id="event",
            period_end="2025-12-31",
        )
        self.assertNotIn("revenue_from_operations", metric_facts)
        self.assertNotIn("revenue_from_operations", signal_facts)
        self.assertEqual(metric_facts["pat"]["value"], 100.0)
        self.assertEqual(signal_facts["pat"]["value"], 100.0)
        conn.close()

    def test_company_level_presentation_signal_can_fire(self) -> None:
        signal = read_json(
            CATALOG_DIR / "investor_presentation" / "presentation_signals.json"
        )["revenue_guidance_upgrade"]
        metrics = {
            key: [
                {
                    "metric_key": key,
                    "metric_id": key,
                    "value": value,
                    "segment": None,
                    "geography": None,
                }
            ]
            for key, value in {
                "revenue_guidance_revision_pct": 10.0,
            }.items()
        }
        fired = signals_service.evaluate_presentation_signal_rules(
            {"revenue_guidance_upgrade": signal},
            metrics_by_key=metrics,
            facts_by_key={},
        )
        self.assertEqual(
            [item["signal_key"] for item in fired],
            ["revenue_guidance_upgrade"],
        )

    def test_earnings_semantic_signal_matches_extracted_text(self) -> None:
        signal = read_json(
            CATALOG_DIR / "earnings-call" / "earnings_call_signals.json"
        )["working_capital_concern"]
        facts = {
            "utterance_text": [
                {
                    "fact_key": "utterance_text",
                    "value": "Receivable delays caused a stretch in working capital.",
                    "segment": None,
                    "geography": None,
                }
            ]
        }
        fired = signals_service.evaluate_presentation_signal_rules(
            {"working_capital_concern": signal},
            metrics_by_key={},
            facts_by_key=facts,
        )
        self.assertEqual(
            [item["signal_key"] for item in fired],
            ["working_capital_concern"],
        )


if __name__ == "__main__":
    unittest.main()
