"""Orchestrator for the ingestion pipeline.

Given an `ExtractionJob.extraction_job_id`, walks the full chain:

    storage bytes → parse → extract → normalize → metrics → signals → cards

Every stage records bookkeeping on `ExtractionJob` so the admin review queue
can show progress, the user can see what model produced the data, and any
failure mode lands in `error_message` instead of the worker silently crashing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.enums import ExtractionStatus, SignalDirection
from app.models.events import CompanyEvent, ExtractionJob, SourceDocument
from app.models.intelligence import CalculatedMetric, MetricDefinition
from app.models.review import ReviewQueue
from app.services.pipeline import cards as cards_stage
from app.services.pipeline import concall as concall_stage
from app.services.pipeline import extraction as extraction_stage
from app.services.pipeline import guidance as guidance_stage
from app.services.pipeline import indexing as indexing_stage
from app.services.pipeline import metrics as metrics_stage
from app.services.pipeline import metric_validation as metric_validation_stage
from app.services.pipeline import normalization as normalization_stage
from app.services.pipeline import announcement as announcement_stage
from app.services.pipeline import orderbook as orderbook_stage
from app.services.pipeline import parsing as parsing_stage
from app.services.pipeline import presentation as presentation_stage
from app.services.pipeline import segment as segment_stage
from app.services.pipeline import shareholding as shareholding_stage
from app.services.pipeline import signals as signals_stage
from app.services.pipeline.llm import get_provider, select_extraction_model
from app.services.pipeline.storage import get_storage
from app.services.event_summary import build_event_summary_text, pick_main_issue, pick_watch_next

logger = logging.getLogger(__name__)


@dataclass
class PipelineSummary:
    job_id: int
    document_id: int
    status: ExtractionStatus
    pages: int
    extracted_values: int
    facts: int
    metrics: int
    signals: int
    cards: int
    published: bool
    confidence: float
    error: str | None = None
    notes: list[str] | None = None


def run_pipeline_for_document(db: Session, *, job_id: int) -> PipelineSummary:
    """Entry point used by the worker and by the admin "re-run" action.

    Wraps each stage in a single transaction. On exception we roll back, mark
    the job FAILED, and surface the error in the review queue.
    """
    job = db.get(ExtractionJob, job_id)
    if not job:
        raise ValueError(f"ExtractionJob {job_id} not found")

    document = db.get(SourceDocument, job.document_id)
    event = db.get(CompanyEvent, document.event_id) if document and document.event_id else None
    if not document or not event:
        _fail(db, job, "Document or event missing for job")
        return _summary_from(job, document, status=ExtractionStatus.FAILED)

    # Only one pipeline run per document at a time. bulk_ingest runs the
    # pipeline inline while the dev worker also polls PENDING jobs — without
    # this lock both can call persist_pages concurrently and trip
    # uq_document_pages.
    _acquire_document_pipeline_lock(db, document.document_id)

    if job.status == ExtractionStatus.PENDING:
        job.status = ExtractionStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        db.flush()

    try:
        # ---- Parsing ----
        if not document.storage_path:
            _fail(db, job, "SourceDocument has no storage_path; nothing to parse.")
            return _summary_from(job, document, status=ExtractionStatus.FAILED)
        storage = get_storage()
        raw = storage.open_bytes(document.storage_path)
        parsed = parsing_stage.parse_document_bytes(
            raw, content_type=(document.meta or {}).get("content_type")
        )
        parsing_stage.persist_pages(db, document, parsed)
        db.flush()
        indexing_stage.index_document_pages(db, document_id=document.document_id)

        # ---- Extraction (LLM) ----
        # Pick model per document_type so transcripts / press releases /
        # presentations / annual reports route through `LLM_MODEL_FAST` when
        # set, while `FINANCIAL_RESULT` PDFs stay on the premium tier.
        active_model = select_extraction_model(document)
        provider = get_provider(model=active_model)
        extraction = extraction_stage.run_extraction(
            db, document=document, job=job, provider=provider, model=active_model
        )

        # ---- Doc-type-specific extractors ----
        # Each runs only when its predicate matches the document/event. They
        # write additional `ExtractedValue` rows so the normalization stage
        # below sees them — no special path through the rest of the pipeline.
        supplemental: dict[str, int] = {}
        if shareholding_stage.is_shareholding_document(event):
            supplemental["shareholding"] = shareholding_stage.run_shareholding_extraction(
                db, document=document, event=event
            )
        if guidance_stage.is_guidance_document(document):
            supplemental["guidance"] = guidance_stage.run_guidance_extraction(
                db, document=document, event=event
            )
        if concall_stage.is_concall_document(document):
            supplemental["concall"] = concall_stage.run_concall_scoring(
                db, document=document, event=event
            )
        if orderbook_stage.is_order_book_document(document):
            supplemental["order_book"] = orderbook_stage.run_order_book_extraction(
                db, document=document, event=event
            )
        if segment_stage.is_segment_document(document):
            supplemental["segment"] = segment_stage.run_segment_extraction(
                db, document=document, event=event
            )
        if announcement_stage.is_press_release_document(document):
            supplemental["announcement"] = announcement_stage.run_announcement_extraction(
                db, document=document, event=event
            )
        if presentation_stage.is_investor_presentation_document(document):
            supplemental["presentation"] = presentation_stage.run_presentation_extraction(
                db, document=document, event=event
            )

        # ---- Normalization → facts ----
        facts_written = normalization_stage.run_normalization(
            db, document=document, event=event
        )

        # ---- Metrics ----
        metrics_written = metrics_stage.run_metrics(db, document=document)

        # ---- Cross-statement + drift validation ----
        # Runs after metrics so it can read back stored ``CalculatedMetric``
        # rows and re-derive them from facts. Findings feed the review queue
        # and the auto-publish gate alongside the static bounds + anomaly checks.
        metric_validation_report = None
        if document.period_id is not None:
            metric_validation_report = metric_validation_stage.validate_calculated_metrics(
                db,
                company_id=document.company_id,
                period_id=document.period_id,
            )
            metric_validation_stage.apply_validation_actions(
                db,
                company_id=document.company_id,
                period_id=document.period_id,
                report=metric_validation_report,
            )

        # ---- Signals ----
        sigs, signal_diag_raw = signals_stage.run_signals(db, document=document)
        signal_diag = signals_stage.diagnostics_to_dict(signal_diag_raw)

        # ---- Cards ----
        overall_conf = float(extraction.overall_confidence or 0)
        # High extraction confidence alone is not enough — period-scoped facts
        # must exist or signals/cards would be empty while the row shows published.
        publish = (
            document.period_id is not None
            and facts_written > 0
            and overall_conf >= float(settings.AUTO_PUBLISH_CONFIDENCE)
        )
        # The metric_anomaly check flagged values that look impossible against
        # the company's own history (the RELIANCE Q2 60.8 % PAT margin case).
        # Hold the document for analyst review rather than publishing a
        # signal-set built on an obviously suspect metric.
        anomaly_summary: str | None = None
        if publish:
            anomaly_summary = _summarize_anomalies(sigs)
            if anomaly_summary is not None:
                publish = False
                logger.warning(
                    "Suppressing auto-publish on document %s: %s",
                    document.document_id,
                    anomaly_summary,
                )
        # Cross-statement breaches (PAT > Revenue, EBITDA > Revenue) and
        # extreme growth rates are also publish-blockers — the underlying
        # extraction is internally inconsistent.
        cross_statement_summary: str | None = None
        if publish and metric_validation_report is not None and (
            metric_validation_report.cross_statement_breaches
            or metric_validation_report.growth_review
        ):
            parts: list[str] = []
            if metric_validation_report.cross_statement_breaches:
                parts.append(
                    f"{len(metric_validation_report.cross_statement_breaches)} cross-statement breach(es)"
                )
            if metric_validation_report.growth_review:
                parts.append(
                    f"{len(metric_validation_report.growth_review)} extreme growth value(s)"
                )
            cross_statement_summary = ", ".join(parts)
            publish = False
            logger.warning(
                "Suppressing auto-publish on document %s: %s",
                document.document_id,
                cross_statement_summary,
            )
        recompute_drift_summary: str | None = None
        if publish and metric_validation_report is not None and metric_validation_report.recompute_drift:
            recompute_drift_summary = (
                f"{len(metric_validation_report.recompute_drift)} metric recompute drift(s)"
            )
            publish = False
            logger.warning(
                "Suppressing auto-publish on document %s: %s",
                document.document_id,
                recompute_drift_summary,
            )
        unit_rescale_summary: str | None = None
        if publish:
            rescaled_touching = _rescaled_codes_touching_fired_signals(
                db,
                sigs,
                job.validator_report or {},
            )
            if rescaled_touching:
                unit_rescale_summary = (
                    f"unit rescaling on primary inputs ({', '.join(rescaled_touching)})"
                )
                publish = False
                logger.warning(
                    "Suppressing auto-publish on document %s: %s",
                    document.document_id,
                    unit_rescale_summary,
                )
        # Mirror publish state onto the parent objects so the read-side filters
        # (which all gate on `is_published`) stay coherent.
        event.is_published = publish
        for s in sigs:
            s.is_published = publish
        cards_written = cards_stage.run_cards(
            db,
            document=document,
            signals=sigs,
            publish=publish,
            audit_trail=_build_audit_trail(job),
        )

        # Roll up onto the event summary so home / company pages show a real
        # verdict instead of an empty header for ingested events.
        _populate_event_summary(event, sigs, cards_written)

        # Quarterly result events also emit a `result_verdict` summary card.
        # This is the single hero card that ranks above the individual signal
        # cards on the event page and feed.
        verdict = cards_stage.run_result_verdict(
            db,
            document=document,
            event=event,
            signals=sigs,
            publish=publish,
            audit_trail=_build_audit_trail(job),
        )
        if verdict is not None:
            cards_written = [verdict, *cards_written]

        # ---- Bookkeeping ----
        job.status = ExtractionStatus.COMPLETED if publish else ExtractionStatus.NEEDS_REVIEW
        job.completed_at = datetime.now(timezone.utc)
        job.meta = {
            **(job.meta or {}),
            "stages": {
                "pages": len(parsed),
                "extracted": len(extraction.items),
                "facts": facts_written,
                "metrics": metrics_written,
                "signals": len(sigs),
                "cards": len(cards_written),
                **(
                    {f"supplemental_{k}": v for k, v in supplemental.items()}
                    if supplemental
                    else {}
                ),
            },
            "signal_diagnostics": signal_diag,
            "published": publish,
            "auto_publish_threshold": float(settings.AUTO_PUBLISH_CONFIDENCE),
            "metric_validation": (
                metric_validation_report.to_dict()
                if metric_validation_report is not None
                else None
            ),
        }
        document.extraction_status = job.status
        document.cards_generated = len(cards_written)

        fired = signal_diag["fired_count"]
        evaluable = signal_diag["rules_evaluable"]
        _update_review_queue(
            db,
            document=document,
            job=job,
            summary_status="RESOLVED" if publish else "OPEN",
            description=_review_description(
                publish=publish,
                overall_conf=overall_conf,
                cards=len(cards_written),
                signals_fired=fired,
                rules_evaluable=evaluable,
                signal_diag=signal_diag,
                cache_hit=bool((job.meta or {}).get("cache_hit")),
                validator_report=job.validator_report or {},
                anomaly_summary=anomaly_summary,
                cross_statement_summary=cross_statement_summary,
                recompute_drift_summary=recompute_drift_summary,
                unit_rescale_summary=unit_rescale_summary,
            ),
        )

        db.commit()
        return PipelineSummary(
            job_id=job.extraction_job_id,
            document_id=document.document_id,
            status=job.status,
            pages=len(parsed),
            extracted_values=len(extraction.items),
            facts=facts_written,
            metrics=metrics_written,
            signals=len(sigs),
            cards=len(cards_written),
            published=publish,
            confidence=overall_conf,
            notes=extraction.notes,
        )
    except Exception as exc:
        logger.exception("Pipeline failed for job %s", job_id)
        db.rollback()
        # Re-fetch after rollback because the rolled-back transaction expired
        # the original instances.
        job = db.get(ExtractionJob, job_id)
        document = db.get(SourceDocument, job.document_id) if job else None
        if job:
            _fail(db, job, str(exc))
        return _summary_from(
            job or ExtractionJob(extraction_job_id=job_id, document_id=0, company_id=0, job_type=""),
            document,
            status=ExtractionStatus.FAILED,
            error=str(exc),
        )


def _acquire_document_pipeline_lock(db: Session, document_id: int) -> None:
    """Serialize pipeline runs that share a ``document_id``.

    Uses a PostgreSQL transaction-scoped advisory lock when available.
    On other dialects (e.g. in-memory SQLite in unit tests) this is a no-op.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": document_id})


