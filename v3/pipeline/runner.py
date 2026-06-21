"""Orchestrate document processing: extract → metrics → signals."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from config import settings
from db import connect, init_db
from pipeline.extract import run_extraction
from pipeline.persist import (
    document_counts,
    load_document_bundle,
    load_fact_details_for_period,
    replace_metric_values,
    replace_signals,
    set_document_status,
    set_event_status,
    upsert_values,
)

logger = logging.getLogger(__name__)


def process_document(document_id: str, *, force: bool = False) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        bundle = load_document_bundle(conn, document_id)
        if not bundle:
            return {"success": False, "error": "document not found", "document_id": document_id}

        doc = bundle["document"]
        event = bundle["event"]
        if not event:
            return {
                "success": False,
                "error": "no event linked to document",
                "document_id": document_id,
            }

        if doc.get("status") == "processed" and not force:
            counts = document_counts(conn, document_id)
            return {
                "success": True,
                "document_id": document_id,
                "event_id": event["id"],
                "status": "processed",
                "skipped": True,
                **counts,
            }

        company_id = doc["company_id"]
        event_id = event["id"]
        set_document_status(conn, document_id, "processing")
        set_event_status(conn, event_id, "processing")
        conn.commit()

    try:
        pdf_path = Path(doc["storage_path"])
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        extraction = run_extraction(
            pdf_path,
            title=doc.get("title") or event.get("title") or "",
            document_id=document_id,
            force=force,
        )
        period = extraction.period

        from capital_nerve_logic import build_raw_details, compute_pipeline_metrics, interpret_metric_signals
        from periods import prior_quarter_period, prior_year_period

        raw_details = build_raw_details(extraction.accepted_rows)
        py_period = prior_year_period(period)
        pq_period = prior_quarter_period(period)

        with connect() as conn:
            values_written = upsert_values(
                conn,
                company_id=company_id,
                event_id=event_id,
                period_start=None,
                period_end=period.quarter_end,
                rows=extraction.accepted_rows,
            )

            py_details = load_fact_details_for_period(
                conn,
                company_id=company_id,
                period_end=py_period.quarter_end,
            )
            pq_details = load_fact_details_for_period(
                conn,
                company_id=company_id,
                period_end=pq_period.quarter_end,
            )

            def resolve_provenance(fact_key: str, scope: str) -> dict[str, Any] | None:
                pool = {
                    "CURRENT": raw_details,
                    "PY": py_details,
                    "PQ": pq_details,
                }.get(scope.upper(), {})
                detail = pool.get(fact_key)
                if not detail:
                    return None
                return {
                    "value": detail.get("numeric_value"),
                    "unit": detail.get("unit"),
                    "evidence": detail.get("evidence"),
                    "source_document_id": document_id,
                }

            metrics = compute_pipeline_metrics(
                {},
                {},
                {},
                period_label=period.label,
                raw_details=raw_details,
                prior_year_details=py_details,
                prior_quarter_details=pq_details,
                resolve_provenance=resolve_provenance,
            )
            metrics_written = replace_metric_values(
                conn,
                company_id=company_id,
                event_id=event_id,
                period_start=None,
                period_end=period.quarter_end,
                metrics=metrics,
            )

            signals = interpret_metric_signals(metrics)
            signals_written = replace_signals(
                conn,
                company_id=company_id,
                event_id=event_id,
                signals=signals,
                metrics=metrics,
            )

            set_event_status(
                conn,
                event_id,
                "processed",
                fiscal_year=period.fy_start_year,
                fiscal_quarter=period.quarter,
            )
            set_document_status(conn, document_id, "processed", error_message=None)
            conn.commit()

        return {
            "success": True,
            "document_id": document_id,
            "event_id": event_id,
            "status": "processed",
            "period": period.label,
            "extracted_values": values_written,
            "metric_values": metrics_written,
            "signals": signals_written,
            "rejected_facts": len(extraction.rejected_rows),
        }
    except Exception as exc:
        logger.exception("process_document failed for %s", document_id)
        with connect() as conn:
            set_document_status(conn, document_id, "failed", error_message=str(exc))
            if event:
                set_event_status(conn, event["id"], "failed")
            conn.commit()
        return {
            "success": False,
            "document_id": document_id,
            "event_id": event["id"] if event else None,
            "status": "failed",
            "error": str(exc),
        }
