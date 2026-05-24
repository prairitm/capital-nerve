# TopSearch

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Global search input in the top bar with a typeahead dropdown for companies,
cards, events, and filing hits. Bound to Cmd/Ctrl+K.

## Source

- Path: `frontend/src/components/layout/TopSearch.tsx`
- Layer: frontend-component (smart — reads from React Query)

## Contract

- Export: `export function TopSearch()` — used inside `AppShell` only.

## Dependencies

- May import: `react`, `react-router-dom` (`useNavigate`), `@tanstack/react-query`, `lucide-react` (`Search`), `@/api/client`, `@/api/types` (`SearchResult`), `@/components/common/SourceDocumentLink` (`documentSourceHref`).
- Must not: own a results page — the full results live in `SearchPage`.

## Patterns (symmetry)

- Query key: `["topSearch", q]`. Enabled when `q.length >= 2`.
- Hotkey: Cmd/Ctrl+K focuses the input via `document.querySelector<HTMLInputElement>("#cn-top-search")`. Keep the `id` so the binding works.
- Enter on the input navigates to `/search?q=...` to hand off to the full Search page.
- Dropdown sections: Companies (4 max) → Intelligence Cards (4 max) → In filings (3 max) → Events (4 max). When all are empty, show "No matches.".
- Click-outside closes via a `useRef` + `mousedown` listener (same pattern as `HeaderAlerts`).

## UI / UX

- Input: `.input pl-9 text-base sm:text-sm` with a `lucide-react` `Search` icon absolutely positioned.
- Dropdown: `top-full left-0 right-0 mt-2 .card p-2 max-h-[60vh] overflow-y-auto z-40`.
- Section helper component lives inside this file — do not export it.

## Verification checklist

- [ ] React Query key includes the search string
- [ ] Cmd/Ctrl+K focus binding targets `#cn-top-search`
- [ ] Enter on the input navigates to `/search?q=...`
- [ ] Each section capped at 4 rows (filings at 3)
- [ ] Click-outside closes the dropdown
