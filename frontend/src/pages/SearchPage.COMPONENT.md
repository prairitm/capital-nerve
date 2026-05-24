# SearchPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Full search results page at `/search?q=...`. Returns sectioned results for
companies, intelligence cards, events, and filing text hits, plus an Ask panel
for cited RAG Q&A.

## Source

- Path: `frontend/src/pages/SearchPage.tsx`
- Route: `/search`
- Layer: frontend-page

## Contract

- Data: `GET /search?q=` (`SearchResult`), `POST /search/ask` (`AskResponse`).
- Query string `q` is the canonical state; the input syncs to it via `useSearchParams`.

## Dependencies

- May import: `react`, `react-router-dom` (`Link`, `useSearchParams`), `@tanstack/react-query`, `lucide-react`, `@/api/client`, `@/api/types`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SignalBadge`, `@/components/common/SeverityBadge`, `@/components/common/SourceDocumentLink` (`documentSourceHref`).
- Must not: persist the search term anywhere else (no `localStorage`).

## Patterns (symmetry)

- The submit form sets `?q=...`; the input local state syncs from `?q=` via `useEffect`.
- Query key: `["search", q]`. Disabled when `q.length === 0`.
- Result sections: Companies → In filings → Cards → Events. When all are empty, render "No matches."
- Card anchors use `id="card-${c.card_id}"` so `TopSearch` deep-linking (`#card-...`) works.
- Filing hits link via `documentSourceHref(document_id, page_number)`.

## UI / UX

- Ask panel is always visible above results; company scope is optional via select.
- Filing snippets may contain `ts_headline` `<b>` markup — render with `dangerouslySetInnerHTML` in the hit card only.

## Verification checklist

- [ ] `q` round-trips through URL search params
- [ ] React Query is disabled when `q.length === 0`
- [ ] Result sections include `document_hits` when present
- [ ] Card anchors include `id="card-:cardId"` for deep links
- [ ] Ask citations link to `/documents/:id?page=N`
