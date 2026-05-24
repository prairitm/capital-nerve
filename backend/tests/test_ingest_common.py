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
        symbol="RELIANCE",
        period_slug="Q3_FY2025-26",
        document_type=DocumentType.FINANCIAL_RESULT,
    )
    assert stem == "RELIANCE_Q3_FY2025-26_financial_result"


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
