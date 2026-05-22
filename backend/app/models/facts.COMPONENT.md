# models/facts

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Extraction outputs and normalized facts. Sits between source documents and intelligence cards in the pipeline.

## Source

- Path: `backend/app/models/facts.py`
- Layer: backend-models

## Contract

Models defined:

- `FinancialLineItemDefinition` — canonical line-item dictionary (e.g. `revenue_from_operations`, `ebitda`, `pat`).
- `ExtractedValue` — raw extraction rows tied to a document / event / company / period.
- `FinancialStatementFact` — normalized P&L / Balance Sheet / Cash Flow numbers with `period_value_type` (`CURRENT`, `LYQ`, etc.).
- `CompanySegment`, `SegmentFact` — segment-level revenue / margin breakdowns.
- `ConcallSpeaker`, `ConcallFact`, `TranscriptChunk`, `AnalystQuestion` — earnings call structure.
- `PresentationFact`, `AnnouncementFact` — presentation slide / press release facts.

## Dependencies

- Imports: SQLAlchemy primitives, `JSONB`, `Base`, enums (`AuditStatus`, `ConfidenceLevel`, `ConsolidationType`, `SeverityLevel`, `SignalDirection`, `StatementType`).

## Patterns (symmetry)

- All numeric values use `Numeric(24, 6)` for amounts and `Numeric(5, 2)` for confidence — match those precisions on new fact tables.
- Fact rows always carry `company_id` and `document_id` so they can be re-derived from a single document.
- `ExtractedValue.normalized_label` references the canonical `FinancialLineItemDefinition.normalized_code` — keep these in sync when adding a new line item.

## Verification checklist

- [ ] Numeric precision matches the rest of the facts tables
- [ ] New fact table references `company_id` and `document_id`
- [ ] `__init__.py` re-exports the new model
- [ ] Alembic migration created
