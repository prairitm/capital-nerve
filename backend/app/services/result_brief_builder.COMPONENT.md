# services/result_brief_builder

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Backs `GET /v1/companies/{symbol}/result-brief`. Builds the analyst-shaped brief for one quarterly result.

## Source

- Path: `backend/app/services/result_brief_builder.py`
- Layer: backend-service

## Contract

- `build_result_brief(db, company: Company, period_label: str | None) -> ResultBrief | None`. Returns `None` when no `QUARTERLY_RESULT` event exists for the resolved period; the router converts that into a 404.

## Dependencies

- Imports: `sqlalchemy.select`, models (`CompanyEvent`, `IntelligenceCard`, `CalculatedMetric`, `MetricDefinition`, `CardEvidence`, `Company`, `FinancialPeriod`), helpers (`company_brief`, `period_brief`), schemas (`EvidenceItem`, `ResultBrief`, `ResultBriefPoint`, `ResultPeerComparison`), services (`HIGHLIGHT_METRIC_CODES`, `load_metric_comparisons`).

## Patterns (symmetry)

- Period resolution: `display_label` first, `fy_label` fallback. When the caller omits the period, the latest `QUARTERLY_RESULT` is used.
- `key_positives` / `key_negatives` are derived from the event's published cards by `signal_direction` — capped at 5 each. MIXED / NEUTRAL cards do not surface here.
- `peer_comparison` covers each metric in `HIGHLIGHT_METRIC_CODES`. Peer median uses `CalculatedMetric` rows for same-sector peers in the same period.
- `model_update_fields` is a flat `dict[str, float | str | None]` — Excel-friendly.

## Verification checklist

- [ ] Returns `None` (not raises) when the period has no result event
- [ ] `key_positives` / `key_negatives` capped at 5
- [ ] `peer_comparison.sample_size` excludes the query company itself
- [ ] Reuses `HIGHLIGHT_METRIC_CODES` and `load_metric_comparisons` from `card_context.py`
