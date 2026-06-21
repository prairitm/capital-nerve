"""Stage 2: `ExtractedValue` → `FinancialStatementFact`.

Maps the LLM's per-document extractions onto the master `financial_line_item_
definitions` table, applying value-type semantics so EBITDA-margin (a derived
percentage) doesn't accidentally end up as a balance-sheet line item.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import AuditStatus, ConsolidationType
from app.models.events import CompanyEvent, SourceDocument
from app.models.facts import ExtractedValue, FinancialLineItemDefinition, FinancialStatementFact


def run_normalization(
    db: Session,
    *,
    document: SourceDocument,
    event: CompanyEvent,
) -> int:
    """Upsert one fact row per normalized extracted value for the document.

    The DB unique key is `(company_id, period_id, line_item_def_id,
    consolidation, period_value_type)` — not `document_id`. Seeded facts for
    the same quarter must be updated in place when a new filing is ingested.
    """
    if document.period_id is None:
        return 0

    line_items = _load_line_items(db)
    values = (
        db.query(ExtractedValue)
        .filter(
            ExtractedValue.document_id == document.document_id,
            ExtractedValue.numeric_value.is_not(None),
        )
        .all()
    )
    if not values:
        return 0

    consolidation = event.consolidation or ConsolidationType.CONSOLIDATED
    audit_status = event.audit_status or AuditStatus.UNKNOWN

    extracted_codes = {
        (ev.normalized_label or ev.raw_label or "").strip()
        for ev in values
    }

    written = 0
    seen_keys: set[tuple[int, int, ConsolidationType, str]] = set()
    for ev in values:
        code = ev.normalized_label or ev.raw_label
        li = line_items.get(code)
        if not li:
            continue
        if _skip_derived_margin_fact(code, extracted_codes):
            _delete_margin_fact(
                db,
                company_id=document.company_id,
                period_id=document.period_id,
                line_item_def_id=li.line_item_def_id,
                consolidation=consolidation,
            )
            continue
        key = (li.line_item_def_id, document.period_id, consolidation, "CURRENT")
        if key in seen_keys:
            continue
        seen_keys.add(key)

        existing = db.scalar(
            select(FinancialStatementFact).where(
                FinancialStatementFact.company_id == document.company_id,
                FinancialStatementFact.period_id == document.period_id,
                FinancialStatementFact.line_item_def_id == li.line_item_def_id,
                FinancialStatementFact.consolidation == consolidation,
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        )
        if existing:
            existing.event_id = document.event_id
            existing.document_id = document.document_id
            existing.audit_status = audit_status
            existing.value = float(ev.numeric_value or 0.0)
            existing.unit = ev.unit or "crore"
            existing.currency = ev.currency or "INR"
            existing.column_label = ev.column_label
            existing.source_extracted_value_id = ev.extracted_value_id
            existing.confidence_score = ev.confidence_score
        else:
            db.add(
                FinancialStatementFact(
                    company_id=document.company_id,
                    event_id=document.event_id,
                    document_id=document.document_id,
                    period_id=document.period_id,
                    line_item_def_id=li.line_item_def_id,
                    consolidation=consolidation,
                    audit_status=audit_status,
                    value=float(ev.numeric_value or 0.0),
                    unit=ev.unit or "crore",
                    currency=ev.currency or "INR",
                    column_label=ev.column_label,
                    period_value_type="CURRENT",
                    source_extracted_value_id=ev.extracted_value_id,
                    confidence_score=ev.confidence_score,
                )
            )
        written += 1

    db.flush()
    return written


def _load_line_items(db: Session) -> dict[str, FinancialLineItemDefinition]:
    rows = db.execute(select(FinancialLineItemDefinition)).scalars().all()
    return {r.normalized_code: r for r in rows}


def _skip_derived_margin_fact(code: str, extracted_codes: set[str]) -> bool:
    """Do not persist LLM margin % when base P&L lines are present — metrics stage recomputes."""
    if code == "ebitda_margin":
        return "ebitda" in extracted_codes and "revenue_from_operations" in extracted_codes
    if code == "pat_margin":
        return "pat" in extracted_codes and "revenue_from_operations" in extracted_codes
    return False


def _delete_margin_fact(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    line_item_def_id: int,
    consolidation: ConsolidationType,
) -> None:
    existing = db.scalar(
        select(FinancialStatementFact).where(
            FinancialStatementFact.company_id == company_id,
            FinancialStatementFact.period_id == period_id,
            FinancialStatementFact.line_item_def_id == line_item_def_id,
            FinancialStatementFact.consolidation == consolidation,
            FinancialStatementFact.period_value_type == "CURRENT",
        )
    )
    if existing is not None:
        db.delete(existing)
