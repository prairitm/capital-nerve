# SeverityBadge

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Coloured pill for a card's `severity` level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`),
relabelled in the UI as *materiality* (Routine / Notable / Material /
Market-moving). Kept as a compatibility alias for the canonical
[`MaterialityBadge`](MaterialityBadge.tsx) so existing call sites pick up the
new vocabulary without a mechanical rename.

## Source

- Path: `frontend/src/components/common/SeverityBadge.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function SeverityBadge({ level, size })`
- Props:
  - `level: SeverityLevel | null | undefined` — returns `null` when falsy.
  - `size?: "sm" | "md"`.

## Dependencies

- May import: `clsx`, `@/api/types`.
- Must not: combine severity with signal direction in one badge — those are intentionally separate pills.

## Patterns (symmetry)

- Maps `SeverityLevel` → `{ label, klass }`:
  - `LOW` → "Routine" / `chip-low`
  - `MEDIUM` → "Notable" / `chip-neutral`
  - `HIGH` → "Material" / `chip-mixed`
  - `CRITICAL` → "Market-moving" / `chip-negative`
- Same dot + label pattern as `SignalBadge`.
- Renders a `title` tooltip explaining the materiality semantics so hover
  reveals the meaning to first-time users.

## Verification checklist

- [ ] Returns `null` for falsy `level`
- [ ] Labels match the four-step materiality vocabulary above
- [ ] Dot + label structure mirrors `SignalBadge`
- [ ] Backend enum stays `LOW/MEDIUM/HIGH/CRITICAL` — never invent a new value here
