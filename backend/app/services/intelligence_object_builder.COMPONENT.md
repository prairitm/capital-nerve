# services/intelligence_object_builder

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Single derivation point for the v1 `IntelligenceObject` shape. Every v1 router that returns an IO goes through this module so derived fields (`importance_score`, `time_horizon`, `investor_relevance`, `suggested_actions`, `display`) are computed in one place.

## Source

- Path: `backend/app/services/intelligence_object_builder.py`
- Layer: backend-service

## Contract

- `build_intelligence_object(db, card, company, period, event, document) -> IntelligenceObject` — full join including evidence rows and metric comparisons.
- `build_intelligence_object_brief(card, company, period, event) -> IntelligenceObjectBrief` — lighter projection for list endpoints (no evidence / metric comparison / signal join).

Module-level mappings (treat as product rules):

- `_LAYOUT_BY_CARD_TYPE` — default `display.layout` per card type.
- `_CHART_BY_CARD_TYPE` — default `display.chart_type` per card type.
- `_CTA_BY_CARD_TYPE` — default `display.cta` per card type.
- `_LONG_TERM_TYPES`, `_SHORT_TERM_TYPES` — drive `time_horizon`.
- `_RELEVANCE_BY_CARD_TYPE` — drive `investor_relevance` tags.

## Dependencies

- Imports: `sqlalchemy.select`, models (`CardEvidence`, `CompanyEvent`, `GeneratedSignal`, `IntelligenceCard`, `SignalDefinition`, `SourceDocument`, `Company`, `FinancialPeriod`), helpers (`build_source_label`, `company_brief`, `period_brief`), schemas (`EvidenceItem`, `EventBriefV1`, `IntelligenceObject`, `IntelligenceObjectBrief`, `IODisplayConfig`, `IOMetric`, `SignalBriefV1`), services (`load_metric_comparisons`, `load_concall_heatmap`, `load_trend_sparklines`, `should_show_concall`).
- Must not: raise `HTTPException`, write to the DB, or accept request objects.

## Patterns (symmetry)

- `importance_score = clamp(card_priority, 0, 100)`. Renderers should rank by this, never the raw `card_priority`.
- `display.primary_metric` falls back to `metrics[0]` rendered as `"value unit"` when `display_context` does not supply one.
- `suggested_actions` is product-driven. To add an action: extend the per-card-type branch and add the verb to the frontend mapping if it needs a human label.

## Verification checklist

- [ ] Returns `IntelligenceObject` / `IntelligenceObjectBrief` Pydantic models — never `dict`
- [ ] All five derived fields (`importance_score`, `time_horizon`, `investor_relevance`, `suggested_actions`, `display`) are populated in both the brief and the full builder when applicable
- [ ] No `HTTPException` raised here — return what can be computed; callers handle 404s
- [ ] `_normalize_importance` clamps to `0–100`
