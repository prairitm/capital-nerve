# IntelligenceTimeline

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Renders grouped cards as a vertical timeline. Each group has an optional event header (company, type, date, signal, severity) and a list of cards. Used by the Home page (feed view) and the Company / Event detail pages.

## Source

- Path: `frontend/src/components/cards/IntelligenceTimeline.tsx`
- Layer: frontend-component (composes presentational items)

## Contract

- Export: `export function IntelligenceTimeline(props: Props)`
- Props (`interface Props`):
  - `groups: TimelineCardGroup[]` — produced by `groupCardsByEvent` / `groupCardsByTimeline` from `@/lib/cards`.
  - `onOpen: (cardId: number) => void`
  - `onSaveWatchItem?: (card: CardBrief) => void`
  - `showCompanyInHeader?: boolean` — defaults to `false`. Set `true` for market-wide feeds (Home) where each event header should name its company.
  - `variant?: "feed" | "card"` — picks `IntelligenceFeedItem` (default) or `IntelligenceCard`.

## Dependencies

- May import: `react-router-dom` (`useNavigate`), `lucide-react` (`ChevronDown`), `clsx`, `@/api/types`, `@/lib/cards` (`TimelineCardGroup`), `./IntelligenceCard`, `./IntelligenceFeedItem`, `../common/SeverityBadge`, `../common/SignalBadge`, `@/lib/format`.
- Must not: fetch data, mutate the `groups` array, or sort cards itself (sorting belongs in `@/lib/cards`).

## Patterns (symmetry)

- Date sections are derived once via `useMemo(() => buildDateSections(groups), [groups])` so render is cheap.
- Each date section is collapsible (`useState<Set<string>>`) and shows an event count badge.
- When there is exactly one un-dated section the timeline renders inline (no date header).
- Event header navigation goes to `/company/:symbol/event/:eventId` when both are available; otherwise the header button is disabled with `cursor-default`.
- Event header title uses `resolveEventDisplayTitle` (document type only), not `event_title` — company name appears only when `showCompanyInHeader` is true. Reporting quarter (`resolveQuarterPeriodLabel` from card/event `period`) appears as a muted uppercase line between company and document type. Optional meta line is date-only when `showDateInHeader`.
- Card variant choice (`card` vs `feed`) is passed down to either `IntelligenceCard` or `IntelligenceFeedItem`. Do not introduce a third variant without updating both components.

## UI / UX

- Outer list uses `ol.relative border-l border-line` with `<span className="ui-dot" />` markers per group.
- Collapse caret is a `ChevronDown` rotated `-90deg` when collapsed.

## Verification checklist

- [ ] Receives `groups` already sorted/filtered — no in-component sorting
- [ ] Empty input returns `null`
- [ ] Single-section input skips the date accordion
- [ ] Variant prop drives the choice between `IntelligenceFeedItem` and `IntelligenceCard` only
- [ ] Event header reuses `SignalBadge` and `SeverityBadge`
