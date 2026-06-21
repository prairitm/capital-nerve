# `frontend/src/pages/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

One file per route. Pages compose components from [`@/components/`](../components/), fetch data via `useQuery`, and own route-local UI state.

## Rules

- Export a single named function matching the file name: `export function HomePage()` for `HomePage.tsx`. Pages are registered in [`App.tsx`](../App.tsx).
- Route params come from `useParams`; query params come from `useSearchParams`. URLs are the canonical source of filter state — see [`SignalsPage.tsx`](SignalsPage.tsx) for the pattern.
- Server state is fetched with `useQuery`; mutations use `useMutation` and call `qc.invalidateQueries({ queryKey: [...] })` on success.
- Use `PageLoader` (from [`@/components/common/Spinner`](../components/common/Spinner.tsx)) for loading states and `Empty` (from [`@/components/common/Empty`](../components/common/Empty.tsx)) for zero-states. Don't roll your own.
- Local UI state (open drawer, filter chips, dialog target) uses `useState`. Persisted state belongs in URL or in `useAuthStore`.
- Pages share the `AppShell` chrome — they should not render their own top bar, sidebar, or bottom nav.
- For admin-only pages, guard with `if (user && user.user_type !== "ADMIN") return <Navigate to="/" replace />;` (pattern in [`AdminReviewPage.tsx`](AdminReviewPage.tsx)). The admin nav link itself is handled centrally in `AppShell`.
- Compose feed views with `IntelligenceTimeline` and `CardDetailDrawer`. The drawer is rendered at page level so opening a card does not unmount the surrounding feed.
- Use shared formatters (`formatDate`, `formatCr`, `formatPct`, `formatSigned`, `formatNumber`, `mainIssueLabel`, `relativeDate`, `cardTypeLabel`) from [`@/lib/format`](../lib/format.ts).

## Page anatomy

A typical authenticated page looks like:

1. Header (`h1` + subtitle).
2. Filter / summary strip (chip buttons or summary stats).
3. Main content (list, table, or card detail).
4. Page-level overlays (`CardDetailDrawer`, `SaveWatchItemDialog`).

Keep this structure when adding new pages so the visual rhythm matches the rest of the app.
