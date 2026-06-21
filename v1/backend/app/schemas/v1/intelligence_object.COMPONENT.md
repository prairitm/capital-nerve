# schemas/v1/intelligence_object

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

The canonical decision-ready payload for the entire v1 namespace. Every renderer — frontend drawer, alert email, API client, Excel plugin, LLM tool — reads this shape so the same intelligence can be surfaced across channels without re-implementing the join.

## Source

- Path: `backend/app/schemas/v1/intelligence_object.py`
- Layer: backend-schemas

## Contract

- `IntelligenceObject` — full payload returned by `GET /v1/intelligence-objects/{id}`. Carries `company`, `event`, `signal`, `metrics`, `metric_comparisons`, `calculation`, `evidence`, `display`, `suggested_actions`, plus derived fields `importance_score`, `time_horizon`, `investor_relevance`, `confidence`.
- `IntelligenceObjectBrief` — compact row used by list endpoints (`GET /v1/intelligence-objects`, `GET /v1/companies/{symbol}/intelligence-objects`) and embedded inside `PortfolioAlert.top_objects`. Includes `event_type` alongside `event_title` / `event_date` so feed headers can show document type without parsing titles. Also carries `document_id` + `source_label` so feed rows can render a one-click PDF jump chip without joining `SourceDocument` on the frontend.
- `CalculationChain` (+ `CalculationChainSignal`, `CalculationChainMetric`, `CalculationChainInput`) — structured "why this fired" payload attached to every `IntelligenceObject`. Mirrors the value → metric → signal → card pipeline; each input carries `document_id`, `page_number`, and `source_text` so a panel can render the formula with one-click verification.
- `IODisplayConfig` — `(layout, primary_metric, chart_type, cta, surfaces)`. Sourced from `intelligence_cards.display_context` plus card-type defaults derived in the builder.
- `IOMetric` — `(name, value, unit)`. One row per entry in `intelligence_cards.metrics_json`.

## Dependencies

- May import: `pydantic`, [`../../db/enums.py`](../../db/enums.py), [`../common.py`](../common.py) (`CompanyBrief`, `PeriodBrief`, `EvidenceItem`, `CardMetricComparison`), [`./events.py`](events.py) (`EventBriefV1`), [`./signals.py`](signals.py) (`SignalBriefV1`).
- Must not: import ORM models, routers, or other services. The build logic lives in [`../../services/intelligence_object_builder.py`](../../services/intelligence_object_builder.py).

## Patterns (symmetry)

- `intelligence_object_id` mirrors the underlying `intelligence_cards.card_id`. Do not invent a separate identifier — every IO is a card and vice versa.
- `importance_score` is a normalized clamp of `card_priority` to `0–100`. Renderers should rank by `importance_score` (not `card_priority`).
- `status` is the SignalDirection. Pair colour with label using `SignalBadge` — never colour alone (spec §11).
- `display.primary_metric` is a stringified `"value unit"` (e.g. `"180 bps"`). Renderers can fall back to `metrics[0]` if it is null.

## Verification checklist

- [ ] New field added here is also added to the TS `IntelligenceObject` in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts)
- [ ] `IntelligenceObjectBrief` carries every field a list consumer needs to rank / filter — heavier fields (`evidence`, `calculation`, `metrics`) live only on `IntelligenceObject`
- [ ] `IODisplayConfig.layout` defaults to `"metric_comparison"` so renderers always have a fallback
- [ ] Default collections use `[]` / `{}`
