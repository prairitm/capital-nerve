"""Stage 1 of the pipeline: pages → `ExtractedValue` rows.

This is the only stage that talks to the LLM. Everything below it operates on
plain SQL rows, so the rest of the pipeline is provider-agnostic.

Determinism contract (introduced in 0005_extraction_cache):

- Every call computes a `request_hash` over the inputs that can change the
  LLM output: ``(file_hash, prompt_version, parser_version, provider.name,
  model, seed)``. The most recent COMPLETED job for the same document with
  the same hash is consulted; if its `raw_response` is present we *replay*
  the parse path instead of calling the LLM again.
- On a cache miss we call the provider, persist the canonical `raw_response`
  + `request_hash` + sampling settings + provider_used onto the job.
- Post-LLM, the items pass through `validators.run_validators` for source
  anchoring, unit canonicalisation, and totals math. The aggregated report
  is stored on `extraction_jobs.validator_report` for the Review Queue.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.enums import ConfidenceLevel, ExtractionStatus
from app.models.events import DocumentPage, ExtractionJob, SourceDocument
from app.models.facts import ExtractedValue, FinancialStatementFact, SegmentFact
from app.models.intelligence import CardEvidence
from app.models.review import ReviewQueue
from app.services.pipeline.llm import (
    PROMPT_VERSION,
    ExtractionResult,
    LLMProvider,
    ProviderPage,
    _finalize_quarter_items,
    _items_from_payload,
    parse_extraction_payload,
    select_extraction_model,
)
from app.services.pipeline.parsing import PARSER_VERSION
from app.services.pipeline.storage import get_storage
from app.services.pipeline.validators import run_validators

logger = logging.getLogger(__name__)


def run_extraction(
    db: Session,
    *,
    document: SourceDocument,
    job: ExtractionJob,
    provider: LLMProvider,
    model: str | None = None,
) -> ExtractionResult:
    """Call the LLM provider (or replay cached payload) and persist the structured output.

    ``model`` is the actual LLM model id used for this call (after the
    per-document-type fast-lane router has run in
    `runner.run_pipeline_for_document`). It is folded into the request-hash
    cache key so a doc that was previously extracted on Sonnet does not get a
    cache-hit replay when the active model is now Haiku, and vice-versa.
    Defaults to ``settings.LLM_MODEL`` for back-compat.
    """
    pages = _load_provider_pages(db, document.document_id)
    if not pages:
        result = ExtractionResult(items=[], model_name=provider.name, overall_confidence=0.0)
        result.notes.append("Document has no parsed pages — extraction skipped.")
        return result

    active_model = model or settings.LLM_MODEL

    job.status = ExtractionStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    job.model_name = provider.name
    job.prompt_version = PROMPT_VERSION
    job.parser_version = PARSER_VERSION
    db.flush()

    seed = int(getattr(settings, "LLM_SEED", 42))
    request_hash = _compute_request_hash(
        document=document,
        provider_name=provider.name,
        model=active_model,
        seed=seed,
    )

    cached_raw, cached_job_id = _lookup_cached_response(
        db, document_id=document.document_id, request_hash=request_hash, current_job_id=job.extraction_job_id
    )

    cache_hit = False
    if cached_raw:
        items, overall, notes = parse_extraction_payload(cached_raw)
        items = _finalize_quarter_items(
            items, pages=[(p.page_number, p.text or "") for p in pages]
        )
        result = ExtractionResult(
            items=items,
            model_name=provider.name,
            overall_confidence=overall,
            raw_response=cached_raw,
            notes=[*notes, f"Replayed from extraction_jobs.extraction_job_id={cached_job_id}."],
            temperature=0.0,
            seed=seed,
            provider_used=getattr(provider, "name", "unknown").split(":", 1)[0],
        )
        cache_hit = True
    else:
        result = provider.extract_financial_facts(
            pages=pages, document_title=document.document_title
        )

    # --- Validators ---
    page_text_pairs = [(p.page_number, p.text or "") for p in pages]
    validated_items, validator_report = run_validators(result.items, pages=page_text_pairs)
    result.items = validated_items
    if validator_report.has_failures and result.notes is not None:
        result.notes.append(
            "Validators flagged "
            f"{len(validator_report.source_text_dropped)} unanchored, "
            f"{len(validator_report.unit_dropped)} bad-unit, "
            f"{len(validator_report.totals_breaches)} totals breaches."
        )

    # --- Persistence: wipe + reinsert (idempotent re-runs) ---
    ev_ids = list(
        db.scalars(
            select(ExtractedValue.extracted_value_id).where(
                ExtractedValue.document_id == document.document_id
            )
        ).all()
    )
    if ev_ids:
        db.execute(
            update(FinancialStatementFact)
            .where(FinancialStatementFact.source_extracted_value_id.in_(ev_ids))
            .values(source_extracted_value_id=None)
        )
        db.execute(
            update(SegmentFact)
            .where(SegmentFact.source_extracted_value_id.in_(ev_ids))
            .values(source_extracted_value_id=None)
        )
        db.execute(
            update(CardEvidence)
            .where(CardEvidence.extracted_value_id.in_(ev_ids))
            .values(extracted_value_id=None)
        )
        db.execute(
            update(ReviewQueue)
            .where(ReviewQueue.extracted_value_id.in_(ev_ids))
            .values(extracted_value_id=None)
        )
    db.execute(
        delete(ExtractedValue).where(ExtractedValue.document_id == document.document_id)
    )

    for item in result.items:
        db.add(
            ExtractedValue(
                extraction_job_id=job.extraction_job_id,
                document_id=document.document_id,
                event_id=document.event_id,
                company_id=document.company_id,
                period_id=document.period_id,
                raw_label=item.raw_label,
                normalized_label=item.normalized_code,
                raw_value=str(item.value),
                numeric_value=item.value,
                unit=item.unit,
                page_number=item.page_number,
                source_text=item.source_text,
                confidence_score=item.confidence,
                confidence_level=_confidence_to_level(item.confidence),
                is_normalized=True,
            )
        )

    job.input_tokens = result.input_tokens
    job.output_tokens = result.output_tokens
    job.cost_usd = result.cost_usd
    job.request_hash = request_hash
    job.raw_response = result.raw_response
    job.llm_temperature = result.temperature
    job.llm_seed = result.seed
    job.provider_used = result.provider_used
    job.validator_report = validator_report.to_dict()
    job.meta = {
        **(job.meta or {}),
        "extracted_count": len(result.items),
        "overall_confidence": result.overall_confidence,
        "notes": result.notes,
        "cache_hit": cache_hit,
    }

    document.extraction_confidence = result.overall_confidence
    document.values_extracted = len(result.items)

    # Sessions use autoflush=False (see app/db/session.py). Make every stage
    # see the rows we just wrote without relying on the next query to flush.
    db.flush()

    return result


# ---------------------------------------------------------------------------
# Page loader + request-hash cache helpers
# ---------------------------------------------------------------------------


def _load_provider_pages(db: Session, document_id: int) -> list[ProviderPage]:
    rows = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number.asc())
        .all()
    )
    storage = get_storage()
    pages: list[ProviderPage] = []
    for r in rows:
        image_bytes: bytes | None = None
        if r.image_path:
            try:
                image_bytes = storage.open_bytes(r.image_path)
            except FileNotFoundError:
                logger.warning(
                    "image_path %s missing for page %s of document %s",
                    r.image_path,
                    r.page_number,
                    document_id,
                )
        pages.append(
            ProviderPage(
                page_number=r.page_number,
                text=r.page_text or "",
                image_bytes=image_bytes,
            )
        )
    return pages


def _compute_request_hash(
    *,
    document: SourceDocument,
    provider_name: str,
    model: str,
    seed: int,
) -> str:
    """Cache key for the structured-extraction request."""
    parts = [
        document.file_hash or f"doc:{document.document_id}",
        PROMPT_VERSION,
        PARSER_VERSION,
        provider_name,
        model,
        str(seed),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _lookup_cached_response(
    db: Session,
    *,
    document_id: int,
    request_hash: str,
    current_job_id: int,
) -> tuple[str | None, int | None]:
    """Most recent COMPLETED job for this document with a matching hash."""
    row = (
        db.query(ExtractionJob.extraction_job_id, ExtractionJob.raw_response)
        .filter(
            ExtractionJob.document_id == document_id,
            ExtractionJob.request_hash == request_hash,
            ExtractionJob.raw_response.isnot(None),
            ExtractionJob.extraction_job_id != current_job_id,
            ExtractionJob.status.in_(
                (
                    ExtractionStatus.COMPLETED,
                    ExtractionStatus.NEEDS_REVIEW,
                )
            ),
        )
        .order_by(ExtractionJob.extraction_job_id.desc())
        .first()
    )
    if not row:
        return None, None
    return row.raw_response, row.extraction_job_id


def _confidence_to_level(score: float) -> ConfidenceLevel:
    if score >= 85:
        return ConfidenceLevel.HIGH
    if score >= 65:
        return ConfidenceLevel.MEDIUM
    if score >= 40:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.NEEDS_REVIEW


# Re-export for backwards-compat / tests.
__all__ = ["run_extraction", "_items_from_payload"]
