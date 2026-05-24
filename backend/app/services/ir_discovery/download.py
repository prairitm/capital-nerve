"""Download an asset URL into the canonical sha256 store + a human mirror.

Canonical path: ``var/storage/aa/bb/<sha256>.pdf`` (sha256 content addressed,
managed by `services.pipeline.storage.LocalStorage`).

Human mirror: ``var/ingest_runs/<symbol>/<period_slug>/<SYMBOL>_<period_slug>_<document_type>.pdf``
— a parallel, browsable layout that lets the operator inspect what was
ingested per (company, period) without having to query the DB. The mirror
is best-effort; failures to write it are logged and do not abort the
ingest.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.db.enums import DocumentType
from app.services.ingest_common import (
    FetchError,
    fetch_document_from_url,
    standard_document_basename,
    suffix_for,
)
from app.services.ir_discovery.schemas import CompanyTarget, PeriodSpec
from app.services.pipeline.storage import LocalStorage, StoredFile, get_storage


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of one URL download."""

    stored: StoredFile
    canonical_path: Path  # absolute path under STORAGE_DIR
    mirror_path: Optional[Path]  # absolute path under IR_AGENT_RUNS_DIR (best effort)
    filename: Optional[str]
    content_type: Optional[str]


def fetch_to_storage(
    *,
    url: str,
    company: CompanyTarget,
    period: PeriodSpec,
    document_type: DocumentType,
    asset_key: str | None = None,
    storage: LocalStorage | None = None,
) -> DownloadResult:
    """Download ``url``, write canonical + human-mirror copies, return both paths.

    Raises :class:`app.services.ingest_common.FetchError` if the URL can't
    be downloaded or sniffed as a PDF / text document.
    """
    data, filename, content_type = fetch_document_from_url(url)
    suffix = suffix_for(filename, content_type)

    storage = storage or get_storage()
    stored = storage.put_bytes(data, suffix=suffix)
    canonical_path = (storage.root / stored.storage_path).resolve()

    mirror_path = _write_human_mirror(
        canonical_path=canonical_path,
        company=company,
        period=period,
        document_type=document_type,
        suffix=suffix,
    )

    logger.info(
        "Downloaded %s for %s / %s: %s bytes -> %s%s",
        asset_key or document_type.value,
        company.nse_symbol or company.company_name,
        period.display_label,
        stored.size_bytes,
        stored.storage_path,
        f" (mirror={mirror_path})" if mirror_path else "",
    )
    return DownloadResult(
        stored=stored,
        canonical_path=canonical_path,
        mirror_path=mirror_path,
        filename=filename,
        content_type=content_type,
    )


# ---------------------------------------------------------------------------
# Human-browsable mirror
# ---------------------------------------------------------------------------


_FILESAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    """Filesystem-safe slug. Preserves dots so suffixes still work."""
    cleaned = _FILESAFE_RE.sub("_", value.strip())
    return cleaned.strip("._") or "unknown"


def _mirror_root() -> Path:
    return settings.ir_agent_runs_path


def _company_segment(company: CompanyTarget) -> str:
    return _slug(company.nse_symbol or company.bse_code or f"company_{company.company_id}")


def _write_human_mirror(
    *,
    canonical_path: Path,
    company: CompanyTarget,
    period: PeriodSpec,
    document_type: DocumentType,
    suffix: str,
) -> Optional[Path]:
    """Copy the canonical file to the human-readable mirror layout.

    Returns the absolute mirror path on success, ``None`` if the copy
    fails (we never abort an ingest because of mirror issues — the
    canonical sha256 store is the source of truth).
    """
    try:
        period_slug = period.slug
        target_dir = _mirror_root() / _company_segment(company) / period_slug
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = standard_document_basename(
            symbol=company.nse_symbol or company.bse_code,
            period_slug=period_slug,
            document_type=document_type,
        )
        target = target_dir / f"{stem}{suffix}"
        if target.exists() and target.stat().st_size == canonical_path.stat().st_size:
            return target
        shutil.copyfile(canonical_path, target)
        return target
    except OSError as exc:
        logger.warning(
            "Failed to write human mirror for %s / %s / %s: %s",
            company.nse_symbol or company.company_name,
            period.display_label,
            document_type.value,
            exc,
        )
        return None


__all__ = ["DownloadResult", "fetch_to_storage", "FetchError"]
