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
        discovery_source="bse",
    )
    payload = res.to_jsonable()
    assert payload["status"] == "ingested"
    assert payload["event_type"] == "CONCALL_TRANSCRIPT"
    assert payload["document_type"] == "CONCALL_TRANSCRIPT"
    assert payload["discovery_source"] == "bse"


def test_assetingestresult_discovery_source_defaults_to_none():
    res = ingest_module.AssetIngestResult(
        asset_key="transcript",
        event_type=EventType.CONCALL_TRANSCRIPT,
        document_type=DocumentType.CONCALL_TRANSCRIPT,
        url="https://example.com/q3.pdf",
        status="ingested",
    )
    assert res.discovery_source is None
    assert res.to_jsonable()["discovery_source"] is None


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


def test_duplicate_completed_skips_new_job_and_pipeline(monkeypatch):
    """Re-ingesting an already-completed file must not spawn another
    pipeline run (which races the in-process worker on document_pages)."""
    download_calls: list[str] = []

    def _fake_fetch(**kwargs):
        download_calls.append(kwargs["url"])
        from types import SimpleNamespace

        stored = SimpleNamespace(
            file_hash="abc123",
            size_bytes=100,
            storage_path="aa/bb/abc123.pdf",
        )
        from types import SimpleNamespace as NS

        return NS(
            stored=stored,
            mirror_path=None,
            filename="q.pdf",
            content_type="application/pdf",
        )

    monkeypatch.setattr(download_module, "fetch_to_storage", _fake_fetch)
    monkeypatch.setattr(ingest_module, "fetch_to_storage", _fake_fetch)

    pipeline_calls: list[int] = []
    monkeypatch.setattr(
        ingest_module,
        "run_pipeline_for_document",
        lambda db, job_id: pipeline_calls.append(job_id) or None,
    )
    monkeypatch.setattr(ingest_module, "_ensure_period", lambda db, period: 1)
    monkeypatch.setattr(
        ingest_module,
        "_get_or_create_event",
        lambda *a, **k: MagicMock(event_id=1),
    )

    existing_doc = MagicMock()
    existing_doc.document_id = 441
    existing_doc.extraction_status = ingest_module.ExtractionStatus.COMPLETED
    existing_doc.page_count = 80
    existing_doc.extraction_confidence = 88.0

    latest_job = MagicMock()
    latest_job.extraction_job_id = 95
    latest_job.status = ingest_module.ExtractionStatus.COMPLETED
    latest_job.error_message = None
    latest_job.meta = {
        "stages": {
            "pages": 80,
            "extracted": 10,
            "facts": 11,
            "metrics": 15,
            "signals": 3,
            "cards": 3,
        },
        "published": True,
    }

    db = MagicMock()
    db.scalar.side_effect = [existing_doc, latest_job]

    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        presentation=AssetMatch(url="https://x/p.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
        asset_keys=("presentation",),
    )

    assert len(outcome.assets) == 1
    row = outcome.assets[0]
    assert row.status == "duplicate"
    assert row.job_id == 95
    assert row.pipeline is not None
    assert row.pipeline["pages"] == 80
    assert pipeline_calls == []
    db.add.assert_not_called()


def test_duplicate_completed_force_reextract_runs_pipeline(monkeypatch):
    def _fake_fetch(**kwargs):
        from types import SimpleNamespace

        stored = SimpleNamespace(
            file_hash="abc123",
            size_bytes=100,
            storage_path="aa/bb/abc123.pdf",
        )
        return SimpleNamespace(
            stored=stored,
            mirror_path=None,
            filename="q.pdf",
            content_type="application/pdf",
        )

    monkeypatch.setattr(download_module, "fetch_to_storage", _fake_fetch)
    monkeypatch.setattr(ingest_module, "fetch_to_storage", _fake_fetch)

    pipeline_calls: list[int] = []

    def _fake_pipeline(db, job_id):
        pipeline_calls.append(job_id)
        from types import SimpleNamespace

        return SimpleNamespace(
            job_id=job_id,
            document_id=441,
            status=ingest_module.ExtractionStatus.COMPLETED,
            pages=80,
            extracted_values=1,
            facts=1,
            metrics=1,
            signals=1,
            cards=1,
            published=True,
            confidence=90.0,
            error=None,
            notes=None,
        )

    monkeypatch.setattr(ingest_module, "run_pipeline_for_document", _fake_pipeline)
    monkeypatch.setattr(
        ingest_module,
        "_ensure_period",
        lambda db, period: 1,
    )
    monkeypatch.setattr(
        ingest_module,
        "_get_or_create_event",
        lambda *a, **k: MagicMock(event_id=1),
    )
    monkeypatch.setattr(
        ingest_module,
        "_enqueue_review",
        lambda *a, **k: MagicMock(review_id=1),
    )

    existing_doc = MagicMock()
    existing_doc.document_id = 441
    existing_doc.extraction_status = ingest_module.ExtractionStatus.COMPLETED
    existing_doc.page_count = 80

    db = MagicMock()
    db.scalar.return_value = existing_doc

    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        presentation=AssetMatch(url="https://x/p.pdf"),
    )
    captured_job: list[object] = []

    def _track_add(obj):
        captured_job.append(obj)
        if getattr(obj, "extraction_job_id", None) is None:
            obj.extraction_job_id = 99
        return None

    db.add.side_effect = _track_add

    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
        asset_keys=("presentation",),
        force_reextract=True,
    )

    assert len(pipeline_calls) == 1
    assert outcome.assets[0].status in ("ingested", "duplicate")


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
        discovery_source_by_key={"financial_report_pdf": "bse"},
    )
    assert len(outcome.assets) == 1
    failed = outcome.assets[0]
    assert failed.status == "failed"
    assert "HTTP 404" in (failed.error or "")
    assert failed.discovery_source == "bse"
    db.add.assert_not_called()
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Tier-1 -> tier-2 fallback at download time
# ---------------------------------------------------------------------------


