# services/ir_discovery/periods

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Pure-functional range expansion for the bulk-ingest CLI. Takes one of
three CLI input shapes and returns a chronological list of
`PeriodSpec`, optionally interleaved with annual periods for every FY
whose Q4 is in the window.

## Source

- Path: `backend/app/services/ir_discovery/periods.py`
- Layer: backend-service

## Contract

- `expand_range(*, period_from, period_to, start_date, end_date,
  last_quarters, today=None, include_annual=False) -> list[PeriodSpec]`.
- Exactly one of the three input groups must be supplied:
  - quarter range: `period_from` + `period_to` (both required).
  - date range: `start_date` + `end_date` (both required).
  - rolling window: `last_quarters` (positive integer).
- Raises `PeriodRangeError` (a `ValueError` subclass) on conflicting,
  unparseable, or reversed inputs.
- `include_annual=True` appends an `ANNUAL` `PeriodSpec` after each Q4
  in the produced list. Annual specs are de-duplicated per FY year.
- All Indian-FY math reuses
  `app.services.ingest_common.{parse_period_label, quarter_date_bounds}`
  so this module agrees with the upload endpoint on quarter boundaries.

## Dependencies

- May import: `app.db.enums.PeriodType`, `app.services.ingest_common`,
  and `.schemas.PeriodSpec`.
- Must not import: anything from `app.services.pipeline`,
  `app.services.ir_discovery.agent`, or any I/O / DB module.

## Patterns (symmetry)

- The result list is always in chronological order; tests assert this.
- `--last-quarters N` walks N quarters back from the FY quarter
  containing `today` and reverses the list — never produces a future
  quarter.
- Quarter labels accept the same formats the upload endpoint already
  parses (`Q4 FY25-26`, `Q4 FY2025-26`, slash variants), because we
  delegate to `parse_period_label`.

## Verification checklist

- [ ] `expand_range(period_from="Q1 FY25-26", period_to="Q3 FY25-26")`
      returns three `PeriodSpec` rows in Q1 / Q2 / Q3 order.
- [ ] `expand_range(start_date=2024-04-01, end_date=2026-03-31)` covers
      every FY24-25 and FY25-26 quarter.
- [ ] `expand_range(last_quarters=4, today=...)` returns four entries
      ending at the FY quarter containing `today`.
- [ ] `expand_range(period_from=..., period_to=...,
      include_annual=True)` interleaves an `ANNUAL` spec after every
      Q4 once per FY.
- [ ] Conflicting inputs / unparseable labels raise `PeriodRangeError`.
