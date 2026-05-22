# SignalBadge

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Coloured pill for a card's `signal_direction`. The single source of truth for the positive / negative / mixed / neutral pairing across the app.

## Source

- Path: `frontend/src/components/common/SignalBadge.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function SignalBadge({ direction, size })`
- Props:
  - `direction: SignalDirection | null | undefined` — returns `null` when falsy.
  - `size?: "sm" | "md"` — `"md"` adds `text-sm px-3 py-1.5`.

## Dependencies

- May import: `clsx`, `@/api/types`.
- Must not: include severity, confidence, or any non-direction state.

## Patterns (symmetry)

- Maps `SignalDirection` → `{ label, klass }` via a top-level `Record`. Same pattern as `SeverityBadge`.
- Always emits a leading dot (`<span className="size-1.5 rounded-full bg-current" />`) followed by the label. The label is mandatory — spec §11 forbids colour-only signalling.
- Uses `.chip-positive`, `.chip-negative`, `.chip-mixed`, `.chip-neutral` classes from [`@/styles.css`](../../styles.css).

## Verification checklist

- [ ] Returns `null` for falsy `direction`
- [ ] Label always rendered (no colour-only state)
- [ ] Uses `.chip-*` classes (no hand-rolled colour styles)
- [ ] `size="md"` adds the larger padding/text classes
