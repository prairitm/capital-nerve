"""Unit tests for `services/ir_discovery/ingest` covering the branches that
do not need a live DB (mismatched period type, download failure, schema /
mapping invariants).

Round-trip DB tests live in the integration test environment. These checks
are pure-function or mock-based so they run alongside the rest of
`backend/tests/`.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.db.enums import DocumentType, EventType, PeriodType
from app.services import ingest_common
from app.services.ir_discovery import download as download_module
from app.services.ir_discovery import ingest as ingest_module
from app.services.ir_discovery.ingest import IngestOutcome, ingest_one
from app.services.ir_discovery.schemas import (
    DOC_TYPE_BY_ASSET_KEY,
    AssetMatch,
    CompanyRef,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)


# ---------------------------------------------------------------------------
# Static / shape invariants
# ---------------------------------------------------------------------------


def test_doc_type_by_asset_key_covers_every_asset_field():
    """Every non-meta field on `PeriodAssetSet` must appear in the
    asset-key map; otherwise `ingest_one` would silently drop assets."""
    meta_fields = {"company", "period", "notes"}
    asset_fields = set(PeriodAssetSet.model_fields) - meta_fields
    assert asset_fields == set(DOC_TYPE_BY_ASSET_KEY)


def test_doc_type_by_asset_key_pairs_match_enums():
    """Sanity-check the (EventType, DocumentType) pairs."""
    assert DOC_TYPE_BY_ASSET_KEY["financial_report_pdf"] == (
        EventType.QUARTERLY_RESULT,
        DocumentType.FINANCIAL_RESULT,
    )
    assert DOC_TYPE_BY_ASSET_KEY["transcript"] == (
        EventType.CONCALL_TRANSCRIPT,
        DocumentType.CONCALL_TRANSCRIPT,
    )
    assert DOC_TYPE_BY_ASSET_KEY["presentation"] == (
        EventType.INVESTOR_PRESENTATION,
        DocumentType.INVESTOR_PRESENTATION,
    )
    assert DOC_TYPE_BY_ASSET_KEY["annual_report"] == (
        EventType.ANNUAL_REPORT,
        DocumentType.ANNUAL_REPORT,
    )


def test_assetingestresult_jsonable_roundtrip():
    res = ingest_module.AssetIngestResult(
        asset_key="transcript",
        event_type=EventType.CONCALL_TRANSCRIPT,
        document_type=DocumentType.CONCALL_TRANSCRIPT,
        url="https://example.com/q3.pdf",
        status="ingested",
        event_id=1,
        document_id=2,
        job_id=3,
        review_id=4,
        file_hash="abc",
        size_bytes=1024,
    )
    payload = res.to_jsonable()
    assert payload["status"] == "ingested"
    assert payload["event_type"] == "CONCALL_TRANSCRIPT"
    assert payload["document_type"] == "CONCALL_TRANSCRIPT"


def test_ingestoutcome_summary_counts():
    outcome = IngestOutcome(company=_company(), period=_period_quarterly())
    outcome.assets.append(_make_result(status="ingested"))
    outcome.assets.append(_make_result(status="duplicate"))
    outcome.assets.append(_make_result(status="failed", error="boom"))
    outcome.assets.append(_make_result(status="queued"))
    payload = outcome.to_jsonable()
    assert payload["summary"] == {"successful": 2, "duplicates": 1, "failures": 1}


# ---------------------------------------------------------------------------
# Period / asset mismatch branches (no DB required)
# ---------------------------------------------------------------------------


def test_annual_asset_on_quarterly_period_skipped(monkeypatch):
    """An `annual_report` asset on a quarterly period must be skipped without
    triggering a download or DB write."""
    download_calls = []

    def _spy(*args, **kwargs):
        download_calls.append(kwargs)
        raise AssertionError("download must not be called for skipped assets")

    monkeypatch.setattr(download_module, "fetch_to_storage", _spy)
    monkeypatch.setattr(ingest_module, "fetch_to_storage", _spy)

    db = MagicMock()
    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        annual_report=AssetMatch(url="https://x/ar.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
    )
    assert len(outcome.assets) == 1
    skipped = outcome.assets[0]
    assert skipped.asset_key == "annual_report"
    assert skipped.status == "skipped"
    assert "annual_report asset on a quarterly period" in (skipped.error or "")
    db.add.assert_not_called()
    assert download_calls == []


def test_quarterly_asset_on_annual_period_skipped(monkeypatch):
    monkeypatch.setattr(
        download_module,
        "fetch_to_storage",
        lambda **_: pytest.fail("download must not be called"),
    )
    monkeypatch.setattr(
        ingest_module,
        "fetch_to_storage",
        lambda **_: pytest.fail("download must not be called"),
    )
    db = MagicMock()
    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="FY2025-26",
        financial_report_pdf=AssetMatch(url="https://x/q.pdf"),
        transcript=AssetMatch(url="https://x/t.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_annual(),
        assets=assets,
        queued_by_user_id=1,
    )
    assert {a.status for a in outcome.assets} == {"skipped"}
    assert all("annual period" in (a.error or "") for a in outcome.assets)
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# Download failure branch
# ---------------------------------------------------------------------------


def test_download_failure_is_captured_without_db_writes(monkeypatch):
    """A FetchError must surface as a `failed` AssetIngestResult and skip
    every subsequent step (period resolution, table writes, pipeline)."""

    def _boom(**_):
        raise ingest_common.FetchError("HTTP 404")

    monkeypatch.setattr(download_module, "fetch_to_storage", _boom)
    monkeypatch.setattr(ingest_module, "fetch_to_storage", _boom)

    db = MagicMock()
    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        financial_report_pdf=AssetMatch(url="https://x/missing.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
    )
    assert len(outcome.assets) == 1
    failed = outcome.assets[0]
    assert failed.status == "failed"
    assert "HTTP 404" in (failed.error or "")
    db.add.assert_not_called()
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Asset filtering (--doc-types)
# ---------------------------------------------------------------------------


def test_asset_keys_filter_excludes_unselected_assets(monkeypatch):
    """When `asset_keys` is supplied, only those slots are considered."""
    monkeypatch.setattr(
        download_module,
        "fetch_to_storage",
        lambda **_: pytest.fail("filtered asset must not be downloaded"),
    )
    monkeypatch.setattr(
        ingest_module,
        "fetch_to_storage",
        lambda **_: pytest.fail("filtered asset must not be downloaded"),
    )

    db = MagicMock()
    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        transcript=AssetMatch(url="https://x/t.pdf"),
        presentation=AssetMatch(url="https://x/p.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
        asset_keys=("financial_report_pdf",),  # neither slot above is in the filter
    )
    assert outcome.assets == []


def test_unknown_asset_key_recorded_as_error():
    db = MagicMock()
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=PeriodAssetSet(
            company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
            period="Q3 FY2025-26",
        ),
        queued_by_user_id=1,
        asset_keys=("definitely_not_a_real_key",),
    )
    assert outcome.errors == ["Unknown asset_key: definitely_not_a_real_key"]
    assert outcome.assets == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _company() -> CompanyTarget:
    return CompanyTarget(
        company_id=42,
        company_name="Reliance Industries Ltd.",
        nse_symbol="RELIANCE",
        bse_code="500325",
        investor_relations_url="https://www.ril.com/investors",
    )


def _period_quarterly() -> PeriodSpec:
    return PeriodSpec(
        fy_year=2025,
        period_type=PeriodType.QUARTERLY,
        quarter=3,
        period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
        fy_label="FY2025-26",
        display_label="Q3 FY2025-26",
    )


def _period_annual() -> PeriodSpec:
    return PeriodSpec(
        fy_year=2025,
        period_type=PeriodType.ANNUAL,
        quarter=None,
        period_start=date(2025, 4, 1),
        period_end=date(2026, 3, 31),
        fy_label="FY2025-26",
        display_label="FY2025-26",
    )


def _make_result(status: str, error: str | None = None) -> ingest_module.AssetIngestResult:
    return ingest_module.AssetIngestResult(
        asset_key="transcript",
        event_type=EventType.CONCALL_TRANSCRIPT,
        document_type=DocumentType.CONCALL_TRANSCRIPT,
        url="https://example.com/x.pdf",
        status=status,
        error=error,
    )
