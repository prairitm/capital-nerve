# MetricSparkline

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Small inline line chart for an 8-quarter `FinancialTrend`. Shows the metric name, the latest value, and a sparkline.

## Source

- Path: `frontend/src/components/cards/MetricSparkline.tsx`
- Layer: frontend-component (presentational)

## Contract

- Export: `export function MetricSparkline({ trend }: { trend: FinancialTrend })`

## Dependencies

- May import: `recharts` (`LineChart`, `Line`, `YAxis`, `Tooltip`, `ResponsiveContainer`), `@/api/types`, `@/lib/format` (`formatNumber`, `formatPct`).
- Must not: depend on any other charting library; introduce axis labels (sparklines are intentionally minimalist).

## Patterns (symmetry)

- The latest value uses `formatPct` when `unit === "%"`, otherwise `formatNumber` with 0 fraction digits for `Cr` and 1 for everything else.
- The unit is shown as a suffix unless the unit is `%` (the `%` is part of `formatPct`).
- Chart uses brand blue: stroke `#3B82F6`, active dot `#60A5FA` on hover. No axes, no default dot.
- Tooltip uses the same `period_label` from the data point (`labelFormatter`) and formats the value with the unit-aware formatter.

## UI / UX

- Container: `rounded-lg bg-surface-2 border border-line/60 p-3 min-w-0`.
- Chart height: `h-14` (`56px`). Resizes with `ResponsiveContainer`.

## Verification checklist

- [ ] Single sparkline per instance (no axis labels, no legend)
- [ ] Stroke `#3B82F6`, active dot `#60A5FA` (aligned with `brand` tokens in `tailwind.config.ts`)
- [ ] Tooltip background and border match the dark theme tokens (`#141A26` / `#222B3D`)
- [ ] Unit formatting matches the rules in `formatPct` / `formatNumber`
