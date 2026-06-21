# routers/v1/credit

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`GET /v1/companies/{symbol}/credit-risk-signals` — credit monitoring wedge for bank / NBFC consumers. Returns the credit-relevant slice of `generated_signals` bucketed by dimension.

## Source

- Path: `backend/app/routers/v1/credit.py`
- Prefix: `/v1`
- Tags: `["v1: credit"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/credit-risk-signals` (`response_model=CreditRiskResponse`).

## Dependencies

- Imports: `fastapi`, models (`AppUser`), helpers (`find_company`), schemas (`CreditRiskResponse`), service (`build_credit_risk_response`).
- Must not: implement the credit-dimension mapping inline. It lives in [`../../services/credit_risk.py`](../../services/credit_risk.py).

## Patterns (symmetry)

- Thin router — find company → delegate to service.
- The service filters strictly — signals that don't map to a credit dimension are dropped (this is a credit-only view, not a generic feed).

## Verification checklist

- [ ] Symbol resolved via `find_company`
- [ ] No SQL in router body
- [ ] `response_model=CreditRiskResponse`
