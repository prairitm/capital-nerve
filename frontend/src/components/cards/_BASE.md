# `frontend/src/components/cards/` baseline

> Inherits: [../../_BASE.md](../../_BASE.md)

Components in this folder render the intelligence-card domain — feed items, full cards, detail drawer, timelines, sparklines, and the watch-item save dialog. The shape of a card on screen is the product's central abstraction.

## Domain rules

- Cards always show: type label, headline, one-line summary, **tone** (signal direction), optional **materiality**, optional confidence. The visual order in [`IntelligenceCard.tsx`](IntelligenceCard.tsx) and [`IntelligenceFeedItem.tsx`](IntelligenceFeedItem.tsx) is the canonical reference — match it when adding new card surfaces.
- Card colours follow spec §11: [`SignalBadge`](../common/SignalBadge.tsx) and [`SeverityBadge`](../common/SeverityBadge.tsx) / [`MaterialityBadge`](../common/MaterialityBadge.tsx) from [`../common/`](../common/) are the only sources of truth for the colour-plus-label pairing. Do not roll your own coloured pill.
- **Tone vs materiality.** Backend keeps `SignalDirection` (`POSITIVE/NEGATIVE/MIXED/NEUTRAL`) and `SeverityLevel` (`LOW/MEDIUM/HIGH/CRITICAL`). The UI surfaces them as two distinct chips: **Tone** (Positive / Negative / Mixed / Neutral) and **Materiality** (Routine / Notable / Material / Market-moving). Never combine into a single contradictory label like "Critical-risk — Positive".
- Feed ranking respects `card_priority` (spec §19). Sorting / grouping logic for feeds lives in [`@/lib/cards`](../../lib/cards.ts) — do not sort cards by hand inside components.
- The `watch_next` card type is filtered out of insight lists via `filterInsightListCards` (see [`@/lib/cards`](../../lib/cards.ts)).

## Props shape

- Top-level props are typed via a local `interface Props { ... }`. Avoid inlining large object types in the function signature.
- Card-list components accept:
  - `card: CardBrief` (or `groups: TimelineCardGroup[]` for the timeline)
  - `onOpen: (cardId: number) => void`
  - optional `onSaveWatchItem?: (card: CardBrief) => void`
  - optional `showCompany?: boolean` — defaults to `true`; set `false` when the company is already in a parent header (event detail, signal detail).

## Data fetching

- Presentational cards (`IntelligenceCard`, `IntelligenceFeedItem`, `IntelligenceTimeline`, `MetricSparkline`) receive data through props and never call `api()`.
- Smart components that need to fetch on open (`CardDetailDrawer`, `SaveWatchItemDialog`) use `useQuery` / `useMutation` and call `api<T>()` from [`@/api/client`](../../api/client.ts).

## Interaction & accessibility

- A clickable card uses `<article role="button" tabIndex={0} onClick={...} onKeyDown={...}>` and nested buttons call `e.stopPropagation()` (pattern in `IntelligenceCard.tsx`).
- The detail drawer (`CardDetailDrawer.tsx`) closes on Escape and on backdrop click. Mobile uses a bottom-sheet width via Tailwind responsive classes.

## Styling

- Reuse `.card`, `.card-2`, `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.chip-*`, `.num` from [`@/styles.css`](../../styles.css). Numbers use `font-variant-numeric: tabular-nums` via the `.num` class.
- Chart components keep recharts styling in line with the dark theme tokens — see `MetricSparkline.tsx`.
