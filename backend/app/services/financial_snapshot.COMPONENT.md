# financial_snapshot

> Inherits: [_BASE.md](./_BASE.md)

## Purpose

Build `FinancialSnapshotRow` lists and resolve margin levels for hub/event
snapshots and margin trend lines. Centralises YoY delta semantics (relative %
for crore/Rs levels, bps for consolidated margin levels).

## Source

- Path: `backend/app/services/financial_snapshot.py`
- Layer: backend-service

## Contract

- `SNAPSHOT_METRICS` — ordered `(code, display, unit)` tuples for snapshot tables.
- `build_financial_snapshot(db, *, company_id, period) -> list[FinancialSnapshotRow]`
- `build_snapshot_row(...)` — one row with prior-year comparison.
- `snapshot_yoy_delta(code, unit, current, previous) -> (pct, bps)`
- `trend_value_for_code(...)` — calculated margin for sparklines when applicable.
- `MARGIN_LEVEL_CODES` — margin metrics never read raw extracted margin facts alone.

## Dependencies

- May import: `sqlalchemy`, fact/intelligence/master models, `FinancialSnapshotRow`.
- Must not: import routers or pipeline stages.

## Verification checklist

- [ ] Margin YoY on snapshot is `yoy_change_bps`, not relative `yoy_change_pct`
- [ ] `ebitda_margin` level prefers `calculated_metrics` then `ebitda/revenue`
- [ ] Revenue/EBITDA/PAT YoY remains relative percent on `yoy_change_pct`
