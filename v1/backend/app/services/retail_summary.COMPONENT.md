# services/retail_summary

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Backs `GET /v1/companies/{symbol}/retail-summary`. Boils the company's latest published intelligence into a consumer-friendly summary + risk + momentum + top 3 points + headline metrics.

## Source

- Path: `backend/app/services/retail_summary.py`
- Layer: backend-service

## Contract

- `build_retail_summary(db, company: Company) -> RetailSummary`.

Module-level mappings:

- `_TONE_BY_DIRECTION` — maps `SignalDirection` to the `Literal` tone used by `RetailSummaryPoint`.

## Dependencies

- Imports: `collections.Counter`, `sqlalchemy.select`, models (`CompanyEvent`, `IntelligenceCard`, `FinancialStatementFact`, `FinancialLineItemDefinition`, `CalculatedMetric`, `MetricDefinition`, `Company`, `FinancialPeriod`), helpers (`company_brief`, `period_brief`), schemas (`RetailSummary`, `RetailSummaryPoint`).

## Patterns (symmetry)

- `risk_level = max(severity over top 6 cards)`.
- `momentum = modal signal_direction over top 6 cards`.
- `simple_summary = top card's one_line_summary` (the card with the highest `card_priority`).
- `headline_metrics` includes Revenue, EBITDA, PAT (from `financial_statement_facts`) and EBITDA Margin (from `calculated_metrics`). Items are skipped when the fact is missing.

## Verification checklist

- [ ] At most three points in `top_3_points` (deduplicated by `card_type`)
- [ ] `headline_metrics` items use `{name, value, unit}` keys exactly
- [ ] Returns a Pydantic model
