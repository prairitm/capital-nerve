"""Unit tests for `services/ir_discovery/exchange/discover`.

Exercises the orchestration logic without hitting BSE / NSE: both
clients are monkey-patched on the `discover` module so we can assert
the BSE-first / NSE-fallback / agent-merge flow.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest

from app.db.enums import DocumentType, PeriodType
from app.services.ir_discovery.exchange import bse_client, discover, nse_client
from app.services.ir_discovery.exchange.schemas import ExchangeFiling
from app.services.ir_discovery.schemas import (
    AssetMatch,
    CompanyRef,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _company(*, bse_code: str | None = "500325") -> CompanyTarget:
    return CompanyTarget(
        company_id=42,
        company_name="Reliance Industries Ltd.",
        nse_symbol="RELIANCE",
        bse_code=bse_code,
        investor_relations_url="https://www.ril.com/investors",
    )


def _quarterly_period() -> PeriodSpec:
    return PeriodSpec(
        fy_year=2025,
        period_type=PeriodType.QUARTERLY,
        quarter=3,
        period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
        fy_label="FY2025-26",
        display_label="Q3 FY2025-26",
    )


def _annual_period() -> PeriodSpec:
    return PeriodSpec(
        fy_year=2025,
        period_type=PeriodType.ANNUAL,
        quarter=None,
        period_start=date(2025, 4, 1),
        period_end=date(2026, 3, 31),
        fy_label="FY2025-26",
        display_label="FY2025-26",
    )


def _bse_filing(doc_type: DocumentType, *, day: int = 15, url_suffix: str = "x.pdf") -> ExchangeFiling:
    return ExchangeFiling(
        source="bse",
        company_id_at_source="500325",
        filing_date=datetime(2026, 1, day, 18, 30),
        headline=f"BSE {doc_type.value}",
        category="Result" if doc_type == DocumentType.FINANCIAL_RESULT else "Other",
        subcategory=None,
        attachment_url=f"https://www.bseindia.com/{url_suffix}",
        document_type=doc_type,
        source_page="https://www.bseindia.com/corporates/ann.html",
        raw={},
    )


def _nse_filing(doc_type: DocumentType, *, day: int = 15) -> ExchangeFiling:
    return ExchangeFiling(
        source="nse",
        company_id_at_source="RELIANCE",
        filing_date=datetime(2026, 1, day, 18, 30),
        headline=f"NSE {doc_type.value}",
        category="Some category",
        subcategory=None,
        attachment_url=f"https://archives.nseindia.com/{doc_type.value}.pdf",
        document_type=doc_type,
        source_page="https://www.nseindia.com/...",
        raw={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_assets_filled_by_bse_records_nse_as_fallback(monkeypatch):
    """When BSE covers every slot, NSE is still queried (cheap) and any
    matching NSE filings are stashed as download-time fallbacks. This
    is what saves a run when BSE returns a 200 OK HTML wrapper for the
    primary URL."""
    bse_calls: list[dict] = []
    nse_calls: list[dict] = []

    def fake_bse(**kwargs):
        bse_calls.append(kwargs)
        return [
            _bse_filing(DocumentType.FINANCIAL_RESULT),
            _bse_filing(DocumentType.CONCALL_TRANSCRIPT, day=20),
            _bse_filing(DocumentType.INVESTOR_PRESENTATION, day=18),
        ]

    def fake_nse(**kwargs):
        nse_calls.append(kwargs)
        # NSE has a transcript filing that should NOT replace BSE's primary
        # but should be recorded as a fallback for the transcript slot.
        return [_nse_filing(DocumentType.CONCALL_TRANSCRIPT)]

    monkeypatch.setattr(bse_client, "list_filings", fake_bse)
    monkeypatch.setattr(nse_client, "list_filings", fake_nse)

    result = asyncio.run(discover.discover_period_assets(_company(), _quarterly_period()))

    # Primaries still BSE.
    assert result.source_by_asset_key == {
        "financial_report_pdf": "bse",
        "transcript": "bse",
        "presentation": "bse",
    }
    # NSE was queried even though BSE covered everything.
    assert len(bse_calls) == 1
    assert len(nse_calls) == 1
    # The NSE transcript URL is parked as a fallback under that slot.
    transcript_fallbacks = result.fallback_by_asset_key.get("transcript", [])
    assert len(transcript_fallbacks) == 1
    fb_match, fb_source = transcript_fallbacks[0]
    assert fb_source == "nse"
    assert fb_match.url.endswith(f"{DocumentType.CONCALL_TRANSCRIPT.value}.pdf")
    # Slots NSE didn't have anything for stay free of fallback noise.
    assert "financial_report_pdf" not in result.fallback_by_asset_key
    assert "presentation" not in result.fallback_by_asset_key


def test_nse_fills_slot_missing_from_bse(monkeypatch):
    def fake_bse(**kwargs):
        return [_bse_filing(DocumentType.FINANCIAL_RESULT)]

    def fake_nse(**kwargs):
        return [_nse_filing(DocumentType.CONCALL_TRANSCRIPT)]

    monkeypatch.setattr(bse_client, "list_filings", fake_bse)
    monkeypatch.setattr(nse_client, "list_filings", fake_nse)

    result = asyncio.run(discover.discover_period_assets(_company(), _quarterly_period()))

    assert result.source_by_asset_key.get("financial_report_pdf") == "bse"
    assert result.source_by_asset_key.get("transcript") == "nse"
    assert "presentation" not in result.source_by_asset_key
    assert result.missing_keys(("presentation",)) == ["presentation"]


def test_bse_skipped_when_no_bse_code(monkeypatch):
    bse_called = []
    monkeypatch.setattr(bse_client, "list_filings", lambda **kw: bse_called.append(kw))

    nse_calls: list[dict] = []

    def fake_nse(**kwargs):
        nse_calls.append(kwargs)
        return [_nse_filing(DocumentType.FINANCIAL_RESULT)]

    monkeypatch.setattr(nse_client, "list_filings", fake_nse)

    result = asyncio.run(
        discover.discover_period_assets(
            _company(bse_code=None),
            _quarterly_period(),
        )
    )
    assert result.source_by_asset_key.get("financial_report_pdf") == "nse"
    # No bse_code => no BSE call at all.
    assert bse_called == []
    assert len(nse_calls) == 1


def test_latest_filing_per_doc_type_wins(monkeypatch):
    """Two BSE result filings with different dates -> the later one wins."""
    def fake_bse(**kwargs):
        return [
            _bse_filing(DocumentType.FINANCIAL_RESULT, day=10, url_suffix="old.pdf"),
            _bse_filing(DocumentType.FINANCIAL_RESULT, day=22, url_suffix="new.pdf"),
        ]

    monkeypatch.setattr(bse_client, "list_filings", fake_bse)
    monkeypatch.setattr(nse_client, "list_filings", lambda **kw: [])

    result = asyncio.run(discover.discover_period_assets(_company(), _quarterly_period()))
    assert result.assets.financial_report_pdf is not None
    assert result.assets.financial_report_pdf.url.endswith("new.pdf")


def test_quarterly_period_skips_annual_report_slot(monkeypatch):
    def fake_bse(**kwargs):
        # Even if BSE returns an annual_report match, the orchestrator
        # must not project it onto a quarterly period.
        return [_bse_filing(DocumentType.ANNUAL_REPORT)]

    monkeypatch.setattr(bse_client, "list_filings", fake_bse)
    monkeypatch.setattr(nse_client, "list_filings", lambda **kw: [])

    result = asyncio.run(discover.discover_period_assets(_company(), _quarterly_period()))
    assert result.assets.annual_report is None


def test_annual_period_only_requests_annual_report(monkeypatch):
    bse_called = []

    def fake_bse(**kwargs):
        bse_called.append(kwargs)
        return [
            _bse_filing(DocumentType.ANNUAL_REPORT),
            _bse_filing(DocumentType.FINANCIAL_RESULT),  # ignored
        ]

    monkeypatch.setattr(bse_client, "list_filings", fake_bse)
    monkeypatch.setattr(nse_client, "list_filings", lambda **kw: [])

    result = asyncio.run(discover.discover_period_assets(_company(), _annual_period()))
    assert result.assets.annual_report is not None
    assert result.assets.financial_report_pdf is None
    assert result.assets.transcript is None
    assert result.assets.presentation is None
    assert result.source_by_asset_key.get("annual_report") == "bse"


def test_bse_failure_falls_through_to_nse(monkeypatch):
    """If BSE raises, the orchestrator should still try NSE — never crash."""
    def fake_bse(**kwargs):
        raise RuntimeError("BSE down")

    def fake_nse(**kwargs):
        return [_nse_filing(DocumentType.FINANCIAL_RESULT)]

    monkeypatch.setattr(bse_client, "list_filings", fake_bse)
    monkeypatch.setattr(nse_client, "list_filings", fake_nse)

    result = asyncio.run(discover.discover_period_assets(_company(), _quarterly_period()))
    assert result.source_by_asset_key.get("financial_report_pdf") == "nse"


# ---------------------------------------------------------------------------
# merge_with_agent
# ---------------------------------------------------------------------------


def test_merge_with_agent_fills_empty_slots_and_records_filled_as_fallbacks():
    """The agent's URL becomes the primary for empty slots, AND a
    fallback for slots tier-1 already covered. This is what saves a
    run when BSE returns a broken URL for the financial result."""
    exchange = discover.DiscoveryResult(
        assets=PeriodAssetSet(
            company=CompanyRef(symbol="RELIANCE", name="Reliance"),
            period="Q3 FY2025-26",
            financial_report_pdf=AssetMatch(url="https://bse/result.pdf", title="bse"),
        ),
        source_by_asset_key={"financial_report_pdf": "bse"},
    )
    agent = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance"),
        period="Q3 FY2025-26",
        financial_report_pdf=AssetMatch(url="https://agent/result.pdf"),
        transcript=AssetMatch(url="https://agent/transcript.pdf"),
        presentation=AssetMatch(url="https://agent/pres.pdf"),
    )

    merged = discover.merge_with_agent(
        exchange,
        agent,
        keys_to_fill=["financial_report_pdf", "transcript", "presentation"],
    )

    # Primary URLs: BSE wins where it had a hit, agent fills the rest.
    assert merged.assets.financial_report_pdf.url == "https://bse/result.pdf"
    assert merged.assets.transcript.url == "https://agent/transcript.pdf"
    assert merged.assets.presentation.url == "https://agent/pres.pdf"

    assert merged.source_by_asset_key == {
        "financial_report_pdf": "bse",
        "transcript": "agent",
        "presentation": "agent",
    }

    # The agent's financial_report_pdf URL is parked as a fallback
    # because BSE held the primary slot.
    fallbacks = merged.fallback_by_asset_key.get("financial_report_pdf", [])
    assert len(fallbacks) == 1
    fb_match, fb_source = fallbacks[0]
    assert fb_source == "agent"
    assert fb_match.url == "https://agent/result.pdf"
    # Agent-primary slots have no fallbacks (we don't duplicate the
    # primary in the fallback list).
    assert "transcript" not in merged.fallback_by_asset_key
    assert "presentation" not in merged.fallback_by_asset_key


def test_merge_with_agent_preserves_existing_nse_fallbacks():
    """If discover_period_assets already recorded NSE fallbacks, the
    agent's URLs are appended after them, not overwriting."""
    nse_alt = AssetMatch(url="https://archives.nseindia.com/result.pdf")
    exchange = discover.DiscoveryResult(
        assets=PeriodAssetSet(
            company=CompanyRef(symbol="RELIANCE", name="Reliance"),
            period="Q3 FY2025-26",
            financial_report_pdf=AssetMatch(url="https://bse/result.pdf"),
        ),
        source_by_asset_key={"financial_report_pdf": "bse"},
        fallback_by_asset_key={"financial_report_pdf": [(nse_alt, "nse")]},
    )
    agent = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance"),
        period="Q3 FY2025-26",
        financial_report_pdf=AssetMatch(url="https://agent/result.pdf"),
    )
    merged = discover.merge_with_agent(
        exchange, agent, keys_to_fill=["financial_report_pdf"]
    )
    fbs = merged.fallback_by_asset_key["financial_report_pdf"]
    # NSE first, then agent — preserved priority order.
    assert [src for _, src in fbs] == ["nse", "agent"]
    assert [m.url for m, _ in fbs] == [
        "https://archives.nseindia.com/result.pdf",
        "https://agent/result.pdf",
    ]


def test_merge_with_agent_skips_missing_agent_fields():
    exchange = discover.DiscoveryResult(
        assets=PeriodAssetSet(
            company=CompanyRef(symbol="X", name="X"),
            period="Q3 FY2025-26",
        ),
        source_by_asset_key={},
    )
    # Agent only found financial_report_pdf — transcript still empty.
    agent = PeriodAssetSet(
        company=CompanyRef(symbol="X", name="X"),
        period="Q3 FY2025-26",
        financial_report_pdf=AssetMatch(url="https://agent/r.pdf"),
    )
    merged = discover.merge_with_agent(
        exchange,
        agent,
        keys_to_fill=["financial_report_pdf", "transcript"],
    )
    assert merged.assets.financial_report_pdf is not None
    assert merged.source_by_asset_key.get("financial_report_pdf") == "agent"
    assert merged.assets.transcript is None
    assert "transcript" not in merged.source_by_asset_key
