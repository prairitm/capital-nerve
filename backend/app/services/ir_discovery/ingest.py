"""Per-pair end-to-end ingest: download -> tables -> pipeline.

`ingest_one(db, company, period, assets, ...)` mirrors the code path inside
`routers/ingest.py:ingest_upload` for each non-null asset on a
:class:`PeriodAssetSet`:

1. Download the URL via :func:`download.fetch_to_storage`.
2. Resolve the matching `FinancialPeriod` (creating it if missing).
3. Insert / reuse a `CompanyEvent` for that (company, period, event_type).
4. Insert / reuse a `SourceDocument` keyed by sha256 hash.
5. Queue an `ExtractionJob(status=PENDING)`.
6. Open a review row.
7. Unless `skip_pipeline=True`, call `run_pipeline_for_document` inline
   so the pipeline stages produce the canonical
   `extracted_values -> facts -> metrics -> signals -> cards` chain.

Each handled asset returns one :class:`AssetIngestResult`. A failure on
one asset does not stop the others — we keep going and surface the error
in `IngestOutcome.errors` so the CLI can render a partial-success report.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.enums import (
    AuditStatus,
    ConsolidationType,
    DocumentType,
    EventType,
    ExtractionStatus,
    PeriodType,
    SeverityLevel,
)
from app.models.events import CompanyEvent, ExtractionJob, SourceDocument
from app.models.review import ReviewQueue
from app.services.ingest_common import (
    FetchError,
    create_annual_period,
    create_period_from_quarter,
    standard_document_title,
)
from app.services.ir_discovery.download import DownloadResult, fetch_to_storage
from app.services.ir_discovery.schemas import (
    DOC_TYPE_BY_ASSET_KEY,
    AssetMatch,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)
from app.services.pipeline.runner import PipelineSummary, run_pipeline_for_document


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome shapes (consumed by the CLI and the JSONL run log)
# ---------------------------------------------------------------------------


@dataclass
class AssetIngestResult:
    """One row in the per-run JSONL log."""

    asset_key: str
    event_type: EventType
    document_type: DocumentType
    url: str
    status: str  # one of: "ingested", "duplicate", "skipped", "failed", "queued"
    event_id: Optional[int] = None
    document_id: Optional[int] = None
    job_id: Optional[int] = None
    review_id: Optional[int] = None
    file_hash: Optional[str] = None
    size_bytes: Optional[int] = None
    canonical_path: Optional[str] = None
    mirror_path: Optional[str] = None
    pipeline: Optional[dict] = None
    error: Optional[str] = None
    # Where this asset URL was discovered: "bse" | "nse" | "agent" | None.
    # Stamped by the bulk-ingest CLI based on which tier filled the slot.
    discovery_source: Optional[str] = None

    def to_jsonable(self) -> dict:
        return {
            "asset_key": self.asset_key,
            "event_type": self.event_type.value,
            "document_type": self.document_type.value,
            "url": self.url,
            "status": self.status,
            "event_id": self.event_id,
            "document_id": self.document_id,
            "job_id": self.job_id,
            "review_id": self.review_id,
            "file_hash": self.file_hash,
            "size_bytes": self.size_bytes,
            "canonical_path": self.canonical_path,
            "mirror_path": self.mirror_path,
            "pipeline": self.pipeline,
            "error": self.error,
            "discovery_source": self.discovery_source,
        }


@dataclass
class IngestOutcome:
    """Aggregate result for one (Company, PeriodSpec) pair."""

    company: CompanyTarget
    period: PeriodSpec
    assets: list[AssetIngestResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def successful(self) -> int:
        return sum(1 for a in self.assets if a.status in ("ingested", "queued"))

    @property
    def duplicates(self) -> int:
        return sum(1 for a in self.assets if a.status == "duplicate")

    @property
    def failures(self) -> int:
        return sum(1 for a in self.assets if a.status == "failed")

    def to_jsonable(self) -> dict:
        return {
            "company": {
                "company_id": self.company.company_id,
                "name": self.company.company_name,
                "nse_symbol": self.company.nse_symbol,
            },
            "period": {
                "display_label": self.period.display_label,
                "fy_year": self.period.fy_year,
                "quarter": self.period.quarter,
                "period_type": self.period.period_type.value,
            },
            "assets": [a.to_jsonable() for a in self.assets],
            "errors": list(self.errors),
            "summary": {
                "successful": self.successful,
                "duplicates": self.duplicates,
                "failures": self.failures,
            },
        }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def ingest_one(
    db: Session,
    *,
    company: CompanyTarget,
    period: PeriodSpec,
    assets: PeriodAssetSet,
    queued_by_user_id: int,
    asset_keys: tuple[str, ...] | None = None,
    skip_pipeline: bool = False,
    force_reextract: bool = False,
    discovery_source_by_key: dict[str, str] | None = None,
    fallback_by_asset_key: dict[str, list[tuple[AssetMatch, str]]] | None = None,
) -> IngestOutcome:
    """Persist + run-pipeline for every non-null asset on ``assets``.

    ``asset_keys`` lets the CLI restrict the asset types written (``--doc-types``).
    Defaults to all four keys defined on :data:`DOC_TYPE_BY_ASSET_KEY`.

    ``discovery_source_by_key`` (asset_key -> ``"bse" | "nse" | "agent"``)
    is stamped onto each :class:`AssetIngestResult` so the CLI's JSONL
    log records the tier that produced each URL.

    ``fallback_by_asset_key`` (asset_key -> list of ``(AssetMatch, source)``)
    is the tier-1 → tier-2 fallback chain. If the primary URL fails to
    download (e.g. BSE returns a 200 OK HTML wrapper instead of a real
    PDF), each fallback is tried in order and the successful one's
    source is recorded.

    ``force_reextract`` — when the same ``file_hash`` is seen again,
    still reset the document and run the pipeline even if it already
    completed. Defaults to False so repeat bulk-ingest runs do not spawn
    a second pipeline (which would race on ``document_pages``).
    """
    keys = asset_keys or tuple(DOC_TYPE_BY_ASSET_KEY.keys())
    outcome = IngestOutcome(company=company, period=period)
    sources = discovery_source_by_key or {}
    fallbacks = fallback_by_asset_key or {}

    for key in keys:
        if key not in DOC_TYPE_BY_ASSET_KEY:
            outcome.errors.append(f"Unknown asset_key: {key}")
            continue
        asset = _asset_field(assets, key)
        if asset is None or not asset.url:
            continue
        event_type, document_type = DOC_TYPE_BY_ASSET_KEY[key]
        result = _ingest_single_asset(
            db,
            company=company,
            period=period,
            asset_key=key,
            asset=asset,
            event_type=event_type,
            document_type=document_type,
            queued_by_user_id=queued_by_user_id,
            skip_pipeline=skip_pipeline,
            discovery_source=sources.get(key),
            fallbacks=fallbacks.get(key, []),
            force_reextract=force_reextract,
        )
        outcome.assets.append(result)
    return outcome


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _asset_field(assets: PeriodAssetSet, key: str) -> Optional[AssetMatch]:
    return getattr(assets, key, None)


def _ingest_single_asset(
    db: Session,
    *,
    company: CompanyTarget,
    period: PeriodSpec,
    asset_key: str,
    asset: AssetMatch,
    event_type: EventType,
    document_type: DocumentType,
    queued_by_user_id: int,
    skip_pipeline: bool,
    force_reextract: bool = False,
    discovery_source: Optional[str] = None,
    fallbacks: list[tuple[AssetMatch, str]] | None = None,
) -> AssetIngestResult:
    """Run the full intake for one asset, returning a never-throwing result row.

    Tries ``asset`` first (with ``discovery_source`` as the recorded
    source); on :class:`FetchError` it walks ``fallbacks`` in order and
    keeps the first one that downloads. The successful candidate's
    source replaces ``discovery_source`` in the returned result so the
    JSONL log accurately reflects which tier produced the URL we
    actually used.
    """
    result = AssetIngestResult(
        asset_key=asset_key,
        event_type=event_type,
        document_type=document_type,
        url=asset.url,
        status="failed",
        discovery_source=discovery_source,
    )

    # Annual report only makes sense on annual periods; reject any drift.
    if event_type == EventType.ANNUAL_REPORT and not period.is_annual:
        result.status = "skipped"
        result.error = "annual_report asset on a quarterly period — skipped"
        return result
    if event_type != EventType.ANNUAL_REPORT and period.is_annual:
        result.status = "skipped"
        result.error = (
            f"{event_type.value} asset on an annual period — skipped "
            "(use a quarterly period for this asset type)"
        )
        return result

    # ---- 1. Download (primary, then fallbacks on FetchError) ----
    candidates: list[tuple[AssetMatch, Optional[str]]] = [
        (asset, discovery_source),
        *((alt, src) for alt, src in (fallbacks or [])),
    ]
    download: Optional[DownloadResult] = None
    chosen_asset: AssetMatch = asset
    chosen_source: Optional[str] = discovery_source
    last_error: Optional[str] = None
    for candidate, candidate_source in candidates:
        try:
            download = fetch_to_storage(
                url=candidate.url,
                company=company,
                period=period,
                document_type=document_type,
                asset_key=asset_key,
            )
        except FetchError as exc:
            last_error = f"download failed: {exc}"
            logger.info(
                "Primary/fallback download failed for %s / %s / %s (source=%s, url=%s): %s",
                company.nse_symbol,
                period.display_label,
                asset_key,
                candidate_source,
                candidate.url,
                exc,
            )
            continue
        except Exception as exc:  # belt-and-braces — never let one URL kill the loop
            logger.exception(
                "Unexpected download error for %s / %s / %s (source=%s)",
                company.nse_symbol,
                period.display_label,
                asset_key,
                candidate_source,
            )
            last_error = f"download crashed: {exc}"
            continue

        chosen_asset = candidate
        chosen_source = candidate_source
        break

    if download is None:
        # Every candidate failed; keep the original primary URL on the
        # result so the JSONL stays auditable, but record the latest
        # error message.
        result.error = last_error or "download failed: no usable candidates"
        return result

    # Keep the result faithful to the URL we actually downloaded.
    result.url = chosen_asset.url
    result.discovery_source = chosen_source
    asset = chosen_asset

    result.file_hash = download.stored.file_hash
    result.size_bytes = download.stored.size_bytes
    result.canonical_path = download.stored.storage_path
    if download.mirror_path is not None:
        result.mirror_path = str(download.mirror_path)

    # ---- 2. Resolve / create FinancialPeriod ----
    try:
        period_id = _ensure_period(db, period)
    except Exception as exc:
        db.rollback()
        result.error = f"period resolution failed: {exc}"
        return result

    # ---- 3. Get-or-create CompanyEvent ----
    event = _get_or_create_event(
        db,
        company_id=company.company_id,
        period_id=period_id,
        event_type=event_type,
        title=_event_title(company, period, document_type),
        event_date=_event_date(period),
        source_url=asset.source_page,
    )

    # ---- 4. Get-or-create SourceDocument ----
    def _bind_existing_doc(existing: SourceDocument) -> None:
        nonlocal doc, was_duplicate, already_extracted
        prior_status = existing.extraction_status
        prior_page_count = existing.page_count or 0
        existing.event_id = event.event_id
        existing.company_id = company.company_id
        existing.period_id = period_id
        existing.document_type = document_type
        existing.document_title = _document_title(company, period, document_type)
        existing.source_url = asset.url
        doc = existing
        was_duplicate = True
        already_extracted = (
            not force_reextract
            and prior_status == ExtractionStatus.COMPLETED
            and prior_page_count > 0
        )

    existing_doc = db.scalar(
        select(SourceDocument).where(
            SourceDocument.file_hash == download.stored.file_hash
        )
    )
    doc: SourceDocument
    was_duplicate = False
    already_extracted = False
    if existing_doc is not None:
        _bind_existing_doc(existing_doc)
        if already_extracted:
            # File is unchanged and the pipeline already succeeded — do not
            # reset to PENDING or spawn another job (which would race the
            # in-process worker on document_pages).
            db.commit()
            latest_job = db.scalar(
                select(ExtractionJob)
                .where(ExtractionJob.document_id == doc.document_id)
                .order_by(ExtractionJob.extraction_job_id.desc())
            )
            if latest_job is not None:
                result.job_id = latest_job.extraction_job_id
                result.pipeline = _pipeline_summary_from_job_meta(latest_job, doc)
            result.status = "duplicate"
            return result
        existing_doc.extraction_status = ExtractionStatus.PENDING
    else:
        doc = SourceDocument(
            event_id=event.event_id,
            company_id=company.company_id,
            period_id=period_id,
            document_type=document_type,
            document_title=_document_title(company, period, document_type),
            source_url=asset.url,
            storage_path=download.stored.storage_path,
            file_hash=download.stored.file_hash,
            extraction_status=ExtractionStatus.PENDING,
            meta={
                "content_type": download.content_type,
                "original_filename": download.filename,
                "size_bytes": download.stored.size_bytes,
                "ir_discovery": {
                    "source_page": asset.source_page,
                    "asset_key": asset_key,
                    "agent_title": asset.title,
                    "discovery_source": chosen_source,
                    "mirror_path": str(download.mirror_path)
                    if download.mirror_path
                    else None,
                },
            },
        )
        db.add(doc)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            # Concurrent bulk-ingest workers can race on the same PDF hash
            # (e.g. NSE mapped one press release to multiple quarters).
            db.expunge(doc)
            raced_doc = db.scalar(
                select(SourceDocument).where(
                    SourceDocument.file_hash == download.stored.file_hash
                )
            )
            if raced_doc is None:
                raise
            _bind_existing_doc(raced_doc)
            if already_extracted:
                db.commit()
                latest_job = db.scalar(
                    select(ExtractionJob)
                    .where(ExtractionJob.document_id == doc.document_id)
                    .order_by(ExtractionJob.extraction_job_id.desc())
                )
                if latest_job is not None:
                    result.job_id = latest_job.extraction_job_id
                    result.pipeline = _pipeline_summary_from_job_meta(latest_job, doc)
                result.status = "duplicate"
                return result
            doc.extraction_status = ExtractionStatus.PENDING
        else:
            was_duplicate = False

    result.event_id = event.event_id
    result.document_id = doc.document_id

    # ---- 5. Queue ExtractionJob ----
    # Mark PROCESSING before commit when we run inline so the in-process
    # worker (WORKER_INPROCESS) does not claim the same PENDING row.
    run_inline_pipeline = not skip_pipeline
    now = datetime.now(timezone.utc)
    job = ExtractionJob(
        document_id=doc.document_id,
        company_id=company.company_id,
        job_type="document_extraction",
        status=(
            ExtractionStatus.PROCESSING
            if run_inline_pipeline
            else ExtractionStatus.PENDING
        ),
        started_at=now if run_inline_pipeline else None,
        meta={
            "queued_by_user_id": queued_by_user_id,
            "ir_discovery": {
                "asset_key": asset_key,
                "period_label": period.display_label,
            },
        },
    )
    db.add(job)
    db.flush()
    result.job_id = job.extraction_job_id

    # ---- 6. Review row ----
    review = _enqueue_review(
        db, company_id=company.company_id, event=event, document=doc
    )
    result.review_id = review.review_id

    # Commit so the pipeline can see the job in its own session if it opens one.
    db.commit()

    if skip_pipeline:
        result.status = "queued" if not was_duplicate else "duplicate"
        return result

    # ---- 7. Run the same pipeline POST /ingest/upload would queue ----
    try:
        summary = run_pipeline_for_document(db, job_id=job.extraction_job_id)
        result.pipeline = _pipeline_summary_to_dict(summary)
        result.status = "duplicate" if was_duplicate else "ingested"
    except Exception as exc:
        logger.exception(
            "Pipeline run failed for job %s (%s / %s / %s)",
            job.extraction_job_id,
            company.nse_symbol,
            period.display_label,
            asset_key,
        )
        result.status = "failed"
        result.error = f"pipeline failed: {exc}"
    return result


def _ensure_period(db: Session, period: PeriodSpec) -> int:
    if period.period_type == PeriodType.ANNUAL:
        return create_annual_period(db, fy_year=period.fy_year)
    if period.period_type == PeriodType.QUARTERLY and period.quarter is not None:
        return create_period_from_quarter(
            db, fy_year=period.fy_year, quarter=period.quarter
        )
    raise ValueError(
        f"Unsupported period_type {period.period_type} for {period.display_label}"
    )


def _get_or_create_event(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    event_type: EventType,
    title: str,
    event_date: date,
    source_url: Optional[str],
) -> CompanyEvent:
    """Reuse an existing draft event for the same (company, period, type) tuple.

    Mirrors the implicit semantics of the upload endpoint: each
    (company, period, event_type) triple should have at most one draft
    event during ingestion.
    """
    existing = db.scalar(
        select(CompanyEvent).where(
            CompanyEvent.company_id == company_id,
            CompanyEvent.period_id == period_id,
            CompanyEvent.event_type == event_type,
        )
    )
    if existing is not None:
        if not existing.source_url and source_url:
            existing.source_url = source_url
        return existing
    event = CompanyEvent(
        company_id=company_id,
        period_id=period_id,
        event_type=event_type,
        event_title=title,
        event_date=event_date,
        filing_date=datetime.now(timezone.utc),
        consolidation=ConsolidationType.CONSOLIDATED,
        audit_status=AuditStatus.UNKNOWN,
        is_published=False,
        source_url=source_url,
    )
    db.add(event)
    db.flush()
    return event


def _enqueue_review(
    db: Session,
    *,
    company_id: int,
    event: CompanyEvent,
    document: SourceDocument,
) -> ReviewQueue:
    review = ReviewQueue(
        company_id=company_id,
        event_id=event.event_id,
        document_id=document.document_id,
        review_type="new_document_ingested",
        priority=SeverityLevel.MEDIUM,
        issue_description=(
            f"New {document.document_type.value} awaiting extraction "
            "(bulk_ingest)."
        ),
        status="OPEN",
    )
    db.add(review)
    db.flush()
    return review


def _event_title(
    company: CompanyTarget, period: PeriodSpec, document_type: DocumentType
) -> str:
    return standard_document_title(
        symbol=company.nse_symbol or company.bse_code,
        display_label=period.display_label,
        document_type=document_type,
    )


def _document_title(
    company: CompanyTarget, period: PeriodSpec, document_type: DocumentType
) -> str:
    return _event_title(company, period, document_type)


def _event_date(period: PeriodSpec) -> date:
    """Use the last day of the period as a placeholder filing-style date."""
    return period.period_end


def _pipeline_summary_from_job_meta(
    job: ExtractionJob, document: SourceDocument
) -> dict | None:
    """Best-effort pipeline snapshot from a prior completed job."""
    stages = (job.meta or {}).get("stages") or {}
    if not stages and job.status != ExtractionStatus.COMPLETED:
        return None
    return {
        "job_id": job.extraction_job_id,
        "document_id": document.document_id,
        "status": job.status.value,
        "pages": stages.get("pages", document.page_count or 0),
        "extracted_values": stages.get("extracted", 0),
        "facts": stages.get("facts", 0),
        "metrics": stages.get("metrics", 0),
        "signals": stages.get("signals", 0),
        "cards": stages.get("cards", 0),
        "published": bool((job.meta or {}).get("published")),
        "confidence": float(document.extraction_confidence or 0),
        "error": job.error_message,
    }


def _pipeline_summary_to_dict(summary: PipelineSummary) -> dict:
    return {
        "job_id": summary.job_id,
        "document_id": summary.document_id,
        "status": summary.status.value,
        "pages": summary.pages,
        "extracted_values": summary.extracted_values,
        "facts": summary.facts,
        "metrics": summary.metrics,
        "signals": summary.signals,
        "cards": summary.cards,
        "published": summary.published,
        "confidence": summary.confidence,
        "error": summary.error,
    }


__all__ = [
    "AssetIngestResult",
    "IngestOutcome",
    "ingest_one",
]
