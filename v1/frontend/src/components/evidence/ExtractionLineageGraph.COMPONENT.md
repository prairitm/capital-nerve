# ExtractionLineageGraph

> Inherits: ./_BASE.md

## Purpose
Render the read-only lineage payload returned by
`GET /v1/intelligence-objects/{id}/reproducibility` as a five-lane
horizontal flow: `Extracted → Facts → Metric → Signal → Card`.

## Source
- Path: `frontend/src/components/evidence/ExtractionLineageGraph.tsx`
- Layer: frontend-component

## Contract
- Props: `{ graph: LineageGraph, className?: string }` where
  `LineageGraph` comes from `@/api/types`.
- Returns `null` when the graph carries no nodes (e.g. summary cards
  with no underlying signal).

## Dependencies
- May import: `@/api/types`, `lucide-react`, `clsx`.
- Must not: fetch data itself, navigate, or mutate the graph payload.

## Patterns (symmetry)
- Uses the same `card` shell as other detail-page sections so the page
  reads as one stack of panels.
- Anomaly / quarantined nodes pick up the `mixed` / `negative` tones
  used elsewhere in the feed (e.g. `MetricValidationBadge`).

## UI / UX (frontend only)
- Tailwind tokens: `card`, `border-line/40`, `bg-surface-2/30`,
  `text-ink-soft`, `text-ink-mute`.
- Five-column grid on `lg`, three on `md`, single column on mobile.
- Each lane shows an icon + label header; missing lanes show "none".

## Verification checklist
- [ ] Confidence and page number show only when the node carries them.
- [ ] Anomaly / quarantined cards have visible coloured borders and
      an inline status icon.
- [ ] Component renders cheaply on every IntelligenceObjectPage open
      (no extra network calls beyond the parent bundle query).
