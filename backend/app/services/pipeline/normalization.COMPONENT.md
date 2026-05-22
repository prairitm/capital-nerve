# services/pipeline/normalization

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 2. Map the per-document `ExtractedValue` rows onto the canonical
`financial_statement_facts` table so downstream consumers (metrics, /v1 read
side, signal_context) can ignore the document layout and work in terms of
normalized codes.

## Source

- Path: `backend/app/services/pipeline/normalization.py`
- Layer: backend-service

## Contract

- `run_normalization(db, *, document, event) -> int` — writes one
  `FinancialStatementFact` per recognized `ExtractedValue`. Returns the count.

## Dependencies

- May import: `app.models.events`, `app.models.facts`.
- Must not import: pipeline stages other than its own helpers, LLM modules.

## Patterns (symmetry)

- The `financial_line_item_definitions` table is the **only** source of truth
  for the allowed `normalized_code` set; unknown codes are skipped, not
  invented.
- `(company_id, period_id, line_item_def_id, consolidation, period_value_type)`
  is the unique key — duplicates are filtered in-process before insert so the
  unique index never raises.
- `period_value_type` is always `"CURRENT"` for now; future support for
  prior-period rows from the same document should reuse the same column.
- Re-runs first DELETE existing facts for the document, then INSERT — keeps
  idempotency without partial-update bugs.

## Verification checklist

- [ ] Unknown normalized codes are skipped silently (logged at debug).
- [ ] No fact row is written without a `period_id`.
- [ ] Re-running the pipeline does not duplicate facts.
- [ ] `source_extracted_value_id` always points back at the originating row.
