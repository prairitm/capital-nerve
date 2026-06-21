# AnalystSummaryCard

> Inherits: ./_BASE.md

## Purpose

Pinned themed summary card surfaced at the top of `EventDetailPage`. Gives an
analyst a single-glance read on the quarter: a verdict tone and one sentence
per theme (Topline, Margins, Segments, Capex / management tone).

## Source

- Path: `frontend/src/components/cards/AnalystSummaryCard.tsx`
- Layer: frontend-component

## Contract

Props:

```ts
{
  summary: AnalystSummary | null | undefined;
  className?: string;
}
```

`AnalystSummary` is defined in [`@/api/types`](../../api/types.ts) and lives on
`EventDetailV1.analyst_summary`. Returns `null` when there are no themes.

## Dependencies

- May import: `@/api/types`, `lucide-react` (`TrendingUp`, `TrendingDown`,
  `AlertTriangle`, `Minus`), `clsx`.
- Must not: fetch data, compute a summary client-side, or join multiple
  events. The payload is built once on the backend (see
  [`services/event_summary.build_analyst_summary`](../../../../backend/app/services/event_summary.py)).

## Patterns (symmetry)

- Verdict labels mirror the backend tone vocabulary: `positive` →
  "Constructive quarter", `negative` → "Challenging quarter", `mixed` →
  "Mixed quarter", `neutral` → "Steady quarter". Keep these in sync with the
  backend if the theme set evolves.
- Tone-coloured icons + chips use the project palette
  (`chip-positive` / `chip-negative` / `chip-mixed` / `chip-neutral`); never
  colour alone — every chip also carries a tone label.
- Theme order is preserved from the API payload; the backend already orders
  themes (Topline → Margins → Segments → Capex / management tone).

## UI / UX

- Pinned section sits **above** the cards list on `EventDetailPage`.
- One `card-2` row per theme. Each row has a tone icon, the theme label, a
  small uppercase tone chip, and the templated sentence.
- Sentence text uses `text-ink-mute leading-relaxed` so it reads like analyst
  copy — not a metric line.

## Verification checklist

- [ ] Returns `null` when `summary` is missing or has zero themes.
- [ ] Verdict chip uses one of `chip-positive` / `chip-negative` /
      `chip-mixed` / `chip-neutral` (no custom colour).
- [ ] Renders one `card-2` row per theme in the order returned by the API.
- [ ] Tone chip on each row matches the row's `tone` value.
- [ ] Pinned above any other card lists on `EventDetailPage`.
