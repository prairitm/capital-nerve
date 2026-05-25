# SearchPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Full search results page at `/search?q=...`. Returns sectioned results for
companies, intelligence cards, events, and filing text hits, plus a unified Ask
panel (auto-routes to SQL facts or filing RAG).

## Source

- Path: `frontend/src/pages/SearchPage.tsx`
- Route: `/search`
- Layer: frontend-page

## Contract

- Data: `GET /search?q=` (`SearchResult`), `POST /search/ask` (`AskResponse` with `mode` `sql` | `rag`).
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

- Single Ask panel above results; optional company select scopes filing RAG only.
- SQL answers show a results table + collapsible SQL; RAG answers show citations.
- Filing snippets may contain `ts_headline` `<b>` markup — render with `dangerouslySetInnerHTML` in the hit card only.

## Verification checklist

- [ ] `q` round-trips through URL search params
- [ ] React Query is disabled when `q.length === 0`
- [ ] Result sections include `document_hits` when present
- [ ] Card anchors include `id="card-:cardId"` for deep links
- [ ] Ask `mode=sql` renders table + SQL details; `mode=rag` renders citations
- [ ] RAG citations link to `/documents/:id?page=N`
