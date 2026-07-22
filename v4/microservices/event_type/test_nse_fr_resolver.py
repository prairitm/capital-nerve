from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_type_service import _resolve_exact_nse_document, classify_announcement
from nse_fr_resolver import (
    build_candidate_pool,
    classify_pdf_content,
    download_pdf,
    infer_period_markers,
    metadata_score,
    resolve_canonical_financial_report,
)


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


class DownloadRegressionTests(unittest.TestCase):
    @patch("nse_fr_resolver.time.sleep")
    def test_pdf_download_retries_transient_request_errors(self, sleep) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = b"%PDF-result"
        session = Mock()
        session.get.side_effect = [
            requests.ConnectionError("temporary failure"),
            response,
        ]

        self.assertEqual(
            download_pdf("https://example.test/result.pdf", session),
            b"%PDF-result",
        )
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once()


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


class SelectionRegressionTests(unittest.TestCase):
    @staticmethod
    def _result(
        url: str,
        sort_date: str,
        *,
        text: str = "Financial Results",
        file_size: str = "1 MB",
    ) -> dict[str, str]:
        return {
            "desc": "Financial Results",
            "attchmntText": text,
            "attchmntFile": url,
            "event_bucket": "Financial Results",
            "sort_date": sort_date,
            "fileSize": file_size,
        }

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_newest_valid_result_wins_over_older_metadata_score(
        self, fetch_and_classify
    ) -> None:
        newer = self._result(
            "https://example.test/newer.pdf",
            "2026-07-11 10:00:00",
            file_size="400 KB",
        )
        older = self._result(
            "https://example.test/older_outcome_financialresults.pdf",
            "2026-04-11 10:00:00",
            text="Submitted to the Exchange, the financial results",
            file_size="3 MB",
        )

        def classify(url, _session, **_kwargs):
            confidence = 1.0 if url == newer["attchmntFile"] else 0.9
            return (
                url,
                {
                    "is_financial_report": True,
                    "confidence": confidence,
                    "document_kind": "FINANCIAL_RESULT",
                },
                b"%PDF-result",
            )

        fetch_and_classify.side_effect = classify
        self.assertGreater(metadata_score(older), metadata_score(newer))

        resolved = resolve_canonical_financial_report(
            [newer, older], [newer, older], session=object()
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["url"], newer["attchmntFile"])

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_explicit_result_wins_over_later_same_day_press_release(
        self, fetch_and_classify
    ) -> None:
        press_release = self._result(
            "https://example.test/press-release.pdf",
            "2024-07-16 12:53:12",
            text="Press release on unaudited financial results for the quarter ended June 30, 2024",
        )
        press_release["desc"] = "Press Release"
        explicit_result = self._result(
            "https://example.test/result.pdf",
            "2024-07-16 12:46:22",
            text=(
                "Submitted to the Exchange, the financial results for the period "
                "ended June 30, 2024"
            ),
        )
        explicit_result["desc"] = "Financial Result Updates"
        fetch_and_classify.return_value = (
            "result-hash",
            {
                "is_financial_report": True,
                "confidence": 0.9,
                "document_kind": "FINANCIAL_RESULT",
            },
            b"%PDF-result",
        )

        resolved = resolve_canonical_financial_report(
            [press_release, explicit_result],
            [press_release, explicit_result],
            session=object(),
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["url"], explicit_result["attchmntFile"])

    def test_period_markers_support_ordinals_and_ignore_upload_dates(self) -> None:
        markers = infer_period_markers(
            [
                self._result(
                    "https://example.test/Boardoutcome_07052024.pdf",
                    "2024-05-07 20:08:53",
                    text="Financial results for the quarter ended 31st March 2024",
                )
            ]
        )

        self.assertIn("31 march 2024", markers)
        self.assertIn("31032024", markers)
        self.assertNotIn("07052024", markers)

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_strict_period_match_normalizes_nse_date_punctuation(
        self, fetch_and_classify
    ) -> None:
        result = self._result(
            "https://example.test/signedBSENSE_10022025205304.pdf",
            "2025-02-10 20:53:04",
            text=(
                "Submitted to the Exchange, the financial results for the period "
                "ended December 31, 2024."
            ),
        )
        fetch_and_classify.return_value = (
            "result-hash",
            {
                "is_financial_report": True,
                "confidence": 0.9,
                "document_kind": "FINANCIAL_RESULT",
            },
            b"%PDF-result",
        )

        resolved = resolve_canonical_financial_report(
            [result],
            [result],
            period_markers=infer_period_markers([result]),
            strict_period_match=True,
            session=object(),
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["url"], result["attchmntFile"])

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_strict_target_period_does_not_fall_back_to_older_period(
        self, fetch_and_classify
    ) -> None:
        target = self._result(
            "https://example.test/target_financialresult.pdf",
            "2026-07-11 10:00:00",
            text="Financial results for the quarter ended 30 June 2026",
        )
        older = self._result(
            "https://example.test/older_financialresult.pdf",
            "2026-04-11 10:00:00",
            text="Financial results for the quarter ended 31 March 2026",
        )

        def classify(url, _session, **_kwargs):
            valid = url == older["attchmntFile"]
            return (
                url,
                {
                    "is_financial_report": valid,
                    "confidence": 0.9 if valid else 0.0,
                    "document_kind": "FINANCIAL_RESULT" if valid else "OTHER",
                },
                b"%PDF-result",
            )

        fetch_and_classify.side_effect = classify
        resolved = resolve_canonical_financial_report(
            [target, older],
            [target, older],
            period_markers=["30 june 2026"],
            strict_period_match=True,
            session=object(),
        )

        self.assertIsNone(resolved)
        attempted_urls = [call.args[0] for call in fetch_and_classify.call_args_list]
        self.assertEqual(attempted_urls, [target["attchmntFile"]])

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_transport_failure_is_not_reported_as_invalid_pdf(
        self, fetch_and_classify
    ) -> None:
        result = self._result(
            "https://example.test/result.pdf",
            "2025-02-10 20:53:04",
            text=(
                "Submitted to the Exchange, the financial results for the period "
                "ended December 31, 2024"
            ),
        )
        fetch_and_classify.side_effect = requests.ConnectionError("archive unavailable")

        with self.assertRaises(requests.ConnectionError):
            resolve_canonical_financial_report([result], [result], session=object())

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_exact_result_does_not_recover_from_another_day(
        self, fetch_and_classify
    ) -> None:
        exact = self._result(
            "https://example.test/exact_financialresult.pdf",
            "2026-07-10 10:00:00",
        )
        alternate = self._result(
            "https://example.test/alternate_financialresult.pdf",
            "2026-07-11 10:00:00",
        )

        def classify(url, _session, **_kwargs):
            valid = url == alternate["attchmntFile"]
            return (
                url,
                {
                    "is_financial_report": valid,
                    "confidence": 0.9 if valid else 0.0,
                    "document_kind": "FINANCIAL_RESULT" if valid else "OTHER",
                },
                b"%PDF-result",
            )

        fetch_and_classify.side_effect = classify

        with self.assertRaises(LookupError):
            _resolve_exact_nse_document(
                session=object(),
                announcements=[exact, alternate],
                document_type="financial_result",
                source_url=exact["attchmntFile"],
            )
        fetch_and_classify.assert_called_once()
        self.assertEqual(fetch_and_classify.call_args.args[0], exact["attchmntFile"])

    @patch("nse_fr_resolver._fetch_and_classify")
    def test_exact_result_can_recover_same_day_same_period_companion(
        self, fetch_and_classify
    ) -> None:
        exact = self._result(
            "https://example.test/exact_letter.pdf",
            "2026-07-10 10:00:00",
            text="Financial results for the quarter ended 30 June 2026",
        )
        companion = self._result(
            "https://example.test/companion_financialresult.pdf",
            "2026-07-10 10:05:00",
            text="Unaudited financial results for quarter ended 30 June 2026",
        )
        unrelated = self._result(
            "https://example.test/unrelated_financialresult.pdf",
            "2026-07-11 10:00:00",
            text="Unaudited financial results for quarter ended 30 June 2026",
        )

        def classify(url, _session, **_kwargs):
            valid = url != exact["attchmntFile"]
            return (
                url,
                {
                    "is_financial_report": valid,
                    "confidence": 0.9 if valid else 0.0,
                    "document_kind": "FINANCIAL_RESULT" if valid else "OTHER",
                },
                b"%PDF-result",
            )

        fetch_and_classify.side_effect = classify
        resolved = _resolve_exact_nse_document(
            session=object(),
            announcements=[exact, companion, unrelated],
            document_type="financial_result",
            source_url=exact["attchmntFile"],
        )

        self.assertEqual(resolved["source_url"], companion["attchmntFile"])
        attempted_urls = [call.args[0] for call in fetch_and_classify.call_args_list]
        self.assertNotIn(unrelated["attchmntFile"], attempted_urls)


