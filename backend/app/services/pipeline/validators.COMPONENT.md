# services/pipeline/validators

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Deterministic post-LLM sanity checks. Sits between the LLM/replay step in
[`extraction.run_extraction`](extraction.py) and the persistence of
`ExtractedValue` rows so that nothing the model emits gets into the database
without being anchored to a real page, normalised to a canonical unit, and
sense-checked against basic accounting identities.

## Source

- Path: `backend/app/services/pipeline/validators.py`
- Layer: backend-service

## Contract

- `run_validators(items, *, pages) -> (items, ValidatorReport)` — the entry
  point. Runs the three validators below in order; returns the filtered /
  amended item list plus a structured report.
- `validate_source_text(items, *, pages, report)` — drops any item whose
  expected numeric token (formatted from `item.value`) cannot be found on the
  whitespace-normalised text of the claimed `page_number`. Items with a
  missing page or page out of range are kept but downgraded to confidence ≤ 60.
- `canonicalize_units(items, *, report)` — maps unit aliases ("Cr",
  "INR cr", "Rs.", "₹") onto the canonical schema enum (`crore`, `%`, `Rs`,
  `bps`, `days`, `x`). Drops items whose unit cannot be canonicalised.
- `validate_totals(items, *, report)` — checks accounting identities:
  - `total_income = revenue_from_operations + other_income`
  - `pat = pbt - tax_expense`
  - `ebitda_margin = ebitda / revenue_from_operations * 100`
  - `pbt = total_income - sum(expense components)` (when ≥3 expense lines present)
  Tolerance is 1 %. On breach we *downgrade* the confidence of every involved
  item to `min(item.confidence, 40)` rather than dropping; the Review Queue's
  confidence gate then surfaces the row for an admin.
- `ValidatorReport.to_dict()` — JSON shape persisted onto
  `extraction_jobs.validator_report`.

## Dependencies

- May import: `app.services.pipeline.llm` (`ExtractedLineItem` only — no
  provider classes), stdlib.
- Must not import: other pipeline stages, routers, models, the database
  session. Validators stay pure functions of typed inputs so they're trivial
  to unit-test.

## Patterns (symmetry)

- Each validator takes the same `report: ValidatorReport` accumulator. Don't
  return errors out-of-band; everything that touched the run must be
  serialisable through the report so the admin UI can explain low confidence.
- Drop-vs-downgrade policy:
  - **Drop** when the item is definitely wrong (numeric token not on page,
    unrecognisable unit) — keeping it would poison downstream metrics.
  - **Downgrade** when the item is *suspect* but plausibly correct (totals
    math breach) — the Review Queue is the right escalation, not silent
    deletion.

## Verification checklist

- [ ] `run_validators` is the only entry point used by extraction; the
      individual functions are imported only by tests.
- [ ] Unit canonicalisation is kept in sync with `llm._ALLOWED_UNITS` and
      the JSON schema enum (drift breaks the schema validator at the LLM).
- [ ] Totals breach downgrades every involved item's confidence, not just
      the target.
- [ ] `tests/test_validators.py` covers each validator path (source-text
      hallucination, unit alias, totals breach for `total_income`, `pat`, and
      `ebitda_margin`).
