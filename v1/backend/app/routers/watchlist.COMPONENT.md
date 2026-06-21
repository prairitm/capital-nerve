# routers/watchlist

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

CRUD for the user's tracked companies plus a watchlist summary panel.

## Source

- Path: `backend/app/routers/watchlist.py`
- Prefix: `/watchlist`
- Tags: `["watchlist"]`
- Layer: backend-router

## Endpoints

- `GET /watchlist` — returns `{ watchlist_id, name, summary, companies }`. Summary counters: tracked, new_events, negative_signals, positive_signals, red_flags. Each company entry includes its `latest_card_*` snippet.
- `POST /watchlist/companies` — body `AddCompanyRequest { company_id: int }`. Idempotent: re-adding returns `{added: false}`.
- `DELETE /watchlist/companies/{company_id}` — idempotent: missing row returns `{removed: false}`.

## Dependencies

- Imports: `fastapi`, `pydantic.BaseModel`, `sqlalchemy.select`, models (`IntelligenceCard`, `Company`, `Sector`, `AppUser`, `Watchlist`, `WatchlistCompany`), helper `company_brief`.

## Patterns (symmetry)

- `_ensure_default(db, user)` lazily creates the default watchlist on first use. Reuse this when a new endpoint needs the user's primary watchlist.
- Add and delete endpoints are **idempotent**: they return a structured response indicating whether the operation actually changed anything.
- Latest-card lookup uses `order_by(card_priority desc, created_at desc).limit(1)` — match this when surfacing "latest card" elsewhere.
- Use `company_brief(company, sector)` for the nested company DTO, not an inline dict.

## Verification checklist

- [ ] Endpoints idempotent
- [ ] Default watchlist created via `_ensure_default`
- [ ] Latest-card ordering matches the rest of the app
- [ ] `company_brief` reused for nested companies
