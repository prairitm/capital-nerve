# seed/seed_catalog

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Idempotent catalog bootstrap that writes only the reference data the
pipeline depends on — line items, metric definitions, signal definitions,
financial periods, a minimal sector list, and (optionally) a single
admin user. No demo companies, events, cards, evidence, or watchlists
are created here.

## Source

- Path: `backend/app/seed/seed_catalog.py`
- Layer: backend-seed

## Contract

- `seed_catalog(db)` runs every upsert in the right order.
- `python -m app.seed.seed_catalog` calls `main()` against a fresh
  `SessionLocal()` and prints `Catalog seed completed.` on success.
- Re-running is **idempotent**: each upsert checks for an existing row and
  refreshes engine fields on `MetricDefinition` / `SignalDefinition` so
  formula and rule changes take effect without manual surgery.
- Admin bootstrap reads `ADMIN_EMAIL`, `ADMIN_PASSWORD`, optional
  `ADMIN_FULL_NAME`. If the env vars are missing, no user is created.

## Dependencies

- Imports: `os`, `datetime.date`, `sqlalchemy.select`,
  `app.core.security.hash_password`, enums from `app.db.enums`,
  `FinancialLineItemDefinition`, `MetricDefinition`, `SignalDefinition`,
  `FinancialPeriod`, `Sector`, `AppUser`, the session factory.
- Must not import demo profiles, synthetic facts, or anything that creates
  `Company` / `CompanyEvent` / `IntelligenceCard` rows.

## Patterns (symmetry)

- New `MetricDefinition`: add the metric to `METRIC_DEFS` and a matching
  `FinancialLineItemDefinition` row to `LINE_ITEMS` when it references a
  new fact code. Then run `pytest tests/test_seed_config.py`.
- New `SignalDefinition`: every leaf in the `rule_json` must reference a
  metric code that exists in `METRIC_DEFS`. The test suite enforces this.
- Wrap inserts with `select(...).first()` for idempotency.

## Verification checklist

- [ ] `python -m app.seed.seed_catalog` succeeds on an empty DB and is a
      no-op the second time.
- [ ] `pytest tests/test_seed_config.py` passes after every change to
      `LINE_ITEMS`, `METRIC_DEFS`, or `SIGNAL_DEFS`.
- [ ] Admin bootstrap works when `ADMIN_EMAIL` / `ADMIN_PASSWORD` are set
      and is skipped silently when they are not.
- [ ] No imports from `app.seed.seed_demo` (the demo seeder has been removed).
