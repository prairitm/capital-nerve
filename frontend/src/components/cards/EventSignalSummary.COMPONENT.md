# EventSignalSummary

> Inherits: ./_BASE.md

## Purpose

Compact "what fired" chip strip for an event group, used by the collapsed
accordion state on [`IntelligenceTimeline.tsx`](IntelligenceTimeline.tsx) and
the company quarter view. Lets an analyst scan an entire quarter in one row
without expanding it.

## Source

- Path: `frontend/src/components/cards/EventSignalSummary.tsx`
- Layer: frontend-component

## Contract

Props:

```ts
{
  cards: CardBrief[];   // event's cards, ranked by importance
  limit?: number;       // default 5 (spec §2A)
  className?: string;
}
```

Returns `null` when no non-`result_verdict` cards are present.

## Dependencies

- May import: `@/api/types` (`CardBrief`, `SignalDirection`), `lucide-react`,
  `clsx`.
- Must not: re-fetch cards or pull from globalstate. Pure projection over the
  caller-supplied `cards` list.

## Patterns (symmetry)

- `result_verdict` card is excluded — that card's headline already lives in
  the verdict chip beside this strip, and including it here would duplicate.
- Direction-coloured chips use the existing `chip-positive` / `chip-negative`
  / `chip-mixed` / `chip-neutral` palette. Never colour alone — every chip
  carries a direction icon and the card headline as label.
- Icon mapping mirrors the timeline accent set:
  - `POSITIVE` → `TrendingUp`
  - `NEGATIVE` → `TrendingDown`
  - `MIXED` → `AlertTriangle`
  - `NEUTRAL` → `Minus`
- Truncates each chip to `max-w-[18rem]` so a long card headline cannot blow
  out the row width; full text stays in the `title` attribute.

## Verification checklist

- [ ] Returns `null` when there are no non-`result_verdict` cards.
- [ ] Honours `limit` (default 5).
- [ ] Renders a `+N more` low-tone chip when the source list exceeds the
      limit.
- [ ] Each chip carries an icon + headline + tone class derived from
      `card.signal_direction`.
- [ ] Excludes the `result_verdict` card so the verdict chip beside this
      strip is not duplicated.
