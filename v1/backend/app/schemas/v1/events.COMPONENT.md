# schemas/v1/events

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed event projections for the v1 timeline endpoints. Replaces the ad-hoc dicts returned by [`../../routers/events.py`](../../routers/events.py) for v1 callers.

## Source

- Path: `backend/app/schemas/v1/events.py`
- Layer: backend-schemas

## Contract

- `EventBriefV1` — compact row used by `GET /v1/companies/{symbol}/events` and as the nested `IntelligenceObject.event`. Carries enums (`EventType`, `SignalDirection`, `SeverityLevel`, `ConsolidationType`), `overall_confidence: float | None`, and the optional embedded `company` + `period`.
- `EventDetailV1` (extends `EventBriefV1`) — adds `main_issue`, `watch_next`, `audit_status`, `raw_facts: list[EventRawFacts]`, `documents: list[DocumentBrief]`, and a flat `metric_snapshot: dict[str, Any]` for renderers that just want headline numbers.
- `EventRawFacts` — `(line_item_code, line_item_name, value, unit, period_value_type, consolidation)`. Sourced from `financial_statement_facts`.

## Dependencies

- May import: `pydantic`, [`../../db/enums.py`](../../db/enums.py), [`../common.py`](../common.py) (`CompanyBrief`, `PeriodBrief`, `DocumentBrief`).
- Must not: import ORM models or routers/services.

## Patterns (symmetry)

- `EventBriefV1` is the embeddable shape (small, no facts/documents). `EventDetailV1` extends it with the heavier collections — keep the inheritance one level.
- `raw_facts` is sourced from `financial_statement_facts` rows where `period_value_type == 'CURRENT'`. Comparison rows belong on `CalculatedMetric` and surface through `IntelligenceObject.metric_comparisons`.

## Verification checklist

- [ ] New field mirrored in [`../../../../frontend/src/api/types.ts`](../../../../frontend/src/api/types.ts) (`EventBriefV1` / `EventDetailV1`)
- [ ] `EventDetailV1` strict superset of `EventBriefV1`
- [ ] Default collections use `[]` / `{}`
