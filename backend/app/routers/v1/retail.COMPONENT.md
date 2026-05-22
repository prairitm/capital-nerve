# routers/v1/retail

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`GET /v1/companies/{symbol}/retail-summary` — consumer brokerage wedge. Boils the company's latest published intelligence into a short summary + risk + momentum + top 3 points + headline metrics.

## Source

- Path: `backend/app/routers/v1/retail.py`
- Prefix: `/v1`
- Tags: `["v1: retail"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/retail-summary` (`response_model=RetailSummary`).

## Dependencies

- Imports: `fastapi`, models (`AppUser`), helpers (`find_company`), schemas (`RetailSummary`), service (`build_retail_summary`).
- Must not: hold its own SQL. The aggregation rules live in [`../../services/retail_summary.py`](../../services/retail_summary.py).

## Patterns (symmetry)

- Thin router — find company → delegate to service.

## Verification checklist

- [ ] Symbol resolved via `find_company`
- [ ] No SQL in router body
- [ ] `response_model=RetailSummary`
