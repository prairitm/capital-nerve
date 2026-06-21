# event_financials

> Inherits: [_BASE.md](./_BASE.md)

## Purpose

Build `FinancialSnapshotRow` list for one reporting period (used by `GET /events/{id}`).

## Source

- Path: `backend/app/services/event_financials.py`
- Layer: backend-service

## Contract

- Export: `build_financial_snapshot_for_period(db, company_id, period) -> list[FinancialSnapshotRow]`
- Metrics: revenue, EBITDA, EBITDA margin, PAT, EPS — current period vs same quarter prior year.

## Dependencies

- May import: [`financial_snapshot`](financial_snapshot.py), `FinancialPeriod`, `FinancialSnapshotRow`.
- Must not: write to the database.

## Verification checklist

- [ ] Returns empty list when `period` is None
- [ ] Delegates to `financial_snapshot.build_financial_snapshot` (margin bps YoY, calculated margins)
