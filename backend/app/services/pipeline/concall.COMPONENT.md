# services/pipeline/concall

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Stage 1d. Lexicon-based scoring of concall transcripts. For Management-Tone
cards we need numeric scores the metric engine can compare quarter-over-
quarter; ML-grade sentiment is overkill for V1. Word counts on a small
lexicon, normalised to 0..100, written as `ExtractedValue` rows so the
engine treats them like any other fact.

## Source

- Path: `backend/app/services/pipeline/concall.py`
- Layer: backend-service

## Contract

- `is_concall_document(document) -> bool` — gate; runs only when
  `DocumentType.CONCALL_TRANSCRIPT`.
- `run_concall_scoring(db, *, document, event) -> int` — returns axes
  written (one row per axis).
- Axes (`normalized_code` written into `ExtractedValue`):
  `concall_confidence_score`, `concall_uncertainty_score`,
  `concall_evasive_score`, `concall_demand_score`,
  `concall_cost_pressure_score`, `concall_pricing_power_score`.

## Dependencies

- May import: `app.models.{events,facts}`, `app.db.enums`.
- Must not import: LLM modules.

## Patterns (symmetry)

- Output is on the same surface as financial extraction; the metric engine's
  `management_confidence_score`, `management_uncertainty_score`, and
  `management_confidence_change_qoq` (PQ-scope) read these values.
- Lexicons are module constants for now — moving them to a JSON config in
  [`backend/app/seed/`](../../seed/) is a follow-up so analysts can iterate
  without code review.
- Scores are not comparable across companies — only QoQ / YoY deltas. Keep
  this contract or downstream signals will misfire.

## Verification checklist

- [ ] Each axis writes exactly one `ExtractedValue` per run.
- [ ] Score is clamped to `[0, 100]`.
- [ ] Source-text excerpt points back at a page that contains the lexicon
      hit (drawer evidence cites the right page).
- [ ] Empty transcript (no text) → 0 rows, no crash.
