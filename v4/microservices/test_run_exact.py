from __future__ import annotations

import argparse
import json
import unittest
from unittest.mock import Mock, patch

import run


class ExactDocumentRunnerTest(unittest.TestCase):
    def test_starts_at_resolution_and_pins_discovered_source(self) -> None:
        event_id = "c" * 64
        document_id = "d" * 64
        source_url = "https://example.com/exact.pdf"
        args = argparse.Namespace(
            symbol="EXAMPLE",
            from_date="17-07-2026",
            to_date="18-07-2026",
            event_type="Investor Presentation",
            skip_health=True,
            timeout=30.0,
            poll_interval=0.01,
            values_sync=False,
            values_parse_workers=None,
            values_extraction_workers=None,
            detail_limit=1,
            **{f"{name}_url": url for name, url in run.DEFAULT_SERVICES.items()},
        )
        step3 = {
            "event_id": event_id,
            "chosen_source_url": source_url,
            "resolved_documents": [{
                "document_type": "investor_presentation",
                "event_type": "Investor Presentation",
                "source_mode": "nse_exact",
                "event_id": event_id,
                "source_url": source_url,
            }],
            "next_service_params": {
                "symbol": "EXAMPLE", "from_date": args.from_date, "to_date": args.to_date,
                "company_id": "b" * 64, "event_id": event_id,
                "pdf_url": source_url,
            },
        }
        values = {
            "document_id": document_id,
            "next_service_params": {
                "symbol": "EXAMPLE", "from_date": args.from_date, "to_date": args.to_date,
                "company_id": "b" * 64, "event_id": event_id,
                "document_id": document_id, "period_quarter": 1,
                "period_fy_start": 2026, "period_end": "2026-06-30",
            },
        }
        metrics = {"next_service_params": values["next_service_params"]}
        signals = {"next_service_params": values["next_service_params"]}
        alerts = {"next_service_params": values["next_service_params"], "message": "ok"}
        callback = Mock()

        with patch.object(run, "request_json", side_effect=[step3, metrics, signals, alerts]) as request, \
             patch.object(run, "wait_for_values_job", return_value=values):
            result = run.run_exact_document_flow(
                args,
                company_id="b" * 64,
                source_url=source_url,
                resolved_callback=callback,
            )

        self.assertEqual(event_id, result["canonical_event_id"])
        callback.assert_called_once_with(event_id)
        first_url = request.call_args_list[0].args[1]
        self.assertIn(":8022/event-type/resolve", first_url)
        query = request.call_args_list[0].kwargs["query"]
        document = json.loads(query["documents_json"])[0]
        self.assertEqual("nse_exact", document["source_mode"])
        self.assertEqual(source_url, document["source_url"])
        called_urls = [call.args[1] for call in request.call_args_list]
        self.assertFalse(any(":8020/" in url or ":8021/" in url for url in called_urls))


if __name__ == "__main__":
    unittest.main()
