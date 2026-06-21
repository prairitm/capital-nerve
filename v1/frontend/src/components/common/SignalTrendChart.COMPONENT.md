# SignalTrendChart

> Inherits: ./_BASE.md

## Purpose

Multi-line "Signal trend" chart on the company hub. Shows the last N quarters
of the analyst signal set (revenue growth, EBITDA margin, PAT margin, segment
margin) so an analyst can see direction-of-travel without leaving the company
page.

## Source

- Path: `frontend/src/components/common/SignalTrendChart.tsx`
- Layer: frontend-component

## Contract

Props:

```ts
{
  symbol: string;                  // NSE/BSE symbol path param
  codes?: string[];                // override the default metric set
  quarters?: number;               // default 8 (matches spec §2C)
  className?: string;
}
```

Calls `GET /v1/companies/{symbol}/metric-trend?codes=...&quarters=...` and
renders a Recharts `LineChart` with one series per `FinancialTrend`. Returns
`null` when the endpoint has nothing usable for the company.

## Dependencies

- May import: `react`, `@tanstack/react-query`, `recharts`,
  `@/api/client`, `@/api/types` (`FinancialTrend`), `@/components/common/Spinner`,
  `@/lib/format`.
- Must not: compute metric values client-side, swallow errors silently, or
  introduce a different chart library.

## Patterns (symmetry)

- Endpoint name (`/v1/companies/{symbol}/metric-trend`) mirrors the rest of
  the v1 router prefix. Keep this URL stable.
- Default metric set is owned by the backend (`_DEFAULT_METRIC_TREND_CODES`
  in [`backend/app/routers/v1/companies.py`](../../../../backend/app/routers/v1/companies.py)).
  The frontend only overrides via `codes` when a caller needs a custom slice.
- Quarantined `calculated_metrics` rows are filtered out by the backend so
  one bad data point cannot drag the line off-scale.
- Lines are coloured from a shared 6-colour palette so additional metric
  codes have a predictable rendering without touching the chart code.
- Chronological order (oldest → newest, left → right) is enforced by the
  backend; the frontend never re-sorts.

## UI / UX

- Chart sits inside a `card p-5 md:p-6` shell to match the rest of the
  company-page sections.
- Tooltip uses the project surface tokens (`#141A26` background, `#222B3D`
  border) so it matches the existing sparkline tooltip.
- Legend is at the bottom so the lines themselves dominate the visual area.

## Verification checklist

- [ ] Returns `null` when the API responds with an empty array.
- [ ] Renders one Recharts `<Line>` per `FinancialTrend` in the response.
- [ ] Tooltip values use the metric's `unit` (e.g. `%` → `formatPct`, `bps`
      → `±N bps`, others → plain number).
- [ ] X-axis label uses the period's `period_label` (e.g. "Q3 FY24-25") and
      the data is chronological.
- [ ] Quarters prop and `codes` array round-trip into the API URL.
