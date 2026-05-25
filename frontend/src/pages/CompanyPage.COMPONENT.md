# CompanyPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Company hub at `/company/:symbol`. Verdict-first layout: identity + actions, latest quarterly view (badges, summary, main issue / watch next), recent events timeline, key intelligence cards, documents; sidebar with signals, financial snapshot, and trends.

## Source

- Path: `frontend/src/pages/CompanyPage.tsx`
- Route: `/company/:symbol`
- Layer: frontend-page

## Contract

- Data: `GET /companies/:symbol` (`CompanyDetail`).
- Secondary: `GET /v1/companies/:symbol/signals` (up to 6 rows for sidebar).
- Mutations: add/remove watchlist (`POST /watchlist/companies`, `DELETE /watchlist/companies/:companyId`).
- `top_cards` open via `IntelligenceCard` → `/intelligence/:cardId` (no drawer).

## Dependencies

- May import: `react`, `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`, `@/api/client`, `@/api/types`, `@/components/cards/IntelligenceCard`, `@/components/cards/MetricSparkline`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SignalBadge`, `@/components/common/SeverityBadge`, `@/lib/cards` (`filterInsightListCards`), `@/lib/format`.
- Must not: duplicate `MetricSparkline` — use the shared component for trend charts.

## Patterns (symmetry)

- Query keys: `["company", symbol]`, `["companySignals", symbol]`.
- `top_cards` filtered with `filterInsightListCards` before render.
- Latest verdict uses `latest_event_id` to resolve timeline row for badges / `mainIssueLabel`.
- Timeline shows 4 events by default; **View all** opens [`CompanyEventsPage`](CompanyEventsPage.tsx) at `/company/:symbol/events`.
- Documents show 4 by default; top-right control expands to full list.
- Snapshot rows highlighted when badge label maps via `BADGE_SNAPSHOT_CODES`.
- Tone map for dimension badges → `chip-*` classes.

## UI / UX

- `xl:grid-cols-3`: main column = timeline, intelligence, documents; sidebar = signals, snapshot, trends.
- Market price/mcap de-emphasized to a single muted line under company meta.
- Recent-events timeline uses `CompanyQuarterTimeline` (4 most recent quarters); `latest_event_id` highlights the verdict row and drives the quarterly strip above.

## Verification checklist

- [ ] Query key includes the symbol
- [ ] Watchlist mutations invalidate `["company", symbol]` and `["watchlist"]`
- [ ] `top_cards` navigate to `/intelligence/:cardId` on click
- [ ] Snapshot YoY tone: positive / negative / mute
- [ ] Timeline capped at 4; View all links to `/company/:symbol/events`
- [ ] Documents capped at 4 until expanded
- [ ] `MetricSparkline` used for trends (not inline recharts)
