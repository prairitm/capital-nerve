# CompanyEventsPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Full event timeline for one company at `/company/:symbol/events`.

## Source

- Path: `frontend/src/pages/CompanyEventsPage.tsx`
- Route: `/company/:symbol/events`
- Layer: frontend-page

## Contract

- Data: `GET /v1/companies/:symbol` (company header) and `GET /v1/companies/:symbol/events?limit=200&dedupe_periods=false` (all filings, grouped by quarter in UI).
- Back control at top returns to `/company/:symbol`.

## Dependencies

- May import: `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`, `@/api/client`, `@/api/types`, badges, `@/components/common/Spinner`, `@/lib/format`.

## Patterns (symmetry)

- Renders [`CompanyQuarterTimeline`](../components/common/CompanyQuarterTimeline.tsx): one section per `period.display_label`, nested rows per filing type (results, concall, deck).
- Timeline order: newest quarter first; within a quarter, quarterly result before other types.

## Verification checklist

- [ ] Query key `["company", symbol]`
- [ ] Each row navigates to `/company/:symbol/event/:eventId`
- [ ] Empty state when `timeline` is empty
