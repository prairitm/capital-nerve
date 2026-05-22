# models/master

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Master / reference tables: `Sector`, `Company`, `Security`, `FinancialPeriod`. These tables anchor every other domain.

## Source

- Path: `backend/app/models/master.py`
- Layer: backend-models

## Contract

- `Sector` — `sector_id`, `sector_name`, optional `industry_group`/`industry`/`sub_industry`. `companies` back-populated.
- `Company` — identity (`company_name`, `legal_name`, `short_name`), unique exchange codes (`nse_symbol`, `bse_code`, `isin`), `sector_id` FK, `status` enum, `market_cap_cr`, `last_price`.
- `Security` — exchange-symbol mapping (`UniqueConstraint("exchange", "symbol")`).
- `FinancialPeriod` — fiscal year + quarter + period type with display label. Uniqueness on `(fy_year, quarter, period_type)`.

## Dependencies

- Imports: `sqlalchemy` typing primitives, `Base`, enums (`CompanyStatus`, `ExchangeCode`, `PeriodType`).

## Patterns (symmetry)

- Symbols (`nse_symbol`, `bse_code`, `isin`) are unique constraints — preserve uniqueness when seeding or migrating.
- `Company.status` defaults to `ACTIVE`; only admin endpoints (`POST /admin/companies`, future status updates) should mutate it.
- `FinancialPeriod.display_label` is the human-readable label rendered by the frontend (`PeriodBrief.display_label`). Keep this stable.

## Verification checklist

- [ ] New master fields added to the matching Pydantic schema in [`../schemas/common.py`](../schemas/common.py)
- [ ] Frontend `CompanyBrief` / `PeriodBrief` updated in [`../../../frontend/src/api/types.ts`](../../../frontend/src/api/types.ts)
- [ ] Alembic migration created
- [ ] Uniqueness constraints preserved