def _fail(db: Session, job: ExtractionJob, message: str) -> None:
    job.status = ExtractionStatus.FAILED
    job.error_message = message
    job.completed_at = datetime.now(timezone.utc)
    if job.document_id:
        doc = db.get(SourceDocument, job.document_id)
        if doc:
            doc.extraction_status = ExtractionStatus.FAILED
    # Bubble the failure into the review queue so an admin can act on it.
    review = (
        db.query(ReviewQueue)
        .filter(ReviewQueue.document_id == job.document_id)
        .order_by(ReviewQueue.created_at.desc())
        .first()
    )
    if review:
        review.status = "OPEN"
        review.issue_description = f"Pipeline failed: {message}"
    db.commit()


def _update_review_queue(
    db: Session,
    *,
    document: SourceDocument,
    job: ExtractionJob,
    summary_status: str,
    description: str,
) -> None:
    review = (
        db.query(ReviewQueue)
        .filter(ReviewQueue.document_id == document.document_id)
        .order_by(ReviewQueue.created_at.desc())
        .first()
    )
    if not review:
        return
    review.status = summary_status
    review.issue_description = description
    if summary_status == "RESOLVED":
        review.resolved_at = datetime.now(timezone.utc)


def _review_description(
    *,
    publish: bool,
    overall_conf: float,
    cards: int,
    signals_fired: int,
    rules_evaluable: int,
    signal_diag: dict,
    cache_hit: bool = False,
    validator_report: dict | None = None,
    anomaly_summary: str | None = None,
    cross_statement_summary: str | None = None,
    recompute_drift_summary: str | None = None,
    unit_rescale_summary: str | None = None,
) -> str:
    threshold = float(settings.AUTO_PUBLISH_CONFIDENCE)
    signal_line = (
        f"{signals_fired} of {rules_evaluable} metric rules fired"
        if rules_evaluable
        else "0 metric rules evaluated"
    )
    if signal_diag.get("blockers"):
        blocker = signal_diag["blockers"][0]
        if blocker == "no_period":
            signal_line = "Signals skipped — document has no financial period"
        elif blocker == "no_metrics":
            signal_line = "Signals skipped — no calculated metrics for this period"

    suffix_parts: list[str] = []
    if cache_hit:
        suffix_parts.append("replayed from extraction cache")
    if validator_report:
        breaches = len(validator_report.get("totals_breaches") or [])
        dropped = len(validator_report.get("source_text_dropped") or [])
        bad_units = len(validator_report.get("unit_dropped") or [])
        if breaches or dropped or bad_units:
            suffix_parts.append(
                f"validators: {breaches} totals breaches, "
                f"{dropped} unanchored, {bad_units} bad-unit"
            )
    suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""

    if publish:
        return (
            f"Auto-published: {cards} cards, {signal_line}, "
            f"{overall_conf:.0f}% extraction confidence (≥ {threshold:.0f}%)." + suffix
        )
    reasons: list[str] = []
    if overall_conf < threshold:
        reasons.append(
            f"extraction confidence {overall_conf:.0f}% is below auto-publish "
            f"threshold ({threshold:.0f}%)"
        )
    if anomaly_summary:
        reasons.append(anomaly_summary)
    if cross_statement_summary:
        reasons.append(cross_statement_summary)
    if recompute_drift_summary:
        reasons.append(recompute_drift_summary)
    if unit_rescale_summary:
        reasons.append(unit_rescale_summary)
    if signals_fired == 0 and not signal_diag.get("blockers"):
        reasons.append("no metric rules breached — cards may be minimal")
    if validator_report and validator_report.get("totals_breaches"):
        reasons.append("totals math breach in extracted values")
    if not reasons:
        reasons.append("awaiting admin approval")
    return f"Needs review: {signal_line}; {cards} cards; " + "; ".join(reasons) + "." + suffix


