# SignalDetailPage

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Detail view for a single generated signal at `/signals/:signalId`. Verdict-first layout: compact header, “Why it matters”, “Why this fired” (composite rule leaves + pass/fail), financial context, related event, related cards; sidebar with suggested actions, trends, and sibling signals.

## Source

- Path: `frontend/src/pages/SignalDetailPage.tsx`
- Route: `/signals/:signalId`
- Layer: frontend-page

## Contract

- Data: `GET /signals/:signalId` (`SignalDetail`).
- Expects enriched fields: `rule_leaves`, `rule_metric_codes`, `primary_metric` (from `enrich_signal_detail`).
- Renders the card detail drawer at page level for related cards.

## Dependencies

- May import: `react`, `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`, `@/api/client`, `@/api/types`, `@/components/cards/CardDetailDrawer`, `@/components/cards/IntelligenceCard`, `@/components/cards/MetricSparkline`, `@/components/common/Spinner` (`PageLoader`), `@/components/common/SeverityBadge`, `@/components/common/SignalBadge`, `@/components/common/SourceDocumentLink`, `@/components/evidence/EvidenceInlineLink`, `@/lib/cards` (`filterInsightListCards`), `@/lib/format`.
- Must not: re-implement `MetricSparkline` or the metric value formatting — share `formatMetricValue` / `formatMetricChange` style with `CardDetailDrawer.tsx`.

## Patterns (symmetry)

- Verdict header: title, direction/severity badges; meta line uses inline `ui-link` for company name and period (`SignalMetaLinks`) plus plain sector — no primary-driver line, NSE, date, or source button in hero.
- “Why it matters” is a separate card (explanation + source links).
- “Why this fired” uses `rule_leaves` checklist when present; falls back to single `trigger_metric` tiles.
- Evidence: inline `p.N` / `source` links via `EvidenceInlineLinks` beside rule leaves and financial context values — no standalone evidence card.
- Financial context table highlights `rule_metric_codes` and `trigger_metric`.
- Related cards run through `filterInsightListCards` before rendering.
- Back control uses [`BackButton`](../components/common/BackButton.tsx) (history back, fallback `/signals`).

## UI / UX

- Two-column grid on `xl:grid-cols-3`: main column = why fired → metrics → event → cards; sidebar = suggested actions → trends → other signals.
- Rule leaf rows show Met / Not met with accessible colour + icon (not colour alone).

## Verification checklist

- [ ] Query key `["signal", signalId]`
- [ ] `rule_leaves` rendered when API returns them; fallback to `trigger_metric` tiles
- [ ] Inline evidence links on metrics; unmatched rows fall back under “Why this fired”
- [ ] Related cards filtered by `filterInsightListCards`
- [ ] Source links use `SourceDocumentLinks` + `uniqueSourceRefs`
- [ ] Drawer rendered at page level
- [ ] Back uses history when available; direct link falls back to `/signals`
