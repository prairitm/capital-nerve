# services/pipeline/guidance

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1c. Regex extractor for forward-guidance numbers in investor
presentations, concall transcripts, annual reports, and press releases.
Backstops the LLM extractor when `LLM_PROVIDER=mock`. Outputs feed the
`revenue_guidance_midpoint`, `revenue_guidance_revision_pct`,
`ebitda_margin_guidance_midpoint` metrics and the
`guidance_upgrade` / `guidance_downgrade` signals.

## Source

- Path: `backend/app/services/pipeline/guidance.py`
- Layer: backend-service

## Contract

- `is_guidance_document(document) -> bool` — gate (excludes `FINANCIAL_RESULT`
  and `EXCHANGE_FILING`).
- `run_guidance_extraction(db, *, document, event) -> int` — number of rows
  written. Each detected range produces two `ExtractedValue` rows:
  `<bucket>_lower` and `<bucket>_upper`.

## Dependencies

- May import: `app.models.{events,facts}`, `app.db.enums`.
- Must not import: LLM modules.

## Patterns (symmetry)

- Conservative regexes only — false positives create noisy guidance signals.
- When management states a point estimate, the LLM provider is responsible
  for producing matching `lower == upper` rows; the regex extractor
  intentionally only handles ranges.
- Adding a new guidance bucket: add the `LINE_ITEMS` row + `MetricDefinition`
  in [`seed_catalog.py`](../../seed/seed_catalog.py) **and** the regex here. The
  LLM prompt allow-list in [`llm.py`](llm.py) must include the same code.

## Verification checklist

- [ ] Re-runs do not duplicate guidance rows.
- [ ] Lower / upper rows always come in pairs.
- [ ] Documents without any matching phrase return 0, no crash.
- [ ] `unit` is always `%` when the source phrasing is a percentage.
