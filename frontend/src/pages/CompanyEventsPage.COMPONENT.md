# CompanyEventsPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Full event timeline for one company at `/company/:symbol/events`.

## Source

- Path: `frontend/src/pages/CompanyEventsPage.tsx`
- Route: `/company/:symbol/events`
- Layer: frontend-page

## Contract

- Data: `GET /companies/:symbol` (`CompanyDetail.timeline`).
- Back control at top returns to `/company/:symbol`.

## Dependencies

- May import: `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`, `@/api/client`, `@/api/types`, badges, `@/components/common/Spinner`, `@/lib/format`.

## Patterns (symmetry)

- Timeline row UI matches [`CompanyPage.tsx`](CompanyPage.tsx); summaries are not line-clamped on this page.
- Timeline order matches company page (newest-first); first row highlighted as most recent by date.

## Verification checklist

- [ ] Query key `["company", symbol]`
- [ ] Each row navigates to `/company/:symbol/event/:eventId`
- [ ] Empty state when `timeline` is empty