def _rescaled_codes_touching_fired_signals(
    db: Session,
    sigs: list,
    validator_report: dict,
) -> list[str]:
    """Return fact codes that were unit-rescaled and feed a fired signal's primary metric."""
    rescaled = validator_report.get("unit_rescaled") or []
    if not rescaled or not sigs:
        return []
    rescaled_codes = {
        str(entry["normalized_code"])
        for entry in rescaled
        if isinstance(entry, dict) and entry.get("normalized_code")
    }
    if not rescaled_codes:
        return []
    touched: list[str] = []
    for sig in sigs:
        if sig.primary_metric_id is None:
            continue
        cm = db.get(CalculatedMetric, sig.primary_metric_id)
        if cm is None or cm.metric_def_id is None:
            continue
        md = db.get(MetricDefinition, cm.metric_def_id)
        if md is None:
            continue
        for inp in md.inputs_json or []:
            if not isinstance(inp, dict):
                continue
            if (inp.get("kind") or "fact").lower() != "fact":
                continue
            if (inp.get("scope") or "CURRENT").upper() != "CURRENT":
                continue
            code = inp.get("code")
            if code and code in rescaled_codes and code not in touched:
                touched.append(code)
    return touched


def _build_audit_trail(job: ExtractionJob) -> dict:
    """Snapshot pipeline versions for the cards we are about to write.

    Persisted on ``IntelligenceCard.display_context['audit_trail']`` so the
    analyst-reproducibility export can answer the question "which pipeline
    produced this card?" without re-joining ``extraction_jobs``.
    """
    return {
        "extraction_job_id": job.extraction_job_id,
        "prompt_version": job.prompt_version,
        "parser_version": job.parser_version,
        "model_name": job.model_name,
        "provider_used": job.provider_used,
        "llm_temperature": (
            float(job.llm_temperature) if job.llm_temperature is not None else None
        ),
        "llm_seed": job.llm_seed,
        "request_hash": job.request_hash,
        "completed_at": (
            job.completed_at.isoformat() if job.completed_at else None
        ),
    }


