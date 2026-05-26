# BackButton

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

History-aware back control for drill-down pages: returns to the previous in-app route when the user navigated here, otherwise navigates to a caller-supplied fallback (direct link / bookmark).

## Source

- Path: `frontend/src/components/common/BackButton.tsx`
- Layer: frontend-component

## Contract

- `useNavigateBack(fallback: string): () => void` — uses `navigate(-1)` when `location.key !== "default"`, else `navigate(fallback)`.
- `BackButton` props: `fallback` (required), optional `className`, optional `children` (default label `"Back"`).

## Dependencies

- May import: `react`, `react-router-dom`, `lucide-react`.
- Must not: fetch data or encode page-specific fallback logic — callers pass `fallback`.

## Patterns (symmetry)

- Default styling matches page back buttons: `btn-ghost -ml-2 text-sm` with `ArrowLeft` size 16.
- All page-level “Back” controls should use this hook or component instead of hard-coded parent routes.

## Verification checklist

- [ ] In-app navigation (e.g. feed → detail) calls `navigate(-1)`
- [ ] Direct URL load uses `fallback`
- [ ] Label defaults to `"Back"`; callers may override `children`
