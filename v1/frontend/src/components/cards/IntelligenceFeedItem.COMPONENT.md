# IntelligenceFeedItem

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Feed-density row for a `CardBrief`. Used inside `IntelligenceTimeline` when `variant="feed"` (the default on Home). Slightly tighter than `IntelligenceCard`, optimized for dense vertical scanning.

## Source

- Path: `frontend/src/components/cards/IntelligenceFeedItem.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function IntelligenceFeedItem(props: Props)`
- Props (`interface Props`):
  - `card: CardBrief`
  - `onSaveWatchItem?: (card: CardBrief) => void`
  - `showCompany?: boolean` — defaults to `true`.
- Click / keyboard activation navigates to `/intelligence/{card.card_id}` (same destination as the drawer's "Open intelligence object" CTA).

## Dependencies

- May import: `react-router-dom` (`useNavigate`), `lucide-react` (`BookmarkPlus`), `clsx`, `@/api/types`, `@/components/common/SourceDocumentLink`, `@/components/common/SignalBadge`, `@/lib/format`.
- Must not: fetch data; render its own drawer; render its own group header (that is `IntelligenceTimeline`'s job).

## Patterns (symmetry)

- Mirror `IntelligenceCard` props (`card`, `onSaveWatchItem`, `showCompany`) so they remain swappable inside `IntelligenceTimeline`. Opening behaviour differs: feed rows route to the full intelligence object page; card variant still uses parent `onOpen` (drawer).
- Same click + keyboard activation pattern (`role="button"`, `tabIndex={0}`, `onKeyDown`).
- Same source label / date row at the bottom (no confidence score).
- Save-watch button uses `opacity-90 group-hover:opacity-100` to fade in on hover (feed-density specific touch).

## UI / UX

- Container: `rounded-xl border border-line/60 bg-surface-2/40 px-3 py-3` — no `.card` shadow because feed items sit inside an already-bordered timeline list.
- Margin above headline is conditional (`mt-0.5`) and only applies when the company line shows above it.

## Verification checklist

- [ ] Click navigates to `/intelligence/{card.card_id}`
- [ ] Shared props with `IntelligenceCard`: `card`, `onSaveWatchItem`, `showCompany`
- [ ] No data fetching
- [ ] Headline truncation via `line-clamp-2`
- [ ] `SignalBadge` reused for the colour pill — no inline coloured `span`
- [ ] `e.stopPropagation()` on every nested clickable
