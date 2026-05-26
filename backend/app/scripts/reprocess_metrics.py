"""Reprocess persisted extracted values without calling the LLM.

Phase 1A of the analyst-trust overhaul introduces new unit rescaling
(lakh → crore, million → crore, raw rupees → crore) and metric output
sanity bounds. Existing `extracted_values` rows for already-ingested
filings need both treatments applied without going back to the model —
that's what this script does.

Pipeline coverage::

    extracted_values (re-canonicalise units in place)
      → financial_statement_facts  (rebuilt)
      → calculated_metrics         (rebuilt, with bounds quarantine)
      → generated_signals          (rebuilt)
      → intelligence_cards         (rebuilt)
      → card_evidence              (rebuilt)

The script never calls the LLM provider and never deletes raw
``extracted_values`` rows — the values themselves are updated in place
when the canonicaliser rescales them.

Usage::

    python -m app.scripts.reprocess_metrics --all
    python -m app.scripts.reprocess_metrics --company RELIANCE
    python -m app.scripts.reprocess_metrics --document 42
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import SignalDirection
from app.db.session import SessionLocal
from app.models.events import CompanyEvent, ExtractionJob, SourceDocument
from app.models.facts import ExtractedValue
from app.models.intelligence import CalculatedMetric, IntelligenceCard
from app.models.master import Company
from app.services.event_summary import (
    build_event_summary_text,
    pick_main_issue,
    pick_watch_next,
)
from app.services.pipeline import cards as cards_stage
from app.services.pipeline import metric_validation as metric_validation_stage
from app.services.pipeline import metrics as metrics_stage
from app.services.pipeline import normalization as normalization_stage
from app.services.pipeline import signals as signals_stage
from app.services.pipeline.runner import (
    _build_audit_trail,
    _rescaled_codes_touching_fired_signals,
)
from app.services.pipeline.llm import ExtractedLineItem
from app.services.pipeline.validators import (
    ValidatorReport,
    canonicalize_units,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class _ReprocessStats:
    documents: int = 0
    rescaled_values: int = 0
    metrics_written: int = 0
    quarantined_metrics: int = 0
    anomalous_metrics: int = 0
    signals_written: int = 0
    cards_written: int = 0
    anomaly_suppressed_documents: int = 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all", action="store_true", help="Reprocess every existing document."
    )
    group.add_argument(
        "--company",
        help="NSE symbol or BSE code — reprocess that company's documents only.",
    )
    group.add_argument(
        "--document", type=int, help="Reprocess a single document by id."
    )
    args = parser.parse_args()

    db = SessionLocal()
    stats = _ReprocessStats()
    try:
        document_ids = _select_documents(db, args)
        total = len(document_ids)
        logger.info("Reprocessing %s document(s)", total)
        for i, document_id in enumerate(document_ids, start=1):
            try:
                _reprocess_document(db, document_id, stats)
                db.commit()
                logger.info(
                    "[%s/%s] document_id=%s OK", i, total, document_id
                )
            except Exception:
                db.rollback()
                logger.exception(
                    "[%s/%s] document_id=%s FAILED — leaving prior state intact",
                    i,
                    total,
                    document_id,
                )
    finally:
        db.close()

    logger.info(
        "Done: documents=%s rescaled_values=%s metrics=%s quarantined=%s anomaly=%s "
        "signals=%s cards=%s anomaly_suppressed_docs=%s",
        stats.documents,
        stats.rescaled_values,
        stats.metrics_written,
        stats.quarantined_metrics,
        stats.anomalous_metrics,
        stats.signals_written,
        stats.cards_written,
        stats.anomaly_suppressed_documents,
    )
    return 0


def _select_documents(db: Session, args: argparse.Namespace) -> list[int]:
    if args.document:
        return [int(args.document)]
    if args.company:
        symbol = args.company.upper()
        company = db.scalar(
            select(Company).where(
                (Company.nse_symbol == symbol) | (Company.bse_code == symbol)
            )
        )
        if not company:
            logger.error("No company with NSE symbol or BSE code %s", symbol)
            return []
        from app.models.master import FinancialPeriod

        ids = db.scalars(
            select(SourceDocument.document_id)
            .outerjoin(
                FinancialPeriod,
                FinancialPeriod.period_id == SourceDocument.period_id,
            )
            .where(SourceDocument.company_id == company.company_id)
            .order_by(
                FinancialPeriod.fy_year.asc().nulls_last(),
                FinancialPeriod.quarter.asc().nulls_last(),
                SourceDocument.document_id.asc(),
            )
        ).all()
        return list(ids)
    # Order by reporting period so prior-quarter metric values exist in the
    # DB before later quarters compute composite metrics (e.g. the new
    # revenue_yoy_growth_acceleration_pp reads revenue_yoy_growth at PQ).
    # Documents without a period sort last but keep stable order.
    from app.models.master import FinancialPeriod

    return list(
        db.scalars(
            select(SourceDocument.document_id)
            .outerjoin(
                FinancialPeriod,
                FinancialPeriod.period_id == SourceDocument.period_id,
            )
            .order_by(
                FinancialPeriod.fy_year.asc().nulls_last(),
                FinancialPeriod.quarter.asc().nulls_last(),
                SourceDocument.document_id.asc(),
            )
        ).all()
    )


def _reprocess_document(
    db: Session, document_id: int, stats: _ReprocessStats
) -> None:
    document = db.get(SourceDocument, document_id)
    if document is None:
        logger.warning("document_id=%s not found, skipping", document_id)
        return
    event = (
        db.get(CompanyEvent, document.event_id)
        if document.event_id is not None
        else None
    )

    rescaled = _recanonicalise_extracted_values(db, document_id)
    stats.rescaled_values += rescaled
    db.flush()

    if event is None or document.period_id is None:
        logger.info(
            "document_id=%s has no period or event; rescaled %s values but skipping downstream",
            document_id,
            rescaled,
        )
        stats.documents += 1
        return

    facts_written = normalization_stage.run_normalization(
        db, document=document, event=event
    )
    metrics_written = metrics_stage.run_metrics(db, document=document)

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

    from sqlalchemy import func

    quarantined = db.scalar(
        select(func.count(CalculatedMetric.metric_id)).where(
            CalculatedMetric.company_id == document.company_id,
            CalculatedMetric.period_id == document.period_id,
            CalculatedMetric.is_quarantined.is_(True),
        )
    ) or 0
    anomalous = db.scalar(
        select(func.count(CalculatedMetric.metric_id)).where(
            CalculatedMetric.company_id == document.company_id,
            CalculatedMetric.period_id == document.period_id,
            CalculatedMetric.anomaly_flag.is_(True),
        )
    ) or 0
    sigs, _ = signals_stage.run_signals(db, document=document)

    job = db.scalar(
        select(ExtractionJob)
        .where(ExtractionJob.document_id == document.document_id)
        .order_by(ExtractionJob.created_at.desc())
        .limit(1)
    )
    audit_trail = _build_audit_trail(job) if job else None

    # Re-publish to whatever state the row was already in; reprocess never
    # downgrades a previously-published row unless a governance gate fires.
    publish = bool(document.is_published if hasattr(document, "is_published") else True)
    publish = publish and facts_written > 0

    suppressed = False
    if publish:
        suppressed = _has_anomalous_signal(db, sigs)
        if suppressed:
            publish = False
        elif (
            metric_validation_report.cross_statement_breaches
            or metric_validation_report.growth_review
            or metric_validation_report.recompute_drift
        ):
            publish = False
            suppressed = True
        elif job and _rescaled_codes_touching_fired_signals(
            db, sigs, job.validator_report or {}
        ):
            publish = False
            suppressed = True
        if suppressed:
            stats.anomaly_suppressed_documents += 1
            logger.info(
                "  publish suppressed: document_id=%s held for analyst review",
                document.document_id,
            )

    cards_written = cards_stage.run_cards(
        db,
        document=document,
        signals=sigs,
        publish=publish,
        audit_trail=audit_trail,
    )

    _populate_event_summary(event, sigs, cards_written)

    verdict = cards_stage.run_result_verdict(
        db,
        document=document,
        event=event,
        signals=sigs,
        publish=publish,
        audit_trail=audit_trail,
    )
    if verdict is not None:
        cards_written = [verdict, *cards_written]

    stats.documents += 1
    stats.metrics_written += metrics_written
    stats.quarantined_metrics += int(quarantined)
    stats.anomalous_metrics += int(anomalous)
    stats.signals_written += len(sigs)
    stats.cards_written += len(cards_written)
    logger.info(
        "  facts=%s metrics=%s quarantined=%s anomaly=%s signals=%s cards=%s%s",
        facts_written,
        metrics_written,
        int(quarantined),
        int(anomalous),
        len(sigs),
        len(cards_written),
        " (publish suppressed)" if suppressed else "",
    )


def _has_anomalous_signal(db: Session, sigs: list) -> bool:
    """Return True when any signal points at a suspect primary metric.

    Mirrors ``runner._summarize_anomalies``: a metric is suspect when either
    ``anomaly_flag`` (historical-distribution outlier) or ``is_quarantined``
    (static / cross-statement / drift / extreme-growth breach) is set. Either
    one is enough to suppress publish.
    """
    metric_ids = [s.primary_metric_id for s in sigs if s.primary_metric_id is not None]
    if not metric_ids:
        return False
    from sqlalchemy import func

    flagged = db.scalar(
        select(func.count(CalculatedMetric.metric_id)).where(
            CalculatedMetric.metric_id.in_(metric_ids),
            (CalculatedMetric.anomaly_flag.is_(True))
            | (CalculatedMetric.is_quarantined.is_(True)),
        )
    )
    return bool(flagged)


def _recanonicalise_extracted_values(db: Session, document_id: int) -> int:
    """Run ``canonicalize_units`` over persisted ``ExtractedValue`` rows in place.

    Mirrors the LLM-path call in [extraction.run_extraction](../services/pipeline/extraction.py)
    but operates on already-persisted rows so the existing RELIANCE ingests
    pick up lakh→crore / million→crore rescaling without re-calling the
    provider.
    """
    rows = (
        db.query(ExtractedValue)
        .filter(ExtractedValue.document_id == document_id)
        .filter(ExtractedValue.numeric_value.is_not(None))
        .all()
    )
    if not rows:
        return 0

    proxies: list[tuple[ExtractedValue, ExtractedLineItem]] = []
    for row in rows:
        proxies.append(
            (
                row,
                ExtractedLineItem(
                    normalized_code=row.normalized_label or row.raw_label,
                    raw_label=row.raw_label,
                    value=float(row.numeric_value),
                    unit=row.unit or "crore",
                    page_number=row.page_number,
                    source_text=row.source_text,
                    confidence=float(row.confidence_score or 0.0),
                    column_label=row.column_label,
                ),
            )
        )

    report = ValidatorReport()
    kept = canonicalize_units([p[1] for p in proxies], report=report)
    kept_codes = {(id(item),) for item in kept}

    rescaled = 0
    for original, item in proxies:
        if (id(item),) not in kept_codes:
            continue
        if float(original.numeric_value or 0.0) != item.value or (
            original.unit or "crore"
        ) != item.unit:
            original.numeric_value = item.value
            original.raw_value = str(item.value)
            original.unit = item.unit
            rescaled += 1

    return rescaled


def _populate_event_summary(
    event: CompanyEvent, sigs: list, cards: list
) -> None:
    """Mirror runner._populate_event_summary so the event header stays fresh."""
    if not sigs:
        event.overall_signal = SignalDirection.NEUTRAL
        summary = build_event_summary_text([], cards)
        if summary:
            event.summary_text = summary
        return
    score_map: dict[str, int] = {"POSITIVE": 0, "NEGATIVE": 0, "MIXED": 0, "NEUTRAL": 0}
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


if __name__ == "__main__":
    sys.exit(main())
