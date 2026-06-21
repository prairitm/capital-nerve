# HeaderAlerts

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Alerts data and UI: `AlertsPanel` renders either a popover (`variant="popover"`, legacy) or an inline scrollable list for the right utility sidebar (`variant="sidebar"`).

## Source

- Path: `frontend/src/components/layout/HeaderAlerts.tsx`
- Layer: frontend-component (smart — reads from React Query)

## Contract

- Exports: `AlertsPanel`, `useAlertsUnread`, `HeaderAlerts` (popover wrapper, legacy).
- `AlertsPanel` props: `variant: "popover" | "sidebar" | "rail"`, optional `onNavigate` (called when an alert is opened, e.g. to close mobile utility drawer). `rail` = icon button with popover opening to the left (collapsed utility sidebar).

## Dependencies

- May import: `react`, `react-router-dom` (`useNavigate`), `@tanstack/react-query`, `lucide-react` (`Bell`), `clsx`, `@/api/client`, `@/api/types`, `@/lib/format` (`relativeDate`).
- Must not: subscribe to a real-time channel (alerts are polled by React Query refetch settings).

## Patterns (symmetry)

- `useQuery({ queryKey: ["alerts"], queryFn: () => api<AlertItem[]>("/alerts") })`. The query is shared with any other page that wants the alerts list.
- Unread badge appears only when `unread > 0` and caps at `"9+"`.
- Click-outside closes the dropdown via a `ref` + `mousedown` listener (same pattern as `TopSearch`).
- Navigation: clicking an alert with a `company_symbol` goes to `/company/:symbol`. Otherwise the row stays inert.

## UI / UX

- Button container: `size-9 rounded-xl`. Badge: `absolute top-1 right-1`, `bg-negative text-white text-[9px]`.
- Dropdown: `right-0 top-full mt-2 w-[min(calc(100vw-2rem),20rem)] .card p-2 max-h-[min(60vh,24rem)] overflow-y-auto z-40`.
- Slice to the first 8 alerts in the dropdown — keep this cap when adding new metadata to the rows.

## Verification checklist

- [ ] Single React Query key `["alerts"]`
- [ ] Unread badge logic uses `alerts.filter((a) => !a.is_read).length`
- [ ] Click-outside via `useRef` + `mousedown` listener
- [ ] Capped at 8 rows in the dropdown
- [ ] Disabled state when alert has no `company_symbol`
