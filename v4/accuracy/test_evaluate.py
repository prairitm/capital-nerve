import copy
import unittest

from evaluate import EvaluationInputError, evaluate


def gold(**overrides):
    record = {
        "label_id": "doc-1:revenue:q1:consolidated",
        "document_id": "doc-1",
        "company_symbol": "TEST",
        "fact_code": "revenue_from_operations",
        "value_numeric": 123.45,
        "value_text": None,
        "unit": "crore",
        "period_end": "2026-06-30",
        "period_type": "quarter",
        "basis": "consolidated",
        "source_page": 3,
        "source_text": "Revenue from operations | 123.45",
        "segment": None,
        "geography": None,
        "label_status": "approved",
    }
    record.update(overrides)
    return record


def prediction(**overrides):
    record = {
        "label_id": "doc-1:revenue:q1:consolidated",
        "decision": "publish",
        "document_id": "doc-1",
        "company_symbol": "TEST",
        "fact_code": "revenue_from_operations",
        "value_numeric": 123.45,
        "value_text": None,
        "unit": "crore",
        "period_end": "2026-06-30",
        "period_type": "quarter",
        "basis": "consolidated",
        "source_page": 3,
        "source_text": "Revenue from operations | 123.45",
        "segment": None,
        "geography": None,
        "has_unresolved_conflict": False,
    }
    record.update(overrides)
    return record


class EvaluateTest(unittest.TestCase):
    def test_correct_published_fact_passes_gates(self):
        report = evaluate([gold()], [prediction()])
        self.assertEqual(report["metrics"]["auto_published_precision"], 1.0)
        self.assertEqual(report["metrics"]["auto_published_coverage"], 1.0)
        self.assertTrue(report["release_gates"]["passed"])

    def test_wrong_value_fails_precision(self):
        report = evaluate([gold()], [prediction(value_numeric=999.0, source_text="999")])
        self.assertEqual(report["metrics"]["auto_published_precision"], 0.0)
        self.assertEqual(report["errors"]["wrong_value"], 1)
        self.assertFalse(report["release_gates"]["passed"])

    def test_wrong_period_basis_unit_and_page_are_counted(self):
        report = evaluate(
            [gold()],
            [
                prediction(
                    period_end="2025-06-30",
                    basis="standalone",
                    unit="million",
                    source_page=4,
                )
            ],
        )
        self.assertEqual(report["errors"]["wrong_period_end"], 1)
        self.assertEqual(report["errors"]["wrong_basis"], 1)
        self.assertEqual(report["errors"]["wrong_unit"], 1)
        self.assertEqual(report["errors"]["wrong_source_page"], 1)

    def test_review_preserves_precision_and_reduces_coverage(self):
        report = evaluate([gold()], [prediction(decision="review")])
        self.assertIsNone(report["metrics"]["auto_published_precision"])
        self.assertEqual(report["metrics"]["auto_published_coverage"], 0.0)
        self.assertEqual(report["metrics"]["review_rate"], 1.0)
        self.assertFalse(report["release_gates"]["passed"])

    def test_missing_prediction_counts_as_abstention(self):
        report = evaluate([gold()], [])
        self.assertEqual(report["counts"]["missing"], 1)
        self.assertEqual(report["metrics"]["abstention_rate"], 1.0)

    def test_draft_gold_is_ignored(self):
        report = evaluate([gold(label_status="draft")], [prediction()])
        self.assertEqual(report["approved_gold_records"], 0)
        self.assertEqual(report["ignored_unapproved_gold_records"], 1)

    def test_draft_gold_can_be_scored_but_never_released(self):
        report = evaluate(
            [gold(label_status="draft")], [prediction()], include_draft=True
        )
        self.assertEqual(report["metrics"]["auto_published_precision"], 1.0)
        self.assertTrue(report["provisional"])
        self.assertFalse(report["release_gates"]["approved_gold_only"])
        self.assertFalse(report["release_gates"]["passed"])

    def test_accounting_negative_is_supported_by_evidence(self):
        expected = gold(value_numeric=-19.19, source_text="Finance cost | (19.19)")
        actual = prediction(value_numeric=-19.19, source_text="Finance cost | (19.19)")
        report = evaluate([expected], [actual])
        self.assertTrue(report["release_gates"]["passed"])

    def test_unresolved_conflict_cannot_pass(self):
        report = evaluate([gold()], [prediction(has_unresolved_conflict=True)])
        self.assertEqual(report["errors"]["unresolved_conflict"], 1)
        self.assertFalse(report["release_gates"]["passed"])

    def test_spurious_published_fact_reduces_precision(self):
        extra = copy.deepcopy(prediction(label_id="unknown-label"))
        report = evaluate([gold()], [prediction(), extra])
        self.assertEqual(report["metrics"]["auto_published_precision"], 0.5)
        self.assertEqual(report["counts"]["spurious_published"], 1)

    def test_duplicate_prediction_ids_are_rejected(self):
        with self.assertRaises(EvaluationInputError):
            evaluate([gold()], [prediction(), prediction()])


if __name__ == "__main__":
    unittest.main()
