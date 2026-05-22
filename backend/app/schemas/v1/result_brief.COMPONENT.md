# schemas/v1/result_brief

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Wire shape for `GET /v1/companies/{symbol}/result-brief?period=` — sell-side analyst briefing on one quarterly result.

## Source

- Path: `backend/app/schemas/v1/result_brief.py`
- Layer: backend-schemas

## Contract

- `ResultBriefPoint` — `(title, detail, metric_code, value, unit)`. One bullet point.
- `ResultPeerComparison` — `(metric_code, metric_name, company_value, peer_median, rank, sample_size, unit)`.
- `ResultBrief` — `(company, period, event_id, headline, overall_verdict, key_positives, key_negatives, model_update_fields, peer_comparison, metric_comparisons, source_evidence)`.

## Dependencies

- May import: `pydantic`, [`../common.py`](../common.py) (`CompanyBrief`, `PeriodBrief`, `CardMetricComparison`, `EvidenceItem`).
- Must not: import ORM models.

## Patterns (symmetry)

- `model_update_fields` is a flat dict so it can drop into an Excel model row without renaming. Keys are metric codes; values are scalars (number or string).
- `key_positives` / `key_negatives` are sliced from cards by `signal_direction` (`POSITIVE` / `NEGATIVE`). MIXED / NEUTRAL cards do not surface here — they appear in the underlying event detail instead.
- `peer_comparison.rank` is 1-based among the sector cohort (smaller is better when the metric is desirable).

## Verification checklist

- [ ] Mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] `key_positives` / `key_negatives` each capped at 5 entries in the service
- [ ] `peer_comparison.sample_size` is the count of peer values used (not including the company itself)
