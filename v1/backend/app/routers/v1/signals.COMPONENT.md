# routers/v1/signals

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed signal endpoints under `/v1`. Same data as the flat `/signals` router but the response models are `SignalBriefV1` / `SignalDetailV1` so OpenAPI documents the contract.

## Source

- Path: `backend/app/routers/v1/signals.py`
- Prefix: `/v1`
- Tags: `["v1: signals"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/signals?category=&severity=&direction=&limit=` (`response_model=list[SignalBriefV1]`).
- `GET /v1/signals?category=&severity=&direction=&sector=&min_confidence=&limit=` (`response_model=list[SignalBriefV1]`). Cross-company feed for the enterprise screener.
- `GET /v1/signals/{signal_id}` (`response_model=SignalDetailV1`). Adds `rule_json`, `calculation: SignalCalculation`, and `evidence`.

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select`, models (`GeneratedSignal`, `SignalDefinition`, `CalculatedMetric`, `CardEvidence`, `IntelligenceCard`, `MetricDefinition`, `Company`, `Sector`, `FinancialPeriod`, `AppUser`), helpers (`company_brief`, `find_company`, `period_brief`), schemas (`EvidenceItem`, `SignalBriefV1`, `SignalCalculation`, `SignalDetailV1`).
- Must not: reuse the flat `/signals` helpers — those return `dict[str, Any]`. v1 has its own typed `_signal_brief` builder.

## Patterns (symmetry)

- The canonical join is `GeneratedSignal → SignalDefinition → Company → Sector (outer) → FinancialPeriod (outer)` — encapsulated in `_signal_query()`. Reuse it for any new signal listing.
- Ordering: `signal_score DESC NULLS LAST, created_at DESC`. Match the flat `/signals` router.
- `SignalCalculation.current_value` / `previous_value` come from `calculated_metrics` row referenced by `GeneratedSignal.primary_metric_id`. Don't try to re-derive from `metric_refs`.

## Verification checklist

- [ ] `_signal_query` reused (no duplicate join)
- [ ] `response_model` declared
- [ ] Evidence rows limited to 12 (matches signal_context defaults)
- [ ] `SignalDetailV1` strict superset of `SignalBriefV1`
