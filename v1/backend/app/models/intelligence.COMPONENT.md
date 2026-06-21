# models/intelligence

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

The product's central abstraction: `MetricDefinition`, `CalculatedMetric`, `SignalDefinition`, `GeneratedSignal`, `IntelligenceCard`, `CardEvidence`. These are the "what the user sees" tables.

## Source

- Path: `backend/app/models/intelligence.py`
- Layer: backend-models

## Contract

- `MetricDefinition` — canonical metric codes (`revenue_yoy_growth`, `ebitda_margin`, ...) with formula text and unit metadata.
- `CalculatedMetric` — per-company-period metric values plus YoY changes (`change_absolute`, `change_percent`, `change_bps`). Unique on `(company_id, period_id, metric_def_id, comparison_type)`.
- `SignalDefinition` — rule library (signal code, name, category, optional rule text + rule JSON).
- `GeneratedSignal` — instances of a signal firing on a company/event/period with direction, severity, score, confidence.
- `IntelligenceCard` — what the UI renders: type, headline, summary, direction/severity/confidence, `card_priority` (spec §19), `metrics_json`, `calculations_json`, `evidence_json`, `display_context`.
- `CardEvidence` — per-card evidence rows pointing back to documents / extracted values / metrics.

## Dependencies

- Imports: SQLAlchemy primitives, `JSONB`, `Base`, enums (`ConfidenceLevel`, `SeverityLevel`, `SignalDirection`).

## Patterns (symmetry)

- `IntelligenceCard.card_type` is a string, not an enum, so new card types can be added without a migration. Add the matching label to `cardTypeLabel` in [`../../../frontend/src/lib/format.ts`](../../../frontend/src/lib/format.ts) and (if it should be tab-filtered) update [`../routers/cards.py`](../routers/cards.py).
- `CalculatedMetric.input_values` and `calculation_steps` are JSON blobs used by services to render the "why this fired" detail.
- `CardEvidence.card_id` cascades on delete (the only cascade in this module).
- `card_priority` reflects the spec §19 ranking — preserve the ordering when adding new cards.

## Verification checklist

- [ ] New card type added to `cardTypeLabel` and (if needed) the cards router tab Literal
- [ ] `card_priority` populated for new cards
- [ ] Unique constraint on `CalculatedMetric` preserved
- [ ] Cascade on `CardEvidence.card_id` preserved
- [ ] `__init__.py` updated when adding a model
