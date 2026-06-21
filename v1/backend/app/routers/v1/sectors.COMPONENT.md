# routers/v1/sectors

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`GET /v1/sectors/{sector_name}/signals` — cross-company signal roll-up scoped by sector.

## Source

- Path: `backend/app/routers/v1/sectors.py`
- Prefix: `/v1`
- Tags: `["v1: sectors"]`
- Layer: backend-router

## Endpoints

- `GET /v1/sectors/{sector_name}/signals?direction=&severity=&period=&limit=` (`response_model=SectorSignalsResponse`).

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select / func`, models (`GeneratedSignal`, `SignalDefinition`, `Company`, `Sector`, `FinancialPeriod`, `AppUser`), helpers (`company_brief`, `period_brief`), schemas (`SectorSignalRow`, `SectorSignalsResponse`).
- Must not: rely on `find_company` (this is a sector lookup, not a company lookup).

## Patterns (symmetry)

- Resolution falls back to a partial `ilike` match (so URLs like `/v1/sectors/IT/signals` match the seeded sector "IT Services").
- `company_count` uses a `SELECT count(...)` against `Company.sector_id` — do not infer from the signals list.
- Ordering: `signal_score DESC NULLS LAST, created_at DESC` (matches `/v1/signals`).

## Verification checklist

- [ ] Sector resolved with exact match first, then partial `ilike`
- [ ] `company_count` from a real query, not from the signal list
- [ ] `signal_count == len(signals)` after filters
- [ ] Optional filters threaded through
