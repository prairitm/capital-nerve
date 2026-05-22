# IntelligenceCard

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Card-density tile for a single `CardBrief`. Used in event detail (signal detail "related" lists, full-card grids) where each row is its own visual card.

## Source

- Path: `frontend/src/components/cards/IntelligenceCard.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function IntelligenceCard(props: Props)`
- Props (`interface Props`):
  - `card: CardBrief`
  - `onOpen?: (id: number) => void` — when omitted, card click navigates to `/intelligence/:cardId` (same as `IntelligenceFeedItem`).
  - `showCompany?: boolean` — defaults to `true`. Set `false` when company is already named in a parent header.
  - `onSaveWatchItem?: (card: CardBrief) => void` — when provided, a `BookmarkPlus` icon button renders.

## Dependencies

- May import: `react-router-dom` (`useNavigate`), `lucide-react` (`BookmarkPlus`), `@/api/types`, `@/components/common/SourceDocumentLink`, `@/components/common/SignalBadge`, `@/lib/format`.
- Must not: call `api()` or `useQuery`. Data must arrive via props.

## Patterns (symmetry)

- Wrapped in `<article role="button" tabIndex={0} onClick onKeyDown>` for keyboard activation (Enter / Space).
- Inner clickable buttons (company name link, save-watch-item, source link) call `e.stopPropagation()` to prevent the outer card click.
- Company symbol resolution: `card.company.nse_symbol || card.company.bse_code`. Reuse this when adding new card surfaces — never assume one is non-null.
- Card-type label rendered with `cardTypeLabel(card.card_type)`.
- Source label and date row shows: source document link (if `document_id`) · relative date (with full date in `title`) · `Math.round(confidence_score)`% confidence.

## UI / UX

- Container: `.card rounded-xl border border-line/60 bg-surface-2/40 px-3 py-3` with hover state `hover:border-line-strong hover:bg-surface-2`.
- Headline uses `text-[15px] font-medium text-ink leading-snug`. Summary is `line-clamp-2`.
- `SignalBadge` is right-aligned in the top row.

## Verification checklist

- [ ] Named export `IntelligenceCard`
- [ ] Props typed via `interface Props`
- [ ] Outer element has `role="button"`, `tabIndex={0}`, and an `onKeyDown` Enter/Space handler
- [ ] Inner buttons call `e.stopPropagation()` before navigation or callbacks
- [ ] Uses `SignalBadge` and `SourceDocumentLink` (no hand-rolled chips or links)
- [ ] Confidence shown only when `card.confidence_score != null`
- [ ] No `useQuery` / `api()` / `useState` for server data
