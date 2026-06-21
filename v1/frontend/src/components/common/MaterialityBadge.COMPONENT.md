# MaterialityBadge

> Inherits: ./_BASE.md

## Purpose

Render the backend `SeverityLevel` as a *materiality* chip in the UI so that
"how much this moves the thesis" stays separate from "tone" (which lives on
`SignalBadge`). This split fixes the semantically broken pairing of
"Critical-risk" with "Positive" the legacy verdict could produce.

## Source

- Path: `frontend/src/components/common/MaterialityBadge.tsx`
- Layer: frontend-component

## Contract

Props:

```ts
{
  level: SeverityLevel | null | undefined;
  size?: "sm" | "md";
}
```

Returns `null` for missing `level`. Always pair this badge with `SignalBadge`
where both tone and materiality are surfaced.

## Dependencies

- May import: `@/api/types`, `clsx`.
- Must not: re-derive the level from cards or signals; the prop owns the
  contract.

## Patterns (symmetry)

- Backend field stays `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` — do not rename
  the enum. Only the user-facing label changes:
  - `LOW` → "Routine"
  - `MEDIUM` → "Notable"
  - `HIGH` → "Material"
  - `CRITICAL` → "Market-moving"
- Chip palette mirrors the rest of the app (`chip-low`, `chip-neutral`,
  `chip-mixed`, `chip-negative`).
- `title` attribute carries the gloss "Materiality — how much this signal
  moves the investment thesis." so hovering reveals the meaning.

## Verification checklist

- [ ] Returns `null` when `level` is missing.
- [ ] Renders one of the four labels above (never the raw enum value).
- [ ] Size variant flips text + padding to `text-sm px-3 py-1.5` for `md`.
- [ ] Sits beside `SignalBadge` wherever a card / signal / event surface
      shows verdict chips.
