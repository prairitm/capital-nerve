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

- May import: `react-router-dom` (`useNavigate`, `useSearchParams`), `lucide-react` (`ChevronDown`), `clsx`, `@/api/types`, `@/lib/cards` (`TimelineCardGroup`), `./IntelligenceCard`, `./IntelligenceFeedItem`, `./EventSignalSummary`, `../common/SeverityBadge`, `../common/SignalBadge`, `@/lib/format`.
- Must not: fetch data, mutate the `groups` array, or sort cards itself (sorting belongs in `@/lib/cards`).

## Patterns (symmetry)

- Date sections are derived once via `useMemo(() => buildDateSections(groups), [groups])` so render is cheap and used as muted section labels (event count beside them).
- **Per-event accordion.** Each event group renders as an accordion. By default the group is collapsed; analysts opt-in by clicking the chevron. Expanded ids are persisted in the URL as `?expanded=evt_123,evt_456` via `useSearchParams({ replace: true })` so reload, deep-link, and back-button preserve state.
- Collapsed state shows: event header (date / company / period / document type), the `result_verdict` headline if any (plus its `SignalBadge` + `SeverityBadge`), and the `EventSignalSummary` chip strip pulled from the same `group.cards`. Expanded state additionally renders each card via `IntelligenceCard` / `IntelligenceFeedItem`.
- When there is exactly one un-dated section the timeline renders inline (no date label row).
- Event header opens `/company/:symbol/event/:eventId` when both are available; the chevron toggle is separate from the open-event button so a single click can either expand or open.
- Event header title uses `resolveEventDisplayTitle` (document type only), not `event_title` — company name appears only when `showCompanyInHeader` is true. Reporting quarter (`resolveQuarterPeriodLabel` from card/event `period`) appears as a muted uppercase line between company and document type. Optional meta line is date-only when `showDateInHeader`.
- Card variant choice (`card` vs `feed`) is passed down to either `IntelligenceCard` or `IntelligenceFeedItem`. Do not introduce a third variant without updating both components.

## UI / UX

- Outer list uses `ol.relative border-l border-line` with `<span className="ui-dot" />` markers per group.
- Collapse caret is a `ChevronDown` rotated `-90deg` when collapsed.
- The `result_verdict` card is treated as the group's verdict — its headline appears in the header and it is excluded from the `EventSignalSummary` chips (otherwise it would duplicate).

## Verification checklist

- [ ] Receives `groups` already sorted/filtered — no in-component sorting
- [ ] Empty input returns `null`
- [ ] Single-section input skips the date label row
- [ ] Variant prop drives the choice between `IntelligenceFeedItem` and `IntelligenceCard` only
- [ ] Event header reuses `SignalBadge` and `SeverityBadge` and shows the `result_verdict` headline when one exists
- [ ] Collapsed event groups render an `EventSignalSummary` chip strip
- [ ] Toggling an event reflects in the `?expanded=evt_123,evt_456` URL param (round-trips on reload)
