from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_admin, get_db
from app.models.events import CompanyEvent, ExtractionJob, SourceDocument
from app.models.facts import ExtractedValue, FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import (
    CalculatedMetric,
    GeneratedSignal,
    IntelligenceCard,
    MetricDefinition,
    SignalDefinition,
)
from app.models.master import Company, FinancialPeriod
from app.models.review import ReviewQueue
from app.models.user import AppUser
from app.services.pipeline import signals as signals_stage

router = APIRouter(prefix="/review", tags=["review"])


class UpdateReview(BaseModel):
    status: str | None = None
    issue_description: str | None = None


@router.get("")
def list_review(
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(ReviewQueue, Company, SourceDocument)
        .join(Company, Company.company_id == ReviewQueue.company_id, isouter=True)
        .join(SourceDocument, SourceDocument.document_id == ReviewQueue.document_id, isouter=True)
    )
    if status_filter:
        stmt = stmt.where(ReviewQueue.status == status_filter)
    stmt = stmt.order_by(ReviewQueue.created_at.desc()).limit(100)
    rows = db.execute(stmt).all()
    doc_ids = [r.document_id for (r, _, _) in rows if r.document_id]
    jobs_by_doc = _latest_jobs_by_document(db, doc_ids)
    return [
        _serialize_review_row(db, r, c, d, jobs_by_doc.get(r.document_id))
        for (r, c, d) in rows
    ]


def _latest_jobs_by_document(db: Session, doc_ids: list[int]) -> dict[int, ExtractionJob]:
    if not doc_ids:
        return {}
    latest_id = (
        select(
            ExtractionJob.document_id,
            func.max(ExtractionJob.extraction_job_id).label("job_id"),
        )
        .where(ExtractionJob.document_id.in_(doc_ids))
        .group_by(ExtractionJob.document_id)
        .subquery()
    )
    jobs = (
        db.execute(
            select(ExtractionJob).join(
                latest_id,
                (ExtractionJob.document_id == latest_id.c.document_id)
                & (ExtractionJob.extraction_job_id == latest_id.c.job_id),
            )
        )
        .scalars()
        .all()
    )
    return {j.document_id: j for j in jobs}


def _serialize_review_row(
    db: Session,
    r: ReviewQueue,
    c: Company | None,
    d: SourceDocument | None,
    job: ExtractionJob | None,
) -> dict[str, Any]:
    stages = (job.meta or {}).get("stages", {}) if job else {}
    signal_diag: dict[str, Any] | None = (job.meta or {}).get("signal_diagnostics") if job else None
    if signal_diag is None and d is not None:
        signal_diag = signals_stage.diagnostics_to_dict(
            signals_stage.evaluate_signal_rules(db, document=d)["diagnostics"]
        )

    confidence = float(d.extraction_confidence) if d and d.extraction_confidence is not None else None
    threshold = float(
        (job.meta or {}).get("auto_publish_threshold", settings.AUTO_PUBLISH_CONFIDENCE)
        if job
        else settings.AUTO_PUBLISH_CONFIDENCE
    )
    published = bool((job.meta or {}).get("published")) if job else False
    cards_count = int(stages.get("cards", d.cards_generated if d and d.cards_generated else 0))

    return {
        "review_id": r.review_id,
        "review_type": r.review_type,
        "priority": r.priority.value,
        "status": r.status,
        "issue_description": r.issue_description,
        "created_at": r.created_at.isoformat(),
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "company_id": r.company_id,
        "company_name": c.company_name if c else None,
        "company_symbol": (c.nse_symbol or c.bse_code) if c else None,
        "document_id": r.document_id,
        "document_title": d.document_title if d else None,
        "document_type": d.document_type.value if d else None,
        "extraction_status": d.extraction_status.value if d else None,
        "extraction_confidence": confidence,
        "event_id": r.event_id,
        "pipeline_stages": stages,
        "cards_generated": cards_count,
        "job_status": job.status.value if job else None,
        "job_error": job.error_message if job else None,
        "auto_publish_threshold": threshold,
        "auto_published": published,
        "publish_blocked_reasons": _publish_blocked_reasons(
            confidence=confidence,
            threshold=threshold,
            published=published,
            job=job,
            signal_diag=signal_diag,
            cards_count=cards_count,
        ),
        "signal_diagnostics": signal_diag,
    }