class ContentClassificationRegressionTests(unittest.TestCase):
    @patch("nse_fr_resolver._extract_pdf_text")
    def test_credit_rating_mention_does_not_veto_financial_statement(
        self, extract_pdf_text
    ) -> None:
        table_rows = "\n".join(
            f"Revenue line {index} 1,200 1,100" for index in range(10)
        )
        extract_pdf_text.return_value = (
            "Statement of Profit and Loss\n"
            "Revenue from operations\n"
            "The company retains its existing credit rating.\n"
            f"{table_rows}",
            20,
        )

        classification = classify_pdf_content(b"%PDF-result")

        self.assertTrue(classification["is_financial_report"])
        self.assertEqual(classification["signals"]["soft_excluded_hits"], 1)

    @patch("nse_fr_resolver._extract_pdf_text")
    def test_monitoring_agency_report_remains_hard_excluded(
        self, extract_pdf_text
    ) -> None:
        extract_pdf_text.return_value = (
            "Monitoring Agency Report\nRevenue from operations 1,200 1,100",
            20,
        )

        classification = classify_pdf_content(b"%PDF-result")

        self.assertFalse(classification["is_financial_report"])
        self.assertEqual(classification["document_kind"], "EXCLUDED")


if __name__ == "__main__":
    unittest.main()
