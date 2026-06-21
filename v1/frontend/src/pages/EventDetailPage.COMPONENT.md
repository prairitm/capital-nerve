# EventDetailPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Drill-down for one event at `/company/:symbol/event/:eventId`. Verdict-first header with document icon beside the period title, event summary, signals and key numbers for quarterly results, intelligence cards, and sidebar with concall concerns when present.

## Source

- Path: `frontend/src/pages/EventDetailPage.tsx`
- Route: `/company/:symbol/event/:eventId`
- Layer: frontend-page

## Contract

- Data: `GET /events/:eventId` (`EventDetail`) — includes `signals`, `financial_snapshot`, `related_events`, `ingestion_status`.
- `SaveWatchItemDialog` at page level; cards navigate to `/intelligence/:id`.

## Dependencies

- May import: `react`, `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`, `@/api/client`, `@/api/types`, card/save-watch components, badges, `@/lib/cards`, `@/lib/format`.

## Patterns (symmetry)

- `QUARTERLY_RESULT`: signals list, then intelligence cards, then key numbers table when present.
- `CONCALL_TRANSCRIPT` / `INVESTOR_PRESENTATION` (or a linked transcript or presentation document): **Management tone intelligence** section for `management_tone`, `guidance_tracker`, and `analyst_concern` cards; concall commentary and heatmap when transcript data exists.
- Title row: period + `FileText` icon inline on the left; `SignalBadge` (overall signal) aligned right. Event date (plain text) below title; severity/confidence chips below that.
- Source documents: `EventDocumentIcons` tooltip carries title, type, values, and confidence — not a separate source block.
- Empty cards copy uses `ingestion_status` (draft cards, extraction without cards, etc.).
- Fallback event summary from top signal when `summary_text` is null.
- Back control uses [`BackButton`](../components/common/BackButton.tsx) (history back, fallback `/company/:symbol`).

## Verification checklist

- [ ] Single query `["event", eventId]` — no secondary signals fetch
- [ ] `financial_snapshot` renders for quarterly results when rows exist
- [ ] Contextual empty state when no published cards
- [ ] `SaveWatchItemDialog` still works from card bookmark action
- [ ] Concall transcript and investor presentation events show a dedicated **Management tone intelligence** section
- [ ] Document icon beside title links to `/documents/:id` when documents exist
- [ ] Back uses history when available; direct link falls back to company hub