def _publish_blocked_reasons(
    *,
    confidence: float | None,
    threshold: float,
    published: bool,
    job: ExtractionJob | None,
    signal_diag: dict[str, Any] | None,
    cards_count: int,
) -> list[str]:
    if published:
        return []
    reasons: list[str] = []
    if job and job.error_message:
        reasons.append(f"Pipeline failed: {job.error_message}")
    if confidence is not None and confidence < threshold:
        reasons.append(
            f"Extraction confidence {confidence:.0f}% is below auto-publish threshold ({threshold:.0f}%)"
        )
    if job:
        stages = (job.meta or {}).get("stages") or {}
        if int(stages.get("facts") or 0) == 0:
            reasons.append(
                "No financial statement facts were normalized for this period"
            )
    if signal_diag:
        blockers = signal_diag.get("blockers") or []
        if "no_period" in blockers:
            reasons.append("Document has no financial period — metrics and signals were skipped")
        elif "no_metrics" in blockers:
            reasons.append("No calculated metrics for this period — signal rules could not run")
        fired = int(signal_diag.get("fired_count") or 0)
        evaluable = int(signal_diag.get("rules_evaluable") or 0)
        if not blockers and fired == 0 and evaluable > 0:
            reasons.append(
                f"0 of {evaluable} metric rules fired — thresholds not breached"
            )
        non_eval = int(signal_diag.get("rules_non_evaluable") or 0)
        if non_eval:
            reasons.append(
                f"{non_eval} signal(s) need concall/auditor extraction (not metric rules)"
            )
    if cards_count == 0 and not reasons:
        reasons.append("No intelligence cards were generated")
    if not reasons:
        reasons.append("Awaiting admin approval")
    return reasons


