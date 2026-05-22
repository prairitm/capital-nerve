# models/user

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

User accounts, watchlists, watch items, alert rules, and alerts.

## Source

- Path: `backend/app/models/user.py`
- Layer: backend-models

## Contract

- `AppUser` — `email` (unique, nullable), `phone` (unique, nullable), `full_name`, `hashed_password`, `user_type` enum.
- `Watchlist` — `user_id` FK, `watchlist_name` (default `"Default Watchlist"`). One default per user; uniqueness on `(user_id, watchlist_name)`.
- `WatchlistCompany` — many-to-many between `Watchlist` and `Company`; uniqueness on `(watchlist_id, company_id)`.
- `UserWatchItem` — thesis monitor: title + description + optional metric + threshold.
- `AlertRule` — declarative alert rule with category / severity filter and delivery channels.
- `Alert` — materialized alert row delivered to the user.

## Dependencies

- Imports: SQLAlchemy primitives, `JSONB`, `Base`, enums (`SeverityLevel`, `UserType`).

## Patterns (symmetry)

- Cascade on user-owned tables: `Watchlist`, `WatchlistCompany`, `UserWatchItem`, `AlertRule`, `Alert` all cascade with the `AppUser` row.
- Company symbol lookup uses `nse_symbol or bse_code`; the auth router populates `email` from the signup request.
- `AppUser` is the only model with a unique nullable `email` — `phone` is also unique nullable for future SMS auth.
- `UserType` defaults to `RETAIL`. Admin is created only by the seed.

## Verification checklist

- [ ] Cascade rules preserved
- [ ] New user-scoped tables include `user_id` FK with `ondelete="CASCADE"`
- [ ] Schema additions mirrored in [`../schemas/common.py`](../schemas/common.py) and `../../../frontend/src/api/types.ts`
- [ ] Alembic migration created
