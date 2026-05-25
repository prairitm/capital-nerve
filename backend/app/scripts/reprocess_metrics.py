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
from app.models.events import CompanyEvent, SourceDocument
from app.models.facts import ExtractedValue
from app.models.intelligence import CalculatedMetric, IntelligenceCard
from app.models.master import Company
from app.services.event_summary import (
    build_event_summary_text,
    pick_main_issue,
    pick_watch_next,
)
from app.services.pipeline import cards as cards_stage
from app.services.pipeline import metrics as metrics_stage
from app.services.pipeline import normalization as normalization_stage
from app.services.pipeline import signals as signals_stage
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
    signals_written: int = 0
    cards_written: int = 0


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
        "Done: documents=%s rescaled_values=%s metrics=%s quarantined=%s signals=%s cards=%s",
        stats.documents,
        stats.rescaled_values,
        stats.metrics_written,
        stats.quarantined_metrics,
        stats.signals_written,
        stats.cards_written,
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
        ids = db.scalars(
            select(SourceDocument.document_id)
            .where(SourceDocument.company_id == company.company_id)
            .order_by(SourceDocument.document_id)
        ).all()
        return list(ids)
    return list(
        db.scalars(
            select(SourceDocument.document_id).order_by(SourceDocument.document_id)
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
    quarantined = db.scalar(
        select(  # type: ignore[arg-type]
            __import__("sqlalchemy").func.count(CalculatedMetric.metric_id)
        ).where(
            CalculatedMetric.company_id == document.company_id,
            CalculatedMetric.period_id == document.period_id,
            CalculatedMetric.is_quarantined.is_(True),
        )
    ) or 0
    sigs, _ = signals_stage.run_signals(db, document=document)

    # Re-publish to whatever state the row was already in; reprocess never
    # downgrades a previously-published row.
    publish = bool(document.is_published if hasattr(document, "is_published") else True)
    publish = publish and facts_written > 0

    cards_written = cards_stage.run_cards(
        db, document=document, signals=sigs, publish=publish
    )

    _populate_event_summary(event, sigs, cards_written)

    verdict = cards_stage.run_result_verdict(
        db, document=document, event=event, signals=sigs, publish=publish
    )
    if verdict is not None:
        cards_written = [verdict, *cards_written]

    stats.documents += 1
    stats.metrics_written += metrics_written
    stats.quarantined_metrics += int(quarantined)
    stats.signals_written += len(sigs)
    stats.cards_written += len(cards_written)
    logger.info(
        "  facts=%s metrics=%s quarantined=%s signals=%s cards=%s",
        facts_written,
        metrics_written,
        int(quarantined),
        len(sigs),
        len(cards_written),
    )


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
