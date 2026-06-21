"""Unit tests for `services/ir_discovery/exchange/nse_client`.

Verifies the cookie-warmup pattern by counting MockTransport requests:
the first request must hit the NSE homepage (warmup) and the second
must hit the JSON API.
"""
from __future__ import annotations

import json
from datetime import date

import httpx

from app.db.enums import DocumentType
from app.services.ir_discovery.exchange import nse_client


_FIXTURE_PAYLOAD = [
    {
        "symbol": "RELIANCE",
        "desc": "Financial Results",
        "subCategory": None,
        "attchmntFile": "https://archives.nseindia.com/corporate/RIL_Q2_FY26_results.pdf",
        "attchmntText": "RIL Q2 FY26 Financial Results",
        "an_dt": "15-Oct-2025 18:30:00",
    },
    {
        "symbol": "RELIANCE",
        "desc": "Earnings Call Transcript",
        "subCategory": None,
        "attchmntFile": "https://archives.nseindia.com/corporate/RIL_Q2_FY26_transcript.pdf",
        "attchmntText": "Q2 FY26 Concall Transcript",
        "an_dt": "16-Oct-2025 10:15:00",
    },
    {
        "symbol": "RELIANCE",
        "desc": "Some Random Disclosure",
        "subCategory": None,
        "attchmntFile": "https://archives.nseindia.com/corporate/RIL_misc.pdf",
        "attchmntText": "Misc",
        "an_dt": "17-Oct-2025 09:00:00",
    },
]


def _mock_session(api_payload, *, fail_first_api: bool = False) -> nse_client._NSESession:
    homepage_calls = []
    api_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.nseindia.com" and request.url.path in ("/", ""):
            homepage_calls.append(request)
            return httpx.Response(
                200,
                content=b"<html>warmed</html>",
                headers={"set-cookie": "nsit=abc; Path=/"},
            )
        if "corporate-announcements" in request.url.path:
            api_calls.append(request)
            if fail_first_api and len(api_calls) == 1:
                return httpx.Response(401, content=b"unauth")
            return httpx.Response(
                200,
                content=json.dumps(api_payload),
                headers={"content-type": "application/json"},
            )
        return httpx.Response(404)

    session = nse_client._NSESession()
    session._client.close()
    session._client = httpx.Client(transport=httpx.MockTransport(handler))
    session._homepage_calls = homepage_calls  # type: ignore[attr-defined]
    session._api_calls = api_calls  # type: ignore[attr-defined]
    return session


def test_list_filings_warms_session_then_calls_api():
    session = _mock_session(_FIXTURE_PAYLOAD)
    try:
        rows = nse_client.list_filings(
            symbol="RELIANCE",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            session=session,
        )
    finally:
        session.close()
    assert len(rows) == 3

    # Warmup happens before the first API call.
    assert len(session._homepage_calls) == 1  # type: ignore[attr-defined]
    assert len(session._api_calls) == 1  # type: ignore[attr-defined]


def test_list_filings_categorises_known_filings():
    session = _mock_session(_FIXTURE_PAYLOAD)
    try:
        rows = nse_client.list_filings(
            symbol="RELIANCE",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            session=session,
        )
    finally:
        session.close()

    by_doc = {r.document_type: r for r in rows}
    assert DocumentType.FINANCIAL_RESULT in by_doc
    assert DocumentType.CONCALL_TRANSCRIPT in by_doc
    # "Some Random Disclosure" doesn't map.
    assert None in by_doc


def test_list_filings_retries_once_on_401():
    session = _mock_session(_FIXTURE_PAYLOAD, fail_first_api=True)
    try:
        rows = nse_client.list_filings(
            symbol="RELIANCE",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            session=session,
        )
    finally:
        session.close()
    # Recovery: the 401 forced a re-warm + retry.
    assert len(rows) == 3
    assert len(session._homepage_calls) == 2  # type: ignore[attr-defined] (initial + re-warm)
    assert len(session._api_calls) == 2  # type: ignore[attr-defined] (failed + success)


def test_list_filings_returns_empty_on_persistent_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.nseindia.com" and request.url.path in ("/", ""):
            return httpx.Response(200, content=b"warm")
        return httpx.Response(500, content=b"boom")

    session = nse_client._NSESession()
    session._client.close()
    session._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        rows = nse_client.list_filings(
            symbol="RELIANCE",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            session=session,
        )
    finally:
        session.close()
    assert rows == []


def test_attachment_url_https_upgrade():
    payload = [
        {
            "desc": "Financial Results",
            "attchmntFile": "archives.nseindia.com/corporate/foo.pdf",  # missing scheme
            "attchmntText": "FR",
            "an_dt": "15-Oct-2025 18:30:00",
        }
    ]
    session = _mock_session(payload)
    try:
        rows = nse_client.list_filings(
            symbol="RELIANCE",
            from_date=date(2025, 10, 1),
            to_date=date(2025, 12, 31),
            session=session,
        )
    finally:
        session.close()
    assert rows[0].attachment_url.startswith("https://archives.nseindia.com/")
