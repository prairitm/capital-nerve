# SearchPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Full search results page at `/search?q=...`. Returns sectioned results for companies, intelligence cards, and events (not raw documents).

## Source

- Path: `frontend/src/pages/SearchPage.tsx`
- Route: `/search`
- Layer: frontend-page

## Contract

- Data: `GET /search?q=` (`SearchResult`).
- Query string `q` is the canonical state; the input syncs to it via `useSearchParams`.

## Dependencies

- May import: `react`, `react-router-dom` (`Link`, `useSearchParams`), `@tanstack/react-query`, `lucide-react` (`Search`), `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SignalBadge`, `@/components/common/SeverityBadge`.
- Must not: persist the search term anywhere else (no `localStorage`).

## Patterns (symmetry)

- The submit form sets `?q=...`; the input local state syncs from `?q=` via `useEffect`.
- Query key: `["search", q]`. Disabled when `q.length === 0`.
- Result sections: Companies → Cards → Events (matches the `TopSearch` dropdown order). When all three are empty, render the "No matches." card.
- Card anchors use `id="card-${c.card_id}"` so `TopSearch` deep-linking (`#card-...`) works.

## UI / UX

- The example list shown when `q.length === 0` is a `.card p-6 text-sm text-ink-mute` block — keep the format if you change the examples.
- Cards section uses `grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3`.

## Verification checklist

- [ ] `q` round-trips through URL search params
- [ ] React Query is disabled when `q.length === 0`
- [ ] Result sections match the `TopSearch` order
- [ ] Card anchors include `id="card-:cardId"` for deep links
