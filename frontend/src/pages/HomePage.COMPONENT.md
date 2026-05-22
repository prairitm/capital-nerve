# HomePage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Market intelligence feed at `/`. Renders a summary strip with feed-scope tabs and pulse counters, then a timeline of grouped cards.

## Source

- Path: `frontend/src/pages/HomePage.tsx`
- Route: `/`
- Layer: frontend-page

## Contract

- Data: `GET /v1/intelligence-objects/summary` (`FeedSummary`) and `GET /v1/intelligence-objects?feed=&tab=&limit=` (`IntelligenceObjectBrief[]`, adapted to `CardBrief` in-page).
- Local state: `feedScope` (`"all" | "watchlist" | "results"`), `pulseFilter` (nullable), `watchItemFor` (`CardBrief | null`).

## Dependencies

- May import: `react`, `@tanstack/react-query`, `lucide-react`, `@/api/client`, `@/api/types`, `@/components/cards/IntelligenceTimeline`, `@/components/cards/SaveWatchItemDialog`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/Empty`, `clsx`, `@/lib/cards`.
- Must not: hand-sort the cards (use `groupCardsByEvent` after `filterHomeFeedCards`).

## Patterns (symmetry)

- The `FEED_TABS` constant is the only place that lists feed scopes — keep it the source of truth.
- The two pulse filter sets (`WATCHLIST_PULSE`, `RESULTS_PULSE`) depend on `feedScope`. When you add a new pulse filter, add it to the matching set and to `TAB_COPY`.
- `resolveApiTab` translates `(feedScope, pulseFilter)` into the backend `tab` query param. Keep its return values aligned with the `Literal[...]` enum in [`backend/app/routers/v1/intelligence_objects.py`](../../../backend/app/routers/v1/intelligence_objects.py).
- React Query keys: `["feedSummary"]`, `["feed", feedScope, pulseFilter]`. Mutations from the watch-item dialog invalidate `["watchItems"]`.

## UI / UX

- Summary card lays the feed-scope tabs above the pulse filter row. Pulse appears only when `feedScope !== "all"`.
- Selected feed scope uses `btn-brand-active`. Selected pulse filter uses `bg-surface-2 ring-1 ring-line/80`.
- Empty state uses the shared `Empty` component with a `FileBarChart` icon.

## Verification checklist

- [ ] `useQuery` keys include all filter dimensions
- [ ] Feed rows open `/intelligence/:id` directly (no drawer on this page); watch-item dialog at page level
- [ ] Tab API resolution matches the backend `Literal` set
- [ ] `Empty` component used for the zero-state
- [ ] Cards are filtered through `filterHomeFeedCards(cards, resolveApiTab(...))` and grouped via `groupCardsByEvent`
- [ ] All / watchlist tabs only show cards with `signal_id`; Results pulse tabs may show verdict cards without a signal
