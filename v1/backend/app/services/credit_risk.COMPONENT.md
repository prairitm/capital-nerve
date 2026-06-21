# services/credit_risk

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Backs `GET /v1/companies/{symbol}/credit-risk-signals`. Filters `generated_signals` to credit-relevant entries, buckets them by `credit_dimension`, and computes an `overall_risk` level.

## Source

- Path: `backend/app/services/credit_risk.py`
- Layer: backend-service

## Contract

- `build_credit_risk_response(db, company: Company) -> CreditRiskResponse`.

Module-level mappings:

- `_CODE_TO_DIMENSION` — explicit signal-code overrides (e.g. `audit_redflag → auditor`).
- `_CATEGORY_TO_DIMENSION` — signal-category fallback (e.g. `red_flag → auditor`).
- `_SEVERITY_RANK` / `_RANK_TO_SEVERITY` — used to compute `overall_risk`.

## Dependencies

- Imports: `sqlalchemy.select`, models (`GeneratedSignal`, `SignalDefinition`, `Company`, `FinancialPeriod`), helpers (`company_brief`, `period_brief`), schemas (`CreditDimension`, `CreditRiskResponse`, `CreditRiskSignal`).

## Patterns (symmetry)

- Signals are filtered strictly — `_dimension_for` returning `None` drops the signal. This is a credit-only view, not a generic feed.
- `overall_risk` = highest severity among NEGATIVE / MIXED signals. POSITIVE / NEUTRAL signals do not raise the risk floor.
- Code overrides win over category fallbacks.

## Verification checklist

- [ ] Only credit-mapped signals returned
- [ ] `overall_risk` matches the actual max severity among NEGATIVE/MIXED signals
- [ ] Ordering: `signal_score DESC NULLS LAST, created_at DESC`
- [ ] Returns a Pydantic model
