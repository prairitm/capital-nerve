# routers/search

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Lightweight ILIKE search across companies, events, and intelligence cards. Powers both the top-bar dropdown and the Search page.

## Source

- Path: `backend/app/routers/search.py`
- Prefix: `/search`
- Tags: `["search"]`
- Layer: backend-router

## Endpoints

- `GET /search?q=` — `q` is required (`Query(min_length=1)`). Returns `{ companies, events, cards }`.

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select` / `or_`, models (`Company`, `Sector`, `CompanyEvent`, `IntelligenceCard`, `AppUser`), helper `company_brief`.

## Patterns (symmetry)

- Single string-LIKE pattern: `f"%{q.lower()}%"`. Reuse this when adding a new search dimension.
- Caps: 10 companies, 10 events, 15 cards. Keep the same caps when adding new types (or document the change in the frontend `SearchPage` and `TopSearch` components).
- Companies are searched on `company_name`, `nse_symbol`, `bse_code`, `short_name`. Events on `event_title` and `summary_text`. Cards on `headline`, `one_line_summary`, `detailed_explanation`.
- The response uses ad hoc dicts (no `response_model`). When you add a field, mirror it in the frontend `SearchResult` interface.

## Verification checklist

- [ ] Pattern uses lower-cased `f"%{q.lower()}%"`
- [ ] Caps preserved (10 / 10 / 15)
- [ ] Field additions mirrored in `frontend/src/api/types.ts SearchResult`
- [ ] No new search type added without updating `TopSearch` and `SearchPage`
