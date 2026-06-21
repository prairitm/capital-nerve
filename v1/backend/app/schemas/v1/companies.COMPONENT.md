# schemas/v1/companies

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed v1 schema for the company hub payload returned by
`GET /v1/companies/{symbol}`. Replaces the legacy `dict[str, Any]` blob.

## Source

- Path: `backend/app/schemas/v1/companies.py`
- Layer: backend-schema (v1)

## Contract

- `CompanyHubV1` fields:
  - `company: CompanyBrief`
  - `watchlist_status: bool`
  - `badges: list[CompanyBadge]`
  - `latest_event_id: int | None`
  - `latest_period: PeriodBrief | None`
  - `latest_summary: str | None`
  - `main_issue: str | None`
  - `watch_next: str | None`
  - `top_objects: list[IntelligenceObjectBrief]`
  - `financial_snapshot: list[FinancialSnapshotRow]`
  - `trends: list[FinancialTrend]`
  - `timeline: list[TimelineEvent]`
  - `documents: list[DocumentBrief]`

## Dependencies

- May import: `app.schemas.common` and `app.schemas.v1.intelligence_object`.
- Must not: import `app.models` (schemas stay ORM-free) or define embedded
  enums duplicated from `app.db.enums`.

## Patterns (symmetry)

- The `top_objects` list uses the canonical `IntelligenceObjectBrief`
  shape from `schemas.v1.intelligence_object` — do not redefine it here.
- `trends` mirrors the legacy 8-quarter sparkline shape so the frontend
  chart components keep their existing prop types.

## Verification checklist

- [ ] All optional fields default to `None` or empty list.
- [ ] No `Any` types creep in — every field is fully typed.
- [ ] Exported from `app.schemas.v1.__init__`.
