# IntelligenceObjectPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Full-screen detail for a single `IntelligenceObject` at `/intelligence/:objectId`. Investor-first layout: verdict + hero metric, why it matters, proof (key metrics, financial context, evidence), compact context (signal/event), sidebar actions/trends; display metadata collapsed by default.

## Source

- Path: `frontend/src/pages/IntelligenceObjectPage.tsx`
- Layer: frontend-page

## Route

- `/intelligence/:objectId` — `objectId` is `intelligence_object_id` (same as `card_id`).

## Endpoint

- `GET /v1/intelligence-objects/{objectId}` → `IntelligenceObject`.

## Sections

1. **Verdict strip** — matches `SignalDetailPage`: signal category·code (or object-type) eyebrow, headline (`signal.headline` or `title`), `ObjectMetaLinks` (company · period · sector), direction + severity badges only.
2. **Why it matters** — distinct `subtitle`, then `insight`, `investor_question`, `display.cta`, `investor_relevance`, source links.
3. **Main column** — key metric tiles → financial context table (highlighted rows) → evidence (with doc deep links) → collapsible calculation → compact context (signal + event + `event_main_issue`) → collapsible display metadata.
4. **Sidebar** — suggested actions (labeled chips), trends, analyst concern heatmap, watch next.

## Dependencies

- May import: `react`, `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`, `@/api/client`, `@/api/types`, badges from `@/components/common`, `@/components/cards/MetricSparkline`, `@/components/common/SourceDocumentLink`, `@/components/evidence/EvidenceInlineLink`, `@/lib/format`.
- Must not: render AppShell chrome.

## Patterns (symmetry)

- `xl:grid-cols-3` layout matches `SignalDetailPage` / `CompanyPage`.
- Verdict header mirrors `SignalDetailPage` — no hero metric line, NSE/date, confidence/importance chips, or Company/Event/Signal buttons in the strip (those live in **Context**).
- Inline evidence links (`EvidenceInlineLinks`) beside key metrics and financial context — no standalone evidence card.
- Suggested action labels match `CardDetailDrawer` map.
- Subtitle hidden when duplicate of title (normalized compare).

## Verification checklist

- [ ] Query key `["intelligenceObject", objectId]`
- [ ] `display.primary_metric` surfaced in key metrics / financial context, not the verdict strip
- [ ] Display metadata collapsed by default
- [ ] Inline `p.N` links beside metrics; document links via `SourceDocumentLinks` in “Why it matters” when refs exist
- [ ] Context section links to signal and event routes
- [ ] Concern heatmap renders when non-empty
