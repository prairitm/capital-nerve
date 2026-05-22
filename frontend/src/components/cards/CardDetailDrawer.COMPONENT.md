# CardDetailDrawer

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Right-side drawer that loads an `IntelligenceObject` on demand and renders the full investor read: display config preview, summary, explanation, suggested actions, key metrics, YoY/calculated metrics table, calculation, watch-next, trend sparklines, and concall heatmap. The drawer is the v1 IO surface inside list views.

## Source

- Path: `frontend/src/components/cards/CardDetailDrawer.tsx`
- Layer: frontend-component (smart — owns its own query)

## Contract

- Export: `export function CardDetailDrawer(props: Props)`
- Props (`interface Props`):
  - `cardId: number | null` — when `null`, the drawer renders nothing. The id is the `intelligence_object_id` (which mirrors `intelligence_cards.card_id`).
  - `onClose: () => void`
  - `onSaveWatchItem?: (detail: IntelligenceObject) => void` — receives the full IO. Pages that map to a `CardBrief`-shaped watch item adapter handle the conversion at the call site (`HomePage.tsx`).

## Endpoint

- `GET /v1/intelligence-objects/{cardId}` → `IntelligenceObject`. Replaces the legacy `GET /cards/{cardId}` (which is still served by `routers/cards.py` for the flat surface).

## Dependencies

- May import: `react`, `@tanstack/react-query`, `react-router-dom` (`useNavigate`), `lucide-react`, `clsx`, `@/api/client`, `@/api/types` (`IntelligenceObject`, `CardMetricComparison`), `@/components/common/Spinner`, `@/components/common/SourceDocumentLink`, `./MetricSparkline`, `@/lib/format`.
- Must not: render outside its own overlay; bypass the `useQuery` cache; reach back into the flat `/cards` endpoint.

## Patterns (symmetry)

- Fetches via `useQuery({ queryKey: ["intelligenceObject", cardId], queryFn: () => api<IntelligenceObject>(`/v1/intelligence-objects/${cardId}`), enabled: open })`. Do not refetch manually.
- Escape closes the drawer (`useEffect` adds a `keydown` listener while open).
- Body click on the backdrop (`.bg-black/60`) also closes.
- Helper components: `CardSummarySection`, `CardVerdictChips`, `DisplayConfigCallout`, `SuggestedActions`, `CalculationPanel`, `ImportanceBadge`. Reuse them rather than duplicating layout.
- Metric value formatting via `formatMetricValue` (handles `%`, `bps`, `Cr`, numeric). Change row formatting via `formatMetricChange`.
- The header CTA stack offers "Open intelligence object" (navigates to `/intelligence/{id}`), "Open event" (when the IO is tied to an event), and "Save as watch item".

## Sections rendered

1. `DisplayConfigCallout` — `display.primary_metric`, `display.cta`, `time_horizon`, `investor_relevance` tags.
2. `CardSummarySection` — `subtitle` + source links (via `SourceDocumentLinks` + `uniqueSourceRefs`).
3. Insight (`insight`) — `whitespace-pre-wrap` for multi-paragraph explanations.
4. Suggested actions (`suggested_actions`) — chip row using `chip-neutral` from [`@/styles.css`](../../styles.css).
5. Key metrics (`metrics`) — grid of 2/3 columns.
6. YoY & calculated metrics (`metric_comparisons`) — table.
7. Calculation (`calculation`) — flat key/value dl.
8. Main issue (`event_main_issue`) + Watch next (`watch_next`).
9. Trend sparklines (`trend_sparklines`).
10. Concall heatmap (`concern_heatmap`).
11. Event footer (`event_title` + `event_summary`).

## UI / UX

- Drawer width: `w-full md:w-[560px] lg:w-[620px]`. Slides in from the right.
- Sticky drawer header (`sticky top-0 bg-bg/95 backdrop-blur`) carries close button, headline metadata, verdict chips, and the action CTA stack.
- `ImportanceBadge` colour: `>=80` `text-positive`, `>=60` `text-ink`, else `text-ink-mute`.

## Verification checklist

- [ ] `cardId === null` short-circuits to `return null`
- [ ] Single `useQuery` with stable key `["intelligenceObject", cardId]`
- [ ] Fetches `/v1/intelligence-objects/{cardId}` (not the legacy `/cards/{cardId}`)
- [ ] Escape and backdrop close handlers
- [ ] Uses `SourceDocumentLinks` + `uniqueSourceRefs` for source list
- [ ] `MetricSparkline` used for trend cards (no recharts inline here)
- [ ] `ImportanceBadge` shown alongside `SignalBadge` / `SeverityBadge` / `ConfidenceBadge`
- [ ] `onSaveWatchItem` receives `IntelligenceObject`; the call site adapts to the dialog shape
