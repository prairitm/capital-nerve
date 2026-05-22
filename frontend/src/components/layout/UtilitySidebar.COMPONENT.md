# UtilityMenu (`UtilitySidebar.tsx`)

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Header account menu (dropdown): profile toggle, Watchlist link, alerts list, and sign-out. Not a layout sidebar — no persistent right column.

## Source

- Path: `frontend/src/components/layout/UtilitySidebar.tsx`
- Layer: frontend-component (layout)

## Contract

- Exports: `UtilityMenu`, `UtilityMenuToggle`, `UTILITY_NAV`
- Aliases: `UtilitySidebar`, `UtilitySidebarToggle` (deprecated)
- `UtilityMenu` props: `user`, `onSignOut`, `open`, `onClose`
- `UtilityMenuToggle` props: `user`, `onOpen`

## Dependencies

- May import: `react-router-dom` (`NavLink`), `lucide-react`, `clsx`, `@/api/types`, `./HeaderAlerts` (`AlertsPanel`, `useAlertsUnread`).
- Must not: render a sticky/full-height `<aside>` column.

## Patterns (symmetry)

- `UTILITY_NAV` is the single source for utility routes (Watchlist).
- Panel is `fixed` under the header (`top-14`), click-outside and Escape close it.
- Profile row toggles `menuOpen` to show Watchlist, alerts, and Sign out below.

## UI / UX

- Toggle: user avatar in the header with optional unread badge on alerts.
- Dropdown: `.card` panel, max height scrollable; same content on mobile and desktop.

## Verification checklist

- [ ] No desktop right sidebar column in the layout
- [ ] `UtilityMenuToggle` visible in the header at all breakpoints
- [ ] Click-outside and Escape dismiss the menu
- [ ] Sign out calls parent `onSignOut` only
