# AppShell

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

The persistent chrome around every authenticated route: left nav sidebar, top bar with search and account menu, mobile bottom nav, and an `<Outlet />` for the active route.

## Source

- Path: `frontend/src/components/layout/AppShell.tsx`
- Layer: frontend-component (layout)

## Contract

- Export: `export function AppShell()` — used in [`@/App.tsx`](../../App.tsx) as the wrapper element inside `RequireAuth`.

## Dependencies

- May import: `react-router-dom` (`Outlet`, `NavLink`, `useNavigate`, `useLocation`), `lucide-react`, `clsx`, `@/store/auth`, `./TopSearch`, `./UtilitySidebar` (`UtilityMenu`, `UtilityMenuToggle`).
- Must not: fetch data. User info is read from `useAuthStore()` only.

## Patterns (symmetry)

- The `NAV` array drives the left desktop sidebar and the mobile bottom nav. Utility routes live in `UTILITY_NAV` inside the header dropdown ([`UtilitySidebar.tsx`](./UtilitySidebar.tsx)).
- `ADMIN_NAV` (`Ingest`, `Review Queue`) renders in the desktop sidebar and mobile bottom nav only when `user?.user_type === "ADMIN"`. This is the only place that branches navigation on user type.
- Left sidebar is `hidden lg:flex` with `sticky top-0 h-screen`. Top bar is `sticky top-0 z-30`. No right layout column.
- The local `Logo` subcomponent is intentionally private to this file — do not extract it into `common/`.

## UI / UX

- Brand mark uses a linear gradient (`#60A5FA` → `#3B82F6`) and a brand-blue accent dot (`#60A5FA`). Match the colours if you ever re-render the logo.
- Active `NavLink` state styles: `bg-surface text-ink border border-line` (desktop), `text-ink` (mobile). Inactive: `text-ink-mute` / `text-ink-soft`.
- The main column uses `flex-1 px-4 md:px-6 lg:px-8 py-4 md:py-6 pb-24 lg:pb-8` to keep content clear of the mobile bottom nav.

## Verification checklist

- [ ] `NAV` drives left sidebar and bottom nav
- [ ] `ADMIN_NAV` (Ingest + Review Queue) gated on `ADMIN`, shown on desktop sidebar and mobile bottom nav
- [ ] Top bar contains `TopSearch` and `UtilityMenuToggle` — no right sidebar
- [ ] Logout uses shared `signOut()` passed into `UtilityMenu`
- [ ] No data fetching in AppShell
