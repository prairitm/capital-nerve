# SignalsPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Signal screener at `/signals`. Filters by category (chips), severity, and direction. Renders a table on desktop and a card list on mobile. Each row links to the signal detail page.

## Source

- Path: `frontend/src/pages/SignalsPage.tsx`
- Route: `/signals`
- Layer: frontend-page

## Contract

- Data: `GET /signals?category=&severity=&direction=` (`SignalRow[]`).
- Filter state lives in the URL via `useSearchParams`.

## Dependencies

- May import: `react`, `react-router-dom`, `@tanstack/react-query`, `clsx`, `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SignalBadge`, `@/components/common/SeverityBadge`.
- Must not: persist filters to `localStorage`. URL is the only source of truth.

## Patterns (symmetry)

- The three constant arrays `CATEGORIES`, `SEVERITIES`, `DIRECTIONS` are the source of truth for the chips/selects. Add new filter values here only.
- React Query key: `["signals", category, severity, direction]`.
- Filter updates use a single `setParam(key, value)` helper that toggles between set/delete.
- Row click navigates to `/signals/:signalId`.

## UI / UX

- Desktop: `.card hidden md:block overflow-x-auto` with a `<table>` whose rows have `hover:bg-surface-2/50 cursor-pointer`.
- Mobile: `md:hidden grid grid-cols-1 gap-2` of `.card p-4` buttons.
- Selected chip: `btn-brand-active`. Unselected chip: `border-line text-ink-mute hover:text-ink hover:bg-surface`.

## Verification checklist

- [ ] Filters round-trip through URL search params
- [ ] React Query key includes all three filter dimensions
- [ ] Both desktop table and mobile card list render the same data
- [ ] Empty state uses an inline `.card p-8 text-sm text-ink-mute text-center` message (acceptable variant of `Empty`)
- [ ] No `localStorage` for filters
