# services/pipeline/cards

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 5 — the user-visible layer. Turns each `GeneratedSignal` into an
`IntelligenceCard` + `CardEvidence` row set so the home feed, drawer, and `/v1`
intelligence objects all surface ingested data identically to the seeded data.

## Source

- Path: `backend/app/services/pipeline/cards.py`
- Layer: backend-service

## Contract

- `run_cards(db, *, document, signals, publish) -> list[IntelligenceCard]`.
- `publish` controls `IntelligenceCard.is_published`; the runner sets it from
  the overall extraction confidence vs `AUTO_PUBLISH_CONFIDENCE`.

## Dependencies

- May import: `app.models.intelligence`, `app.models.facts`, `app.models.events`.
- Must not import: LLM modules.

## Patterns (symmetry)

- `card_type` map mirrors the seed's vocabulary
  (`margin_movement`, `growth_signal`, `profit_quality`, `earnings_quality`,
  `cash_quality`, `cashflow_signal`, `working_capital`, `cost_pressure`,
  `debt_signal`, `solvency_signal`, `valuation_signal`, `market_reaction`,
  `governance_signal`, `guidance_signal`, `order_book`, `management_tone`,
  `red_flag`) so feed colour/badge logic in the frontend keeps working
  unchanged. The same vocabulary is mirrored in
  [`frontend/src/lib/format.ts::cardTypeLabel`](../../../../frontend/src/lib/format.ts).
- Every card gets:
  - one `CardEvidence(evidence_type="calculated_metric")` row pointing at the
    primary `CalculatedMetric`,
  - one `CardEvidence(evidence_type="source_quote")` per `ExtractedValue` that
    fed the metric inputs — keeps the drawer's evidence panel populated.
    Formula variable names (`s`, `now`, `revenue`, …) are resolved through
    `MetricDefinition.inputs_json` (`name` → `code`, `CURRENT` scope only).
- `metrics_json` always carries the primary metric in the first slot. The
  drawer reads `metrics_json[0]` for the hero badge — do not reorder.
- `card_priority` is set from severity using the same weights the seed uses.

## Verification checklist

- [ ] Re-runs delete previous cards + evidence for the document before insert.
- [ ] Every card has at least one `CardEvidence` row (calculated_metric).
- [ ] `confidence_level` is derived from `confidence_score` via the standard
      thresholds (HIGH ≥ 85, MEDIUM ≥ 65, LOW ≥ 40, else NEEDS_REVIEW).
- [ ] `display_context.primary_metric` is present when a primary metric exists.
