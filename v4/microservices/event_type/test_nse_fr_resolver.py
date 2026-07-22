from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_type_service import classify_announcement
from nse_fr_resolver import build_candidate_pool, resolve_canonical_financial_report


PRESENTATION_URL = (
    "https://nsearchives.nseindia.com/corporate/"
    "BCCL_03022026161501_Presentation_with_PPT_Signed.pdf"
)
RESULT_URL = (
    "https://nsearchives.nseindia.com/corporate/"
    "BCCL_03022026153914_Financial_Result_Q3_2025-26.pdf"
)


def _presentation() -> dict[str, str]:
    return {
        "desc": "Financial Results",
        "attchmntText": (
            "Presentation made by Company on the Un-Audited Financial Results "
            "for the 3rd Quarter ended 31st December 2025"
        ),
        "attchmntFile": PRESENTATION_URL,
        "event_bucket": "Financial Results",
        "fileSize": "4.5 MB",
    }


def _financial_result() -> dict[str, str]:
    return {
        "desc": "Financial Results",
        "attchmntText": "Un-Audited Financial Results for quarter ended 31 December 2025",
        "attchmntFile": RESULT_URL,
        "event_bucket": "Financial Results",
        "fileSize": "1.2 MB",
    }


class PresentationExclusionTests(unittest.TestCase):
    def test_bharat_coal_title_is_classified_as_investor_presentation(self) -> None:
        self.assertEqual(classify_announcement(_presentation()), "Investor Presentation")

    def test_presentation_is_excluded_from_financial_candidate_pool(self) -> None:
        pool = build_candidate_pool([_presentation(), _financial_result()])
        self.assertEqual([item["attchmntFile"] for item in pool], [RESULT_URL])

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_canonical_resolver_refuses_presentation_even_if_content_scores_one(
        self, fetch_and_classify
    ) -> None:
        financial_classification = {
            "is_financial_report": True,
            "confidence": 0.8,
            "document_kind": "FINANCIAL_RESULT",
        }
        fetch_and_classify.return_value = (
            "result-hash",
            financial_classification,
            b"%PDF-result",
        )

        resolved = resolve_canonical_financial_report(
            [_presentation(), _financial_result()],
            [_presentation(), _financial_result()],
            session=object(),
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["url"], RESULT_URL)
        fetch_and_classify.assert_called_once()
        self.assertEqual(fetch_and_classify.call_args.args[0], RESULT_URL)


if __name__ == "__main__":
    unittest.main()