def _summarize_anomalies(sigs: list) -> str | None:
    """Return a short summary string when any fired signal's primary metric
    is suspect — historical anomaly or sanity-bound quarantine.

    The runner uses it to suppress auto-publish; the review queue surfaces
    the same string for the admin. Quarantine + anomaly are both blocking
    because either one means the rule fired on a number we do not trust.
    """
    from app.models.intelligence import CalculatedMetric, MetricDefinition

    anomalies: list[str] = []
    quarantined: list[str] = []
    for s in sigs:
        cm = getattr(s, "primary_metric", None)
        if cm is None:
            # Lazy SQLAlchemy attribute: the signal carries primary_metric_id;
            # the actual row is fetched if we use the ORM session via the
            # session attached to the signal.
            from sqlalchemy.orm import object_session

            session = object_session(s)
            if session is None or s.primary_metric_id is None:
                continue
            cm = session.get(CalculatedMetric, s.primary_metric_id)
        if cm is None:
            continue
        is_anomaly = bool(getattr(cm, "anomaly_flag", False))
        is_quarantined = bool(getattr(cm, "is_quarantined", False))
        if not (is_anomaly or is_quarantined):
            continue
        md_session = None
        try:
            from sqlalchemy.orm import object_session

            md_session = object_session(cm)
        except Exception:  # pragma: no cover - defensive
            md_session = None
        code = None
        if md_session is not None:
            md = md_session.get(MetricDefinition, cm.metric_def_id)
            code = md.metric_code if md else None
        label = code or f"metric#{cm.metric_def_id}"
        if is_anomaly:
            anomalies.append(label)
        if is_quarantined:
            quarantined.append(label)
    if not anomalies and not quarantined:
        return None
    parts: list[str] = []
    if anomalies:
        parts.append(f"historical-anomaly on {', '.join(sorted(set(anomalies)))}")
    if quarantined:
        parts.append(f"quarantined primary metric on {', '.join(sorted(set(quarantined)))}")
    return "; ".join(parts)


