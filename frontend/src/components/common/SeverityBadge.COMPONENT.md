# SeverityBadge

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Coloured pill for a card's `severity` level (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

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

- Maps `SeverityLevel` → `{ label, klass }`. Both `HIGH` and `CRITICAL` use `chip-negative`; `MEDIUM` uses `chip-mixed`; `LOW` uses `chip-low`.
- Same dot + label pattern as `SignalBadge`.

## Verification checklist

- [ ] Returns `null` for falsy `level`
- [ ] HIGH and CRITICAL share the `chip-negative` class (do not split them)
- [ ] Dot + label structure mirrors `SignalBadge`