@router.get("/{review_id}/pipeline")
def get_review_pipeline(
    review_id: int,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> dict[str, Any]:
    """Full ingestion pipeline artifacts for one review row (admin drill-down)."""
    item = db.get(ReviewQueue, review_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return _pipeline_detail_for_review(db, item)


@router.patch("/{review_id}")
def update_review(
    review_id: int,
    body: UpdateReview,
    db: Session = Depends(get_db),
    admin: AppUser = Depends(get_current_admin),
) -> dict[str, Any]:
    item = db.get(ReviewQueue, review_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    if body.status:
        item.status = body.status
        if body.status in {"APPROVED", "REJECTED", "CORRECTED", "RESOLVED"}:
            item.resolved_at = datetime.now(timezone.utc)
        # APPROVED on an ingested document means: "extraction looks right —
        # publish the cards/signals/event so the rest of the app can show them".
        if body.status == "APPROVED":
            _publish_ingestion_artifacts(db, review=item)
            _sync_job_publish_meta(db, review=item, published=True)
        # REJECTED un-publishes the whole pipeline output so a partial mis-read
        # never leaks into the feed — including rows that were auto-published.
        elif body.status == "REJECTED":
            _retract_ingestion_artifacts(db, review=item)
            _sync_job_publish_meta(db, review=item, published=False)
    if body.issue_description is not None:
        item.issue_description = body.issue_description
    db.commit()
    db.refresh(item)
    return {"review_id": item.review_id, "status": item.status}


def _publish_ingestion_artifacts(db: Session, *, review: ReviewQueue) -> None:
    """Flip `is_published=True` on the event + signals + cards belonging to
    this review's document. Matches what the pipeline runner does on
    high-confidence auto-publish so the admin "approve" gives identical state.
    """
    if review.event_id:
        db.execute(
            update(CompanyEvent)
            .where(CompanyEvent.event_id == review.event_id)
            .values(is_published=True)
        )
    if review.document_id:
        db.execute(
            update(GeneratedSignal)
            .where(GeneratedSignal.document_id == review.document_id)
            .values(is_published=True)
        )
        db.execute(
            update(IntelligenceCard)
            .where(IntelligenceCard.document_id == review.document_id)
            .values(is_published=True)
        )


def _pipeline_detail_for_review(db: Session, review: ReviewQueue) -> dict[str, Any]:
    doc_id = review.document_id
    job: ExtractionJob | None = None
    if doc_id:
        job = db.scalar(
            select(ExtractionJob)
            .where(ExtractionJob.document_id == doc_id)
            .order_by(ExtractionJob.extraction_job_id.desc())
            .limit(1)
        )

    period: FinancialPeriod | None = None
    document: SourceDocument | None = None
    if doc_id:
        document = db.get(SourceDocument, doc_id)
        if document and document.period_id:
            period = db.get(FinancialPeriod, document.period_id)

    meta = (job.meta or {}) if job else {}
    signal_diag: dict[str, Any] | None = meta.get("signal_diagnostics")
    if signal_diag is None and document is not None:
        signal_diag = signals_stage.diagnostics_to_dict(
            signals_stage.evaluate_signal_rules(db, document=document)["diagnostics"]
        )

    extracted: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []

    if doc_id:
        for ev in db.scalars(
            select(ExtractedValue)
            .where(ExtractedValue.document_id == doc_id)
            .order_by(ExtractedValue.normalized_label.nulls_last(), ExtractedValue.raw_label)
        ).all():
            label = ev.normalized_label or ev.raw_label
            value = float(ev.numeric_value) if ev.numeric_value is not None else ev.raw_value
            extracted.append(
                {
                    "extracted_value_id": ev.extracted_value_id,
                    "label": label,
                    "raw_label": ev.raw_label,
                    "normalized_label": ev.normalized_label,
                    "value": value,
                    "unit": ev.unit,
                    "page_number": ev.page_number,
                    "confidence_score": float(ev.confidence_score)
                    if ev.confidence_score is not None
                    else None,
                    "statement_type": ev.statement_type.value if ev.statement_type else None,
                }
            )

        fact_rows = db.execute(
            select(FinancialStatementFact, FinancialLineItemDefinition)
            .join(
                FinancialLineItemDefinition,
                FinancialLineItemDefinition.line_item_def_id
                == FinancialStatementFact.line_item_def_id,
            )
            .where(FinancialStatementFact.document_id == doc_id)
            .order_by(
                FinancialLineItemDefinition.normalized_code,
                FinancialStatementFact.period_value_type,
            )
        ).all()
        for fact, line_def in fact_rows:
            facts.append(
                {
                    "fact_id": fact.fact_id,
                    "normalized_code": line_def.normalized_code,
                    "display_name": line_def.display_name,
                    "value": float(fact.value),
                    "unit": fact.unit,
                    "period_value_type": fact.period_value_type,
                    "consolidation": fact.consolidation.value,
                    "confidence_score": float(fact.confidence_score)
                    if fact.confidence_score is not None
                    else None,
                }
            )

    period_id = period.period_id if period else None
    if period_id:
        metric_rows = db.execute(
            select(CalculatedMetric, MetricDefinition)
            .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
            .where(CalculatedMetric.period_id == period_id)
            .order_by(MetricDefinition.metric_code)
        ).all()
        for cm, md in metric_rows:
            metrics.append(
                {
                    "metric_id": cm.metric_id,
                    "metric_code": md.metric_code,
                    "metric_name": md.metric_name,
                    "metric_value": float(cm.metric_value) if cm.metric_value is not None else None,
                    "unit": cm.unit or md.unit,
                    "comparison_type": cm.comparison_type,
                    "change_percent": float(cm.change_percent) if cm.change_percent is not None else None,
                    "change_absolute": float(cm.change_absolute) if cm.change_absolute is not None else None,
                    "confidence_score": float(cm.confidence_score)
                    if cm.confidence_score is not None
                    else None,
                }
            )

    if doc_id:
        signal_rows = db.execute(
            select(GeneratedSignal, SignalDefinition)
            .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
            .where(GeneratedSignal.document_id == doc_id)
            .order_by(SignalDefinition.signal_code)
        ).all()
        for sig, sig_def in signal_rows:
            signals.append(
                {
                    "signal_id": sig.signal_id,
                    "signal_code": sig_def.signal_code,
                    "signal_name": sig_def.signal_name,
                    "signal_direction": sig.signal_direction.value,
                    "severity": sig.severity.value,
                    "headline": sig.headline,
                    "is_published": sig.is_published,
                    "confidence_score": float(sig.confidence_score)
                    if sig.confidence_score is not None
                    else None,
                }
            )

        for card in db.scalars(
            select(IntelligenceCard)
            .where(IntelligenceCard.document_id == doc_id)
            .order_by(IntelligenceCard.card_priority.desc(), IntelligenceCard.card_id)
        ).all():
            cards.append(
                {
                    "card_id": card.card_id,
                    "card_type": card.card_type,
                    "headline": card.headline,
                    "one_line_summary": card.one_line_summary,
                    "signal_direction": card.signal_direction.value if card.signal_direction else None,
                    "severity": card.severity.value if card.severity else None,
                    "is_published": card.is_published,
                    "card_priority": float(card.card_priority),
                }
            )

    return {
        "review_id": review.review_id,
        "document_id": doc_id,
        "event_id": review.event_id,
        "period": {
            "period_id": period.period_id,
            "display_label": period.display_label,
            "fy_label": period.fy_label,
            "quarter": period.quarter,
            "period_start_date": period.period_start_date.isoformat(),
            "period_end_date": period.period_end_date.isoformat(),
        }
        if period
        else None,
        "job": {
            "job_id": job.extraction_job_id,
            "status": job.status.value,
            "model_name": job.model_name,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "input_tokens": job.input_tokens,
            "output_tokens": job.output_tokens,
            "cost_usd": float(job.cost_usd) if job.cost_usd is not None else None,
            "error_message": job.error_message,
            "stages": meta.get("stages") or {},
            "auto_published": bool(meta.get("published")),
            "auto_publish_threshold": float(
                meta.get("auto_publish_threshold", settings.AUTO_PUBLISH_CONFIDENCE)
            ),
        }
        if job
        else None,
        "extraction_confidence": float(document.extraction_confidence)
        if document and document.extraction_confidence is not None
        else None,
        "extracted_values": extracted,
        "facts": facts,
        "metrics": metrics,
        "signals": signals,
        "cards": cards,
        "signal_diagnostics": signal_diag,
    }


def _sync_job_publish_meta(db: Session, *, review: ReviewQueue, published: bool) -> None:
    """Keep `ExtractionJob.meta['published']` aligned after admin approve/reject."""
    if not review.document_id:
        return
    job = db.scalar(
        select(ExtractionJob)
        .where(ExtractionJob.document_id == review.document_id)
        .order_by(ExtractionJob.extraction_job_id.desc())
        .limit(1)
    )
    if not job:
        return
    meta = dict(job.meta or {})
    meta["published"] = published
    job.meta = meta


def _retract_ingestion_artifacts(db: Session, *, review: ReviewQueue) -> None:
    """Mirror of `_publish_*` for the REJECTED case."""
    if review.event_id:
        db.execute(
            update(CompanyEvent)
            .where(CompanyEvent.event_id == review.event_id)
            .values(is_published=False)
        )
    if review.document_id:
        db.execute(
            update(GeneratedSignal)
            .where(GeneratedSignal.document_id == review.document_id)
            .values(is_published=False)
        )
        db.execute(
            update(IntelligenceCard)
            .where(IntelligenceCard.document_id == review.document_id)
            .values(is_published=False)
        )
