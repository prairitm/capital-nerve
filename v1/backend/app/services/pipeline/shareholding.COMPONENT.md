# services/pipeline/shareholding

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1b. Regex-based extractor for the standard NSE / BSE shareholding-
pattern PDF. Pulls promoter holding %, promoter pledge %, FII / DII /
public holdings into `ExtractedValue` rows so the metric engine can
compute QoQ deltas and the governance signals (`promoter_buying`,
`pledge_risk`, `fii_accumulation`, `governance_red_flag`).

## Source

- Path: `backend/app/services/pipeline/shareholding.py`
- Layer: backend-service

## Contract

- `is_shareholding_document(event) -> bool` — gate; runner only invokes the
  extractor when the parent `CompanyEvent.event_type ==
  EventType.SHAREHOLDING_PATTERN`.
- `run_shareholding_extraction(db, *, document, event) -> int` — returns
  rows written. Idempotent — relies on `extraction.run_extraction` having
  already wiped previous rows for the document.

## Dependencies

- May import: `app.models.{events,facts}`, `app.db.enums`.
- Must not import: LLM modules, other pipeline stages.

## Patterns (symmetry)

- Output schema mirrors `ExtractedValue.normalized_label` — values land at
  the same layer as financial line items so the rest of the pipeline does
  not change shape.
- New shareholding fields require: a new `LINE_ITEMS` row in
  [`seed_catalog.py`](../../seed/seed_catalog.py) **and** a new pattern in
  `_PATTERNS` here. Keep the two in lockstep.

## Verification checklist

- [ ] `is_shareholding_document` returns `True` only for `SHAREHOLDING_PATTERN`
      events.
- [ ] Re-running the pipeline doesn't duplicate shareholding rows (relies on
      the extraction stage clearing prior rows).
- [ ] Each `ExtractedValue` carries `unit="%"`, `confidence_level=HIGH`.
- [ ] No extracted values are produced for documents whose pages don't
      contain the regex's keywords (silent skip, not error).
