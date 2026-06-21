# routers/v1/result_brief

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`GET /v1/companies/{symbol}/result-brief?period=` — sell-side analyst briefing for one quarterly result. Pre-assembles key positives / negatives / peer comparison / model-update fields.

## Source

- Path: `backend/app/routers/v1/result_brief.py`
- Prefix: `/v1`
- Tags: `["v1: result-brief"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/result-brief?period=` (`response_model=ResultBrief`). Returns 404 when the resolved period has no `QUARTERLY_RESULT` event.

## Dependencies

- Imports: `fastapi`, models (`AppUser`), helpers (`find_company`), schemas (`ResultBrief`), service (`build_result_brief`).
- Must not: assemble the brief inline. The service is the single derivation point.

## Patterns (symmetry)

- Thin router — find company → delegate to service.
- `period=` is matched via `ilike` on `display_label` then `fy_label` inside the service. When omitted the service falls back to the latest quarterly result.

## Verification checklist

- [ ] Symbol resolved via `find_company`
- [ ] 404 raised when the service returns `None`
- [ ] `response_model=ResultBrief`
