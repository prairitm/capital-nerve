# event_timeline

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Pick a single canonical `CompanyEvent` per financial period for hub and timeline UIs so multiple ingested assets (results, concall, deck) do not crowd out older quarters behind a row limit.

## Source

- Path: `backend/app/services/event_timeline.py`
- Layer: backend-service

## Contract

- `pick_canonical_per_period(events: list[CompanyEvent]) -> list[CompanyEvent]` — input should already be filtered/sorted by caller; output is newest-first with at most one row per `period_id`.

## Dependencies

- May import: `CompanyEvent`, `EventType`.
- Must not: touch the database or mutate input rows.

## Patterns (symmetry)

- Type priority: `QUARTERLY_RESULT` → `ANNUAL_REPORT` → `INVESTOR_PRESENTATION` → `CONCALL_TRANSCRIPT` → other filing types.
- Tie-break on equal priority: later `event_date`, then higher `event_id`.

## Verification checklist

- [ ] Three events on the same `period_id` collapse to the quarterly result when present.
- [ ] Events with `period_id is None` are all retained.
- [ ] Output order is `event_date DESC`, `event_id DESC`.
