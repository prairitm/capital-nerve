# routers/v1/portfolio

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`POST /v1/portfolio/monitor` — the enterprise portfolio monitoring wedge. Caller posts a list of symbols + filters; service returns ranked `PortfolioAlert` rows each linking to the underlying `IntelligenceObjectBrief`s.

## Source

- Path: `backend/app/routers/v1/portfolio.py`
- Prefix: `/v1`
- Tags: `["v1: portfolio"]`
- Layer: backend-router

## Endpoints

- `POST /v1/portfolio/monitor` (`response_model=PortfolioMonitorResponse`). Request body: `PortfolioMonitorRequest` (`symbols`, optional `min_importance` / `severity_in` / `direction_in`, `limit_per_company`).

## Dependencies

- Imports: `fastapi`, models (`AppUser`), schemas (`PortfolioMonitorRequest`, `PortfolioMonitorResponse`), service (`monitor_portfolio`).
- Must not: hold its own SQL. The wedge logic lives in [`../../services/portfolio_monitor.py`](../../services/portfolio_monitor.py).

## Patterns (symmetry)

- Thin router — find user → delegate to `monitor_portfolio(db, payload)` → return response.
- Symbol resolution + ranking + filtering all happen in the service so the same logic can power scheduled webhooks later.

## Verification checklist

- [ ] Single `POST` endpoint declared with `response_model`
- [ ] No SQL or service logic in the router body
- [ ] Auth dep via `get_current_user`
