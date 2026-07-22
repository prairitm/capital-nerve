import unittest

from routers.documents import build_filing_summary


def fact(code: str, value: float | None, *, confidence: float = 0.9) -> dict:
    return {
        "value_code": code,
        "value_name": code.replace("_", " ").title(),
        "value_numeric": value,
        "value_text": None,
        "value_lower": None,
        "value_upper": None,
        "confidence": confidence,
        "source_page": 1,
    }


class FilingSummaryTest(unittest.TestCase):
    def test_selects_material_facts_without_removing_fact_count(self):
        facts = [
            fact("employee_count", 1000, confidence=1.0),
            fact("pat", 40),
            fact("pat_attributable_to_parent", 40, confidence=1.0),
            fact("revenue_from_operations", 500),
            fact("ebitda", 80),
            fact("net_debt", 25),
            fact("capex", 15),
        ]

        summary = build_filing_summary(facts)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(7, summary["available_fact_count"])
        self.assertEqual(
            ["revenue_from_operations", "pat", "ebitda", "net_debt"],
            [row["value_code"] for row in summary["highlights"]],
        )

    def test_returns_none_when_no_facts_have_values(self):
        self.assertIsNone(
            build_filing_summary(
                [
                    {
                        "value_code": "pat",
                        "value_numeric": None,
                        "value_text": None,
                        "value_lower": None,
                        "value_upper": None,
                    }
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
