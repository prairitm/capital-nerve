"""Smoke tests for the shared ingest helpers used by both
`routers/ingest.py` and `services/ir_discovery/`.

These tests intentionally avoid network and DB so they run in the standard
unit-test job. URL fetch with a real httpx client is exercised in
integration tests against a local fixture server.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import ingest_common
from app.services.ingest_common import (
    parse_period_label,
    quarter_date_bounds,
    suffix_for,
)


# ---------------------------------------------------------------------------
# Period parsing / quarter math
# ---------------------------------------------------------------------------


def test_parse_period_label_4_digit_year():
    assert parse_period_label("Q4 FY2024-25") == (4, 2024)


def test_parse_period_label_2_digit_year():
    assert parse_period_label("Q1 FY25-26") == (1, 2025)


def test_parse_period_label_slash_variant():
    assert parse_period_label("q3 fy24/25") == (3, 2024)


def test_parse_period_label_unrecognised_returns_none():
    assert parse_period_label("FY25") is None
    assert parse_period_label("Q5 FY25-26") is None


def test_quarter_date_bounds_indian_fy_q1():
    start, end, fy_label, display = quarter_date_bounds(2025, 1)
    assert start == date(2025, 4, 1)
    assert end == date(2025, 6, 30)
    assert fy_label == "FY2025-26"
    assert display == "Q1 FY2025-26"


def test_format_quarterly_display_label():
    assert ingest_common.format_quarterly_display_label(2025, 3) == "Q3 FY2025-26"


def test_format_annual_display_label():
    assert ingest_common.format_annual_display_label(2025) == "FY2025-26"


def test_period_slug_from_display_label():
    assert ingest_common.period_slug_from_display_label("Q3 FY2025-26") == "Q3_FY2025-26"


def test_standard_document_basename():
    from app.db.enums import DocumentType

    stem = ingest_common.standard_document_basename(
        document_type=DocumentType.FINANCIAL_RESULT,
    )
    assert stem == "financial_result"


def test_standard_document_title():
    from app.db.enums import DocumentType

    title = ingest_common.standard_document_title(
        symbol="RELIANCE",
        display_label="Q3 FY2025-26",
        document_type=DocumentType.CONCALL_TRANSCRIPT,
    )
    assert title == "RELIANCE Q3 FY2025-26 Concall Transcript"


def test_quarter_date_bounds_q4_crosses_civil_year():
    start, end, fy_label, display = quarter_date_bounds(2025, 4)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 3, 31)
    assert display == "Q4 FY2025-26"


# ---------------------------------------------------------------------------
# Suffix detection
# ---------------------------------------------------------------------------


def test_suffix_for_filename_wins():
    assert suffix_for("Q3 results.PDF", "application/octet-stream") == ".pdf"


def test_suffix_for_falls_back_to_content_type():
    assert suffix_for(None, "application/pdf") == ".pdf"
    assert suffix_for("noextension", "text/markdown") == ".md"
    assert suffix_for(None, "text/plain") == ".txt"


def test_suffix_for_unknown_defaults_to_bin():
    assert suffix_for(None, None) == ".bin"


# ---------------------------------------------------------------------------
# fetch_document_from_url validation
# ---------------------------------------------------------------------------


def test_fetch_document_from_url_rejects_html_masquerading_as_pdf(monkeypatch):
    """BSE's CDN returns 200 OK with an HTML wrapper when an attachment id
    is missing. We must reject it instead of storing it as a `.pdf`."""
    import httpx

    html_body = (
        b"<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Transitional//EN\">\n"
        b"<html><head><title>BSE Ltd.</title></head><body>nope</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=html_body,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ingest_common.httpx, "Client", fake_client)

    with pytest.raises(ingest_common.FetchError, match="looks like HTML"):
        ingest_common.fetch_document_from_url(
            "https://www.bseindia.com/xml-data/corpfiling/AttachLive/missing.pdf"
        )


def test_fetch_document_from_url_accepts_real_pdf(monkeypatch):
    import httpx

    pdf_body = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 64 + b"\n%%EOF\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=pdf_body,
            headers={"content-type": "application/pdf"},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ingest_common.httpx, "Client", fake_client)

    data, filename, content_type = ingest_common.fetch_document_from_url(
        "https://www.example.com/foo.pdf"
    )
    assert data.startswith(b"%PDF-")
    assert filename == "foo.pdf"
    assert content_type == "application/pdf"


def test_download_headers_for_nse_uses_browser_ua():
    headers = ingest_common._download_headers_for("nsearchives.nseindia.com")
    assert "Mozilla" in headers["User-Agent"]
    assert headers["Referer"] == "https://www.nseindia.com/"


def test_download_headers_for_bse_uses_browser_ua():
    headers = ingest_common._download_headers_for("www.bseindia.com")
    assert "Mozilla" in headers["User-Agent"]
    assert headers["Referer"] == "https://www.bseindia.com/"


def test_download_headers_for_other_hosts_returns_empty():
    assert ingest_common._download_headers_for("www.example.com") == {}
    assert ingest_common._download_headers_for("api.openai.com") == {}


def test_download_timeout_for_exchange_hosts_is_generous():
    timeout = ingest_common._download_timeout_for("nsearchives.nseindia.com")
    # Exchange CDNs get 60s read window; everyone else stays at 30s.
    assert timeout.read == 60.0
    other = ingest_common._download_timeout_for("www.example.com")
    assert other.read == 30.0


def test_looks_like_html_detection():
    assert ingest_common._looks_like_html(b"<!DOCTYPE html><html><body></body></html>")
    assert ingest_common._looks_like_html(b"\n\n  <HTML><head>boo</head></HTML>")
    assert not ingest_common._looks_like_html(b"%PDF-1.7\nSome PDF data")
    assert not ingest_common._looks_like_html(b"Just some plain text")


# ---------------------------------------------------------------------------
# Refactor invariant: the router still imports from the shared module
# ---------------------------------------------------------------------------


def test_ensure_openai_api_key_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    from app.core.env import ensure_openai_api_key

    assert ensure_openai_api_key() == "sk-from-env"


def test_ensure_openai_api_key_syncs_from_settings(monkeypatch):
    """Agents SDK reads os.environ; bridge from Settings when the env var is empty."""
    from types import SimpleNamespace

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(OPENAI_API_KEY="sk-from-settings"),
    )
    from app.core.env import ensure_openai_api_key
    import os

    assert ensure_openai_api_key() == "sk-from-settings"
    assert os.environ["OPENAI_API_KEY"] == "sk-from-settings"


def test_ensure_openai_api_key_raises_when_missing(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(OPENAI_API_KEY=None),
    )
    from app.core.env import ensure_openai_api_key

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        ensure_openai_api_key()


def test_router_uses_shared_helpers():
    """The HTTP intake path must delegate to `ingest_common` so the CLI
    bulk-ingest stays in lockstep with `POST /ingest/upload`."""
    from app.routers import ingest as router_module

    assert router_module.fetch_document_from_url is ingest_common.fetch_document_from_url
    assert router_module.resolve_period_id is ingest_common.resolve_period_id
    assert router_module.suffix_for is ingest_common.suffix_for
