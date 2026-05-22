# routers/v1/intelligence_objects

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

The centerpiece of the v1 namespace — endpoints that return the canonical `IntelligenceObject` shape. Every response goes through [`../../services/intelligence_object_builder.py`](../../services/intelligence_object_builder.py).

## Source

- Path: `backend/app/routers/v1/intelligence_objects.py`
- Prefix: `/v1`
- Tags: `["v1: intelligence-objects"]`
- Layer: backend-router

## Endpoints

- `GET /v1/companies/{symbol}/intelligence-objects?period=&card_type=&direction=&severity=&min_importance=&limit=` (`response_model=list[IntelligenceObjectBrief]`).
- `GET /v1/intelligence-objects?feed=&tab=&company=&sector=&direction=&severity=&card_type=&min_importance=&period=&limit=` (`response_model=list[IntelligenceObjectBrief]`). Home / watchlist feed (`feed=home|watchlist`, `tab` pulse filters).
- `GET /v1/intelligence-objects/summary` (`response_model=FeedSummaryV1`). Market pulse counters for the home strip.
- `GET /v1/intelligence-objects/{object_id}` (`response_model=IntelligenceObject`). Full payload.

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select`, models (`IntelligenceCard`, `CompanyEvent`, `SourceDocument`, `Company`, `FinancialPeriod`, `Sector`, `AppUser`), helpers (`find_company`), builders (`build_intelligence_object`, `build_intelligence_object_brief`).
- Must not: assemble an `IntelligenceObject` inline. Always go through the builder so derived fields stay consistent.

## Patterns (symmetry)

- Canonical join in `_io_query()`: `IntelligenceCard → Company → FinancialPeriod (outer) → CompanyEvent (outer) → SourceDocument (outer)`.
- Home / watchlist feeds order by `CompanyEvent.event_date DESC NULLS LAST`, then `created_at`, then `card_id` (newest events first). Company-scoped lists keep importance ordering.
- `feed` + `tab` query params mirror the former flat `/cards` filters (`results`, `verdicts`, `red_flags`, etc.).
- `watch_next` cards are excluded from listings — they are not user-facing intelligence objects.
- `period=` accepts either `display_label` (`Q4 FY2025-26`) or `fy_label` (`FY2025-26`) via `ilike` match.

## Verification checklist

- [ ] List endpoints return `IntelligenceObjectBrief`, by-id returns `IntelligenceObject`
- [ ] All payloads built via the builder service (no inline assembly)
- [ ] `watch_next` excluded from listings
- [ ] `min_importance` bounded with `ge=0, le=100`
- [ ] Default ordering preserved