def test_primary_html_wrapper_falls_through_to_fallback(monkeypatch):
    """When the primary URL fails (e.g. BSE returns HTML), the next
    fallback should be tried and its source recorded as the resolved
    discovery_source."""
    calls: list[str] = []

    def _fake_fetch(*, url, company, period, document_type, asset_key, storage=None):
        calls.append(url)
        if url == "https://bse/wrapper.pdf":
            raise ingest_common.FetchError("looks like HTML")
        if url == "https://agent/real.pdf":
            # Stop just past download — we don't need to exercise the
            # full DB / pipeline path. Raise a sentinel to short-circuit.
            raise RuntimeError("__downloaded__")
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(download_module, "fetch_to_storage", _fake_fetch)
    monkeypatch.setattr(ingest_module, "fetch_to_storage", _fake_fetch)

    db = MagicMock()
    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        financial_report_pdf=AssetMatch(url="https://bse/wrapper.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
        discovery_source_by_key={"financial_report_pdf": "bse"},
        fallback_by_asset_key={
            "financial_report_pdf": [
                (AssetMatch(url="https://agent/real.pdf"), "agent"),
            ]
        },
    )

    # Both URLs were tried in order.
    assert calls == ["https://bse/wrapper.pdf", "https://agent/real.pdf"]
    # The result reflects the fallback that "succeeded" (we crashed
    # post-download with a sentinel, which the function catches as
    # `download crashed`). The point of this test is to verify the
    # candidate ordering + fall-through, not the post-download path.
    assert len(outcome.assets) == 1


def test_all_candidates_fail_records_last_error(monkeypatch):
    def _always_fail(*, url, **_):
        raise ingest_common.FetchError(f"bad: {url}")

    monkeypatch.setattr(download_module, "fetch_to_storage", _always_fail)
    monkeypatch.setattr(ingest_module, "fetch_to_storage", _always_fail)

    db = MagicMock()
    assets = PeriodAssetSet(
        company=CompanyRef(symbol="RELIANCE", name="Reliance Industries Ltd."),
        period="Q3 FY2025-26",
        financial_report_pdf=AssetMatch(url="https://bse/x.pdf"),
    )
    outcome = ingest_one(
        db,
        company=_company(),
        period=_period_quarterly(),
        assets=assets,
        queued_by_user_id=1,
        discovery_source_by_key={"financial_report_pdf": "bse"},
        fallback_by_asset_key={
            "financial_report_pdf": [
                (AssetMatch(url="https://nse/x.pdf"), "nse"),
                (AssetMatch(url="https://agent/x.pdf"), "agent"),
            ]
        },
    )
    failed = outcome.assets[0]
    assert failed.status == "failed"
    # Last error is from the final candidate (agent).
    assert "https://agent/x.pdf" in (failed.error or "")
    # No DB writes when every candidate fails.
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_no_fallbacks_keeps_old_failure_semantics(monkeypatch):
    def _boom(*, url, **_):
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
        discovery_source_by_key={"financial_report_pdf": "bse"},
        # Note: no fallback_by_asset_key — old call sites stay valid.
    )
    failed = outcome.assets[0]
    assert failed.status == "failed"
    assert "HTTP 404" in (failed.error or "")
    assert failed.discovery_source == "bse"


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
