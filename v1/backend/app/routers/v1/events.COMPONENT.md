# routers/v1/events

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed event endpoints under `/v1`. Replaces the ad-hoc dict response in the flat `/events/{id}` route for v1 callers and adds the missing nested-company listing.

## Source

- Path: `backend/app/routers/v1/events.py`
- Prefix: `/v1`
- Tags: `["v1: events"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/events?event_type=&dedupe_periods=&limit=&offset=` (`response_model=list[EventBriefV1]`). Resolves the symbol via `find_company`, filters by optional `event_type`, optionally collapses to one canonical row per period (`dedupe_periods=true` by default), paginates with `offset` + `limit` (default `limit=100`).
- `GET /v1/events/{event_id}` (`response_model=EventDetailV1`). Returns the full event including `raw_facts` (joined from `financial_statement_facts`), `documents`, and a flat `metric_snapshot` for headline numbers.

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select`, models (`CompanyEvent`, `SourceDocument`, `FinancialLineItemDefinition`, `FinancialStatementFact`, `Company`, `FinancialPeriod`, `AppUser`), helpers (`company_brief`, `find_company`, `period_brief`), schemas (`DocumentBrief`, `EventBriefV1`, `EventDetailV1`, `EventRawFacts`).
- Must not: build inline ad-hoc dicts. Always return the typed schemas.

## Patterns (symmetry)

- Ordering: `CompanyEvent.event_date DESC, event_id DESC`. Reuse this across new event listings.
- `raw_facts` only includes `period_value_type == 'CURRENT'` so consumers don't have to filter. Comparison values surface through `IntelligenceObject.metric_comparisons`.
- `metric_snapshot` is a flat `dict[str, float]` keyed by `line_item_code` — Excel / Slack consumers can drop it in without parsing the `raw_facts` array.

## Verification checklist

- [ ] `find_company` used for symbol resolution
- [ ] `response_model` declared on both endpoints
- [ ] Default ordering preserved (`event_date DESC`)
- [ ] `raw_facts` filtered to `period_value_type == 'CURRENT'`