def _populate_event_summary(
    event: CompanyEvent, sigs: list, cards: list
) -> None:
    """Best-effort header roll-up so the event page shows a verdict."""
    if not sigs:
        event.overall_signal = SignalDirection.NEUTRAL
        summary = build_event_summary_text([], cards)
        if summary:
            event.summary_text = summary
        return
    score_map = {"POSITIVE": 0, "NEGATIVE": 0, "MIXED": 0, "NEUTRAL": 0}
    for s in sigs:
        score_map[s.signal_direction.value] = score_map.get(s.signal_direction.value, 0) + 1
    winner = max(score_map, key=score_map.get)
    event.overall_signal = SignalDirection(winner)
    severity_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    top_sev = max(sigs, key=lambda s: severity_rank.get(s.severity.value, 0))
    event.overall_severity = top_sev.severity
    event.summary_text = build_event_summary_text(sigs, cards)
    event.main_issue = pick_main_issue(sigs, cards)
    event.watch_next = pick_watch_next(cards) or (
        "Review flagged metrics and source filings before the next reporting period."
    )


def _summary_from(
    job: ExtractionJob,
    document: SourceDocument | None,
    *,
    status: ExtractionStatus,
    error: str | None = None,
) -> PipelineSummary:
    return PipelineSummary(
        job_id=job.extraction_job_id,
        document_id=document.document_id if document else 0,
        status=status,
        pages=0,
        extracted_values=0,
        facts=0,
        metrics=0,
        signals=0,
        cards=0,
        published=False,
        confidence=0.0,
        error=error,
    )
