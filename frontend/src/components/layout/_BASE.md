# `frontend/src/components/layout/` baseline

> Inherits: [../../_BASE.md](../../_BASE.md)

The shell, top-bar search, account menu, and alerts that wrap every authenticated route.

## Components

- [`AppShell.tsx`](AppShell.tsx) — left sidebar + top bar + mobile bottom nav + `<Outlet />`.
- [`UtilitySidebar.tsx`](UtilitySidebar.tsx) — `UtilityMenu` header dropdown (Watchlist, alerts, sign-out); file name is legacy.
- [`TopSearch.tsx`](TopSearch.tsx) — global search input with Ctrl/Cmd+K hotkey and a typeahead dropdown.
- [`HeaderAlerts.tsx`](HeaderAlerts.tsx) — `AlertsPanel`, `useAlertsUnread`.

## Rules

- Layout components are the only place that may read from `useAuthStore()` to derive nav (admin-only `Review Queue` link). Pages should not branch on `user.user_type` for navigation visibility.
- Primary routes use `NAV` in `AppShell.tsx`; utility routes use `UTILITY_NAV` in `UtilitySidebar.tsx`.
- Click-outside handlers use a `useRef` + `mousedown` listener (pattern in `UtilityMenu`, `HeaderAlerts.tsx` popover, and `TopSearch.tsx`).
- Hotkey handlers attach on `document` inside `useEffect` and remove on unmount. The Cmd/Ctrl+K binding for search lives in `TopSearch.tsx`.
- The shell uses sticky positioning for the left sidebar and top bar; do not change z-index without checking the account menu (`z-40`), card drawer (`z-50`), and watch-item dialog (`z-[60]`).
- Mobile bottom nav is rendered by `AppShell` only — pages must not add their own bottom navigation.
- Do not add a persistent right sidebar column; utility UI belongs in the header dropdown only.
