# Empty

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Canonical zero-state for any list / panel. Renders a centered card with an optional icon, a title, an optional description, and an optional action button.

## Source

- Path: `frontend/src/components/common/Empty.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function Empty({ title, description, icon, action })`
- Props:
  - `title: string` — required.
  - `description?: string`
  - `icon?: ReactNode` — typically a `lucide-react` icon at `size={36}`.
  - `action?: ReactNode` — typically a `btn-primary` button.

## Dependencies

- May import: `react`.
- Must not: navigate or call APIs directly. Actions are provided by the caller.

## Patterns (symmetry)

- Container: `.card p-8 text-center flex flex-col items-center gap-3`.
- Icon colour: `text-ink-mute`. Title: `text-base font-semibold text-ink`. Description: `text-sm text-ink-mute max-w-md`.
- Pages and panels should use `Empty` instead of rolling their own zero-state card. See `HomePage`, `WatchlistPage`, `SignalsPage` for examples.

## Verification checklist

- [ ] `title` always rendered
- [ ] `description` rendered conditionally
- [ ] No internal navigation or fetching
