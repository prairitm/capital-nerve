import unittest

from catalog import document_display_config, select_display_signals


class DisplayCatalogTest(unittest.TestCase):
    def test_financial_headlines_replace_pbt_with_margin(self):
        config = document_display_config("Financial Results")
        self.assertNotIn("pbt", config["headline_facts"])
        self.assertIn("ebitda_margin", config["headline_metrics"])
        self.assertLessEqual(config["max_signals"], 3)

    def test_call_does_not_surface_financial_statement_signals(self):
        signals = [
            {"signal_type": "balance_sheet_reconciliation_issue"},
            {"signal_type": "guidance_withdrawn"},
            {"signal_type": "evasive_q_and_a"},
        ]
        selected = select_display_signals(signals, "Earnings Call Transcript")
        self.assertEqual(
            [signal["signal_type"] for signal in selected],
            ["guidance_withdrawn", "evasive_q_and_a"],
        )

    def test_primary_signals_are_deduplicated_by_insight_group(self):
        signals = [
            {"signal_type": "revenue_guidance_cut"},
            {"signal_type": "margin_guidance_cut"},
            {"signal_type": "project_delay"},
            {"signal_type": "market_share_loss"},
        ]
        selected = select_display_signals(signals, "Investor Presentation")
        self.assertEqual(
            [signal["signal_type"] for signal in selected],
            ["revenue_guidance_cut", "project_delay", "market_share_loss"],
        )


if __name__ == "__main__":
    unittest.main()
