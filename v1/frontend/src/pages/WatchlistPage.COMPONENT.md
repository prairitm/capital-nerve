# WatchlistPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

User watchlist at `/watchlist`. Header shows summary stats (tracked, new events, negative, positive, red flags), followed by tracked companies, followed by watch items (thesis monitors).

## Source

- Path: `frontend/src/pages/WatchlistPage.tsx`
- Route: `/watchlist`
- Layer: frontend-page

## Contract

- Data: `GET /watchlist` (`WatchlistResponse`) and `GET /watch-items` (`WatchItem[]`).
- Mutations: `DELETE /watchlist/companies/:companyId` and `DELETE /watch-items/:id`.

## Dependencies

- May import: `react-router-dom` (`useNavigate`), `@tanstack/react-query`, `lucide-react` (`Trash2`), `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SignalBadge`, `@/components/common/SeverityBadge`, `@/components/common/Empty`.
- Must not: render the save-watch-item dialog here (creation flow lives on Home / Event / Signal pages).

## Patterns (symmetry)

- React Query keys: `["watchlist"]`, `["watchItems"]`. Mutations invalidate the matching key.
- Stats use the local `Stat` subcomponent with optional `tone="positive" | "negative"`.
- Watchlist card click navigates to `/company/:symbol`; the trash button stops propagation.
- Empty state uses the shared `Empty` component with a "Browse companies" action.

## UI / UX

- Stats grid: `grid grid-cols-2 sm:grid-cols-5 gap-2`.
- Company cards: `card p-4 cursor-pointer hover:border-line-strong hover:bg-surface-2/50` with keyboard activation on Enter / Space.
- Watch items section appears only when `watchItemsQ.data?.length > 0`.

## Verification checklist

- [ ] Both queries (`watchlist`, `watchItems`) keyed separately
- [ ] Mutations invalidate the matching key
- [ ] Trash button stops event propagation
- [ ] Uses `Empty` for the zero-state with a "Browse companies" CTA
- [ ] Signal + severity badges reused on the company card
