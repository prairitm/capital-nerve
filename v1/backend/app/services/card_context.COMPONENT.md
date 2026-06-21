# services/card_context

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Read-side helpers that turn a card and its company/period/event context into the rich detail the drawer renders: metric comparisons, trend sparklines, and concall heatmaps.

## Source

- Path: `backend/app/services/card_context.py`
- Layer: backend-service

## Contract

- `load_metric_comparisons(db, company_id, period_id, event_id, card_type) -> list[CardMetricComparison]`
- `load_trend_sparklines(db, company_id, period_id) -> list[FinancialTrend]`
- `load_concall_heatmap(db, event_id) -> list[ConcernHeatmapRow]`
- `should_show_concall(card, event) -> bool`

Module-level constants:

- `CONCALL_CARD_TYPES = {"management_tone", "guidance_tracker", "analyst_concern"}` — drives `should_show_concall`.
- `TREND_LINE_CODES` — canonical 3-metric trend trio.
- `HIGHLIGHT_METRIC_CODES` — preferred order for metric comparisons in the drawer.

## Dependencies

- Imports: `sqlalchemy.select`, `app.db.enums.EventType`, models (`CompanyEvent`, `AnalystQuestion`, `FinancialLineItemDefinition`, `FinancialStatementFact`, `CalculatedMetric`, `IntelligenceCard`, `MetricDefinition`, `FinancialPeriod`), schemas (`CardMetricComparison`, `ConcernHeatmapRow`, `FinancialTrend`, `FinancialTrendPoint`).

## Patterns (symmetry)

- Functions accept primitives (ids) plus a `Session`. They are pure reads and return Pydantic objects.
- `HIGHLIGHT_METRIC_CODES` is the ordering used by the drawer's "YoY & calculated metrics" table — add new codes here when introducing a new highlight metric.
- `should_show_concall` keeps concall heatmaps out of non-concall cards even when the event has analyst data.
- `TREND_LINE_CODES` is duplicated with `companies.company_detail`'s snapshot codes for a reason — sparkline display and snapshot table can diverge intentionally.

## Verification checklist

- [ ] New highlight metric added to `HIGHLIGHT_METRIC_CODES`
- [ ] Concall behaviour driven by `should_show_concall` (no inline card-type check)
- [ ] Service returns Pydantic objects (not raw dicts)
- [ ] No `HTTPException` here — return empty list when data is missing
- [ ] `previous_value` on comparisons resolves via prior-period `CalculatedMetric` (same `metric_def_id`) or legacy `input_values` anchors (`margin_lyq`, etc.)
