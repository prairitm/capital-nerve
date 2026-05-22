# services/portfolio_monitor

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Backs `POST /v1/portfolio/monitor`. Resolves NSE/BSE symbols to companies, pulls the top published intelligence cards per company, filters by severity / direction / min importance, and returns ranked `PortfolioAlert` rows.

## Source

- Path: `backend/app/services/portfolio_monitor.py`
- Layer: backend-service

## Contract

- `monitor_portfolio(db, payload: PortfolioMonitorRequest) -> PortfolioMonitorResponse`.

## Dependencies

- Imports: `sqlalchemy.select / or_`, models (`CompanyEvent`, `IntelligenceCard`, `Company`, `FinancialPeriod`), schemas (`IntelligenceObjectBrief`, `PortfolioAlert`, `PortfolioMonitorRequest`, `PortfolioMonitorResponse`), service (`build_intelligence_object_brief`).
- Must not: raise `HTTPException`. Unresolved symbols are surfaced through `unresolved_symbols`, not as errors.

## Patterns (symmetry)

- Symbols are uppercased and matched against `nse_symbol` OR `bse_code`.
- The canonical join is the same as `routers/cards.list_cards` minus `SourceDocument` (we don't render document references in the alert payload).
- Alerts are sorted: matched first, then by top object's `importance_score` desc.
- `top_objects` reuses `IntelligenceObjectBrief` so consumers can drop the alert into a UI without follow-up calls.

## Verification checklist

- [ ] Unresolved symbols surface in `unresolved_symbols`, not as 404s
- [ ] Each alert's `top_objects` is capped by `payload.limit_per_company`
- [ ] Alerts sorted (matched first, importance desc)
- [ ] Returns Pydantic models, not raw dicts
