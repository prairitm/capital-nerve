# `backend/app/schemas/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Pydantic v2 DTOs that define the wire shape of every API response and request body.

## Modules

- [`common.py`](common.py) — domain DTOs shared across routers: `CompanyBrief`, `PeriodBrief`, `CardBrief`, `CardDetail`, `EvidenceItem`, `CardMetricComparison`, `ConcernHeatmapRow`, `FinancialTrend`, `FinancialTrendPoint`, `FinancialSnapshotRow`, `DocumentBrief`, `TimelineEvent`, `CompanyBadge`, etc.
- [`auth.py`](auth.py) — `SignupRequest`, `LoginRequest`, `TokenResponse`, `UserResponse`.
- [`v1/`](v1/_BASE.md) — enterprise v1 API wire contract (`IntelligenceObject`, `EventBriefV1`, `SignalBriefV1`, portfolio / sector / peer / credit / retail / result-brief shapes). Additive on top of `common.py`; existing routers keep using `common.py`.

## Rules

- All schemas subclass `BaseModel`. Avoid dataclasses or `TypedDict`.
- Field names mirror the database / Python attribute names exactly. The frontend `api/types.ts` mirrors these names verbatim.
- `CardDetail` extends `CardBrief` via class inheritance — keep inheritance shallow (one level) and only when the detailed shape is a strict superset.
- Default values for optional lists/dicts use `[]` and `{}` so the JSON shape is stable for the frontend.
- Enums imported from [`../db/enums.py`](../db/enums.py) appear directly in field types (e.g. `signal_direction: SignalDirection | None`). Pydantic serializes them by value.
- Inline request models stay in the relevant router when they apply to only one endpoint (`IngestRequest`, `CreateWatchItem`, `UpdateReview`). Move them to `schemas/` only if reused.
- `UserResponse` uses `class Config: from_attributes = True` so it accepts an ORM `AppUser`. This is the only schema with that opt-in — other shapes are mapped explicitly via helpers.
- When adding a field to an existing DTO:
  1. Update this file.
  2. Update the mirroring TypeScript interface in [`../../../frontend/src/api/types.ts`](../../../frontend/src/api/types.ts).
  3. Update the helper in [`../routers/_helpers.py`](../routers/_helpers.py) if a `*_brief` builder is involved.
