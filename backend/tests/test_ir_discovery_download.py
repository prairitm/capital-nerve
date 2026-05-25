"""Unit tests for `services/ir_discovery/download` (no DB).

We monkeypatch :func:`app.services.ingest_common.fetch_document_from_url`
so the test never makes a real HTTP request, then assert that the
canonical sha256 path and the human-browsable mirror are both written
under tmp dirs that override `STORAGE_DIR` / `IR_AGENT_RUNS_DIR`.
"""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from app.db.enums import DocumentType, PeriodType
from app.services import ingest_common, ir_discovery
from app.services.ir_discovery import download as download_module
from app.services.ir_discovery.schemas import CompanyTarget, PeriodSpec
from app.services.pipeline import storage as storage_module


_FAKE_PDF = b"%PDF-1.4 fake bytes for testing\n"


@pytest.fixture
def fake_storage(tmp_path, monkeypatch):
    """Point `LocalStorage` and the human mirror at temp dirs."""
    storage_root = tmp_path / "storage"
    runs_root = tmp_path / "ingest_runs"
    storage_root.mkdir()
    runs_root.mkdir()

    # Settings drives both paths; patch the cached singleton in place.
    from app.core.config import settings

    monkeypatch.setattr(settings, "STORAGE_DIR", str(storage_root))
    monkeypatch.setattr(settings, "IR_AGENT_RUNS_DIR", str(runs_root))

    # `LocalStorage()` reads `settings.storage_path` at construction; force a
    # fresh instance for each test by clearing any cached storage helper.
    storage = storage_module.LocalStorage(root=storage_root)
    monkeypatch.setattr(storage_module, "get_storage", lambda: storage)
    return storage_root, runs_root, storage


def _patch_fetch(monkeypatch, payload: bytes = _FAKE_PDF) -> None:
    def _fake_fetch(url: str):
        return payload, "report.pdf", "application/pdf"

    monkeypatch.setattr(ingest_common, "fetch_document_from_url", _fake_fetch)
    monkeypatch.setattr(download_module, "fetch_document_from_url", _fake_fetch)


def _company() -> CompanyTarget:
    return CompanyTarget(
        company_id=42,
        company_name="Reliance Industries Ltd.",
        nse_symbol="RELIANCE",
        bse_code="500325",
        investor_relations_url="https://www.ril.com/investors",
    )


def _period() -> PeriodSpec:
    return PeriodSpec(
        fy_year=2025,
        period_type=PeriodType.QUARTERLY,
        quarter=3,
        period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
        fy_label="FY2025-26",
        display_label="Q3 FY2025-26",
    )


def test_fetch_to_storage_writes_canonical_and_mirror(monkeypatch, fake_storage):
    storage_root, runs_root, _ = fake_storage
    _patch_fetch(monkeypatch)

    result = download_module.fetch_to_storage(
        url="https://www.ril.com/q3-fy25-26-results.pdf",
        company=_company(),
        period=_period(),
        document_type=DocumentType.FINANCIAL_RESULT,
        asset_key="financial_report_pdf",
    )

    expected_hash = hashlib.sha256(_FAKE_PDF).hexdigest()
    assert result.stored.file_hash == expected_hash
    assert result.stored.size_bytes == len(_FAKE_PDF)
    assert result.canonical_path.exists()
    assert result.canonical_path.read_bytes() == _FAKE_PDF
    # sha256-keyed two-level shard: aa/bb/<hash>.pdf
    assert result.canonical_path.parts[-3] == expected_hash[:2]
    assert result.canonical_path.parts[-2] == expected_hash[2:4]
    assert result.canonical_path.suffix == ".pdf"

    # Mirror path under runs_root/<symbol>/<period>/<asset_key>.pdf
    assert result.mirror_path is not None
    assert result.mirror_path.exists()
    assert result.mirror_path.read_bytes() == _FAKE_PDF
    assert result.mirror_path.parts[-3] == "RELIANCE"
    assert result.mirror_path.parts[-2] == "Q3_FY2025-26"
    assert result.mirror_path.name == "financial_result.pdf"


def test_fetch_to_storage_dedupes_on_repeat(monkeypatch, fake_storage):
    storage_root, runs_root, _ = fake_storage
    _patch_fetch(monkeypatch)

    first = download_module.fetch_to_storage(
        url="https://www.ril.com/q3.pdf",
        company=_company(),
        period=_period(),
        document_type=DocumentType.FINANCIAL_RESULT,
        asset_key="financial_report_pdf",
    )
    second = download_module.fetch_to_storage(
        url="https://www.ril.com/q3.pdf",
        company=_company(),
        period=_period(),
        document_type=DocumentType.FINANCIAL_RESULT,
        asset_key="financial_report_pdf",
    )

    assert first.stored.file_hash == second.stored.file_hash
    assert first.canonical_path == second.canonical_path
    # Only one file in the storage tree (sha256 dedupe).
    pdfs = list(storage_root.rglob("*.pdf"))
    assert len(pdfs) == 1


def test_fetch_to_storage_uses_company_id_when_no_symbol(monkeypatch, fake_storage):
    storage_root, runs_root, _ = fake_storage
    _patch_fetch(monkeypatch)

    company = CompanyTarget(
        company_id=99,
        company_name="ACME Pvt Ltd",
        nse_symbol=None,
        bse_code=None,
        investor_relations_url=None,
    )
    result = download_module.fetch_to_storage(
        url="https://example.com/report.pdf",
        company=company,
        period=_period(),
        document_type=DocumentType.CONCALL_TRANSCRIPT,
        asset_key="transcript",
    )
    assert result.mirror_path is not None
    assert result.mirror_path.parts[-3] == "company_99"
    assert result.mirror_path.name == "concall_transcript.pdf"


def test_fetch_to_storage_propagates_fetch_error(monkeypatch, fake_storage):
    def _boom(url: str):
        raise ingest_common.FetchError("HTTP 404")

    monkeypatch.setattr(ingest_common, "fetch_document_from_url", _boom)
    monkeypatch.setattr(download_module, "fetch_document_from_url", _boom)

    with pytest.raises(ingest_common.FetchError):
        download_module.fetch_to_storage(
            url="https://example.com/missing.pdf",
            company=_company(),
            period=_period(),
            document_type=DocumentType.INVESTOR_PRESENTATION,
            asset_key="presentation",
        )
