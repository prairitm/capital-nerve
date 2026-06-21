"""Unit tests for `services/ir_discovery/exchange/bse_client`.

Uses `httpx.MockTransport` to feed the client a representative
`AnnGetData/w` payload — no live network hits.
"""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from app.db.enums import DocumentType
from app.services.ir_discovery.exchange import bse_client
from app.services.ir_discovery.exchange.schemas import ExchangeFiling


# A minimal-but-realistic shape captured from BSE's AnnGetData/w endpoint.
_FIXTURE_PAYLOAD = {
    "Table": [
        {
            "NEWSID": "ABC1",
            "NEWS_DT": "2025-10-15T18:42:00",
            "HEADLINE": "Q2 FY26 Financial Results",
            "CATEGORYNAME": "Result",
            "SUBCATNAME": None,
            "ATTACHMENTNAME": "5e9d2af9-4c4f-4f3e-86c5-1b9ad2c7bbd1.pdf",
        },
        {
            "NEWSID": "ABC2",
            "NEWS_DT": "2025-10-16T19:15:00",
            "HEADLINE": "Q2 FY26 Earnings Call Transcript",
            "CATEGORYNAME": "Analysts/Institutional Investor Meet",
            "SUBCATNAME": None,
            "ATTACHMENTNAME": "transcript-q2.pdf",
        },
        {
            "NEWSID": "ABC3",
            "NEWS_DT": "2025-10-17T20:00:00",
            "HEADLINE": "Q2 FY26 Investor Presentation",
            "CATEGORYNAME": "Company Update",
            "SUBCATNAME": "Investor Presentation",
            "ATTACHMENTNAME": "https://www.example.com/full-url.pdf",  # absolute URL stays as-is
        },
        {
            "NEWSID": "ABC4",
            "NEWS_DT": "2025-10-18T08:00:00",
            "HEADLINE": "Trading Window Closure",
            "CATEGORYNAME": "Trading Window",
            "SUBCATNAME": None,
            "ATTACHMENTNAME": "tw.pdf",
        },
    ]
}


def _mock_client(payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "AnnGetData/w" in request.url.path
        # Confirm the params we promise to send
        assert request.url.params.get("strScrip") == "500325"
        assert request.url.params.get("strType") == "C"
        assert request.url.params.get("strSearch") == "P"
        assert request.url.params.get("strPrevDate") == "20251001"
        assert request.url.params.get("strToDate") == "20251231"
        return httpx.Response(200, content=json.dumps(payload), headers={"content-type": "application/json"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_list_filings_parses_known_categories():
    client = _mock_client(_FIXTURE_PAYLOAD)
    try:
        rows = bse_client.list_filings(
            scrip="500325",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            client=client,
        )
    finally:
        client.close()

    assert len(rows) == 4
    by_doc_type = {f.document_type: f for f in rows}
    assert DocumentType.FINANCIAL_RESULT in by_doc_type
    assert DocumentType.CONCALL_TRANSCRIPT in by_doc_type
    assert DocumentType.INVESTOR_PRESENTATION in by_doc_type
    # "Trading Window" is not in the map.
    assert by_doc_type.get(None) is not None
    unmapped = by_doc_type[None]
    assert unmapped.headline == "Trading Window Closure"


def test_list_filings_rebuilds_attachment_url():
    client = _mock_client(_FIXTURE_PAYLOAD)
    try:
        rows = bse_client.list_filings(
            scrip="500325",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            client=client,
        )
    finally:
        client.close()

    fr = next(f for f in rows if f.document_type is DocumentType.FINANCIAL_RESULT)
    # Bare filename gets prepended with the BSE attachment base.
    assert fr.attachment_url.startswith("https://www.bseindia.com/xml-data/corpfiling/AttachLive/")
    assert fr.attachment_url.endswith("5e9d2af9-4c4f-4f3e-86c5-1b9ad2c7bbd1.pdf")

    pres = next(
        f for f in rows if f.document_type is DocumentType.INVESTOR_PRESENTATION
    )
    # Absolute URLs are preserved verbatim.
    assert pres.attachment_url == "https://www.example.com/full-url.pdf"


def test_list_filings_returns_empty_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        rows = bse_client.list_filings(
            scrip="500325",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            client=client,
        )
    finally:
        client.close()
    assert rows == []


def test_list_filings_returns_empty_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        rows = bse_client.list_filings(
            scrip="500325",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            client=client,
        )
    finally:
        client.close()
    assert rows == []


def test_filing_dataclass_carries_raw_row():
    client = _mock_client(_FIXTURE_PAYLOAD)
    try:
        rows = bse_client.list_filings(
            scrip="500325",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            client=client,
        )
    finally:
        client.close()
    sample: ExchangeFiling = rows[0]
    assert sample.source == "bse"
    assert sample.company_id_at_source == "500325"
    assert sample.raw["NEWSID"] == "ABC1"
