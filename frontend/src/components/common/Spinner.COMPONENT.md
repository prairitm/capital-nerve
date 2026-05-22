# Spinner / PageLoader

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Inline spinner and full-page loading state. Two exports from one file because they share the same SVG/CSS animation.

## Source

- Path: `frontend/src/components/common/Spinner.tsx`
- Layer: frontend-component (presentational)

## Contract

- Exports:
  - `export function Spinner({ size = 16 }: { size?: number })` — inline spinner.
  - `export function PageLoader()` — centered "Loading…" with a spinner; used by pages and `CardDetailDrawer`.

## Dependencies

- Pure React; no third-party libs.
- Must not: receive a `text` prop. The label is intentionally fixed to "Loading…" for visual consistency.

## Patterns (symmetry)

- `Spinner` uses `animate-spin` on a border-only circle. Size is controlled via `style={{ width, height }}` — not Tailwind utilities — so callers can pass arbitrary pixel sizes.
- `PageLoader` is the only loading state pages should render. Inline `Spinner` is reserved for buttons (e.g. login submit) and other tight contexts.

## Verification checklist

- [ ] `Spinner` default size `16`
- [ ] `PageLoader` always shows "Loading…" — do not parameterise the text
- [ ] Pages use `PageLoader`, not a custom centered div
