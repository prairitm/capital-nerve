# routers/_helpers

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Shared ORM→Pydantic mappers used by every router that returns cards / companies / periods. Keeps the casting and nullability rules in one place.

## Source

- Path: `backend/app/routers/_helpers.py`
- Layer: backend-routers

## Contract

- `company_brief(company, sector=None) -> CompanyBrief`
- `period_brief(period | None) -> PeriodBrief | None`
- `build_source_label(period, event, document) -> str | None` — chooses the best human label given what is available.
- `card_brief(card, company, period, event, document=None) -> CardBrief`
- `find_company(db, symbol) -> Company | None` — case-insensitive lookup against `nse_symbol` and `bse_code`.

## Dependencies

- Imports SQLAlchemy `Session`, ORM models (`CompanyEvent`, `SourceDocument`, `IntelligenceCard`, `Company`, `FinancialPeriod`, `Sector`), and schemas (`CardBrief`, `CompanyBrief`, `PeriodBrief`).
- Must not: raise `HTTPException` — that is the router's job.

## Patterns (symmetry)

- All `Numeric` casts to Python `float` happen here (e.g. `float(company.market_cap_cr) if ... is not None else None`). Routers should never repeat these casts.
- `card_brief` builds `source_label` via `build_source_label`. Do not bypass it.
- `find_company` upper-cases the input and uses `or_(nse_symbol == X, bse_code == X)`. New symbol resolution must reuse this helper.

## Verification checklist

- [ ] New response field added to the matching `*_brief` helper
- [ ] Numeric casting kept in helpers, not in routers
- [ ] `find_company` used wherever a symbol lookup is needed
- [ ] No `HTTPException` raised here
