# ConfidenceBadge

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Optional confidence pill that takes either a `ConfidenceLevel` enum or a numeric `score` (0–100). Resolves the colour tier the same way the card detail drawer does.

## Source

- Path: `frontend/src/components/common/ConfidenceBadge.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function ConfidenceBadge({ level, score })`
- Props (both optional, but at least one must be set or the badge returns `null`):
  - `level?: ConfidenceLevel | null`
  - `score?: number | null` — percentage value.

## Dependencies

- May import: `@/api/types`.
- Must not: render a coloured dot — confidence uses the chip background colour only.

## Patterns (symmetry)

- Thresholds: `score >= 85` or `level === "HIGH"` → `chip-positive`; `score >= 70` or `level === "MEDIUM"` → `chip-neutral`; otherwise `chip-low`. Keep these in sync with the verdict colours in `CardDetailDrawer.tsx`.
- Text formatting: when `score` is present, `"${score.toFixed(0)}% confidence"`; otherwise `"${level.toLowerCase()} confidence"` (with `_` replaced by space).

## Verification checklist

- [ ] Returns `null` when both `level` and `score` are absent
- [ ] Threshold values (85, 70) match `CardDetailDrawer`'s `confidenceClass` logic
- [ ] No dot — uses chip class for colour only
