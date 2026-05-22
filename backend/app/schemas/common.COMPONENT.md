# schemas/common

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Shared Pydantic response DTOs used by multiple routers.

## Source

- Path: `backend/app/schemas/common.py`
- Layer: backend-schemas

## Contract

Models defined here include:

- Identity: `CompanyBrief`, `PeriodBrief`, `CompanyBadge`.
- Card: `CardBrief`, `CardDetail` (extends `CardBrief`), `CardMetric`, `EvidenceItem`, `CardMetricComparison`.
- Concall: `ConcernHeatmapRow`.
- Financials: `FinancialTrendPoint`, `FinancialTrend`, `FinancialSnapshotRow`.
- Documents: `DocumentBrief`.
- Timeline: `TimelineEvent`.

The full Pydantic source remains authoritative — keep new fields here in sync with the frontend `api/types.ts`.

## Dependencies

- Imports `pydantic.BaseModel`, the enums in [`../db/enums.py`](../db/enums.py).
- Must not: import models, routers, or services — these schemas are the wire contract and stay decoupled from the ORM.

## Patterns (symmetry)

- Field names match ORM attribute names where possible so `_helpers.card_brief` and friends are obvious mappings.
- `CardDetail` extends `CardBrief` and adds detailed fields (`detailed_explanation`, `investor_question`, `action_label`, `calculations_json`, `evidence`, `event_summary`, `event_main_issue`, `metric_comparisons`, `trend_sparklines`, `concern_heatmap`). Keep inheritance shallow.
- Optional list fields default to `[]` so the wire shape is stable for the frontend.
- Do not add `class Config: from_attributes = True` here — explicit mapping via `_helpers.py` is the convention.

## Verification checklist

- [ ] Field added here is also added to the frontend `api/types.ts`
- [ ] The matching `_helpers` builder updated (`company_brief`, `card_brief`, ...)
- [ ] Enums imported from `app.db.enums`
- [ ] Default lists/dicts use `[]` / `{}` (not `None`)
