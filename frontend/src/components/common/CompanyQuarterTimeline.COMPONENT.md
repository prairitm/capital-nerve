# CompanyQuarterTimeline

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Render a company’s events grouped by reporting quarter (newest first), with filing-type rows nested under each quarter header.

## Source

- Path: `frontend/src/components/common/CompanyQuarterTimeline.tsx`
- Layer: frontend-component

## Contract

- Props: `events` (`QuarterTimelineEvent[]`), `symbol`, optional `latestEventId`, `collapsible` (default true), `summaryLineClamp` (default false).
- Uses `groupEventsByQuarter` from `@/lib/cards`.
- Each row navigates to `/company/:symbol/event/:eventId`.

## Dependencies

- May import: `react-router-dom`, `lucide-react`, `clsx`, badges, `@/lib/cards`, `@/lib/format`.
- Must not: fetch data.

## UI / UX

- Quarter headers: `group.label` from `groupEventsByQuarter` — always a period like `Q4 FY2025-26`, never company name or document type.
- Latest quarter header uses `bg-surface-2/60`; collapsible sections when more than one quarter (chevron, latest expanded by default).
- Nested timeline uses `border-l` + `ui-dot` per filing row.
- Each filing row: muted uppercase date only on the meta line; title line is `eventTypeTitle` (document type), not `event_title`.

## Verification checklist

- [ ] Events with the same `period.period_id` share one quarter section
- [ ] `QUARTERLY_RESULT` rows appear before concall / deck rows within a quarter
- [ ] `latestEventId` highlights the matching row’s dot
