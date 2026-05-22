# `backend/app/seed/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Catalog bootstrap data for CapitalNerve. This layer writes only the
**reference data** the pipeline relies on: line items, metric definitions,
signal definitions, financial periods, and a minimal sector list. No
companies, events, cards, evidence, watchlists, or users are seeded here;
those come from real ingestion (`POST /ingest/upload`) and admin actions.

## Modules

- [`seed_catalog.py`](seed_catalog.py) — idempotent catalog seeder; the only
  seeder that runs in production. Exposes `seed_catalog(db)` plus
  `upsert_sectors`, `upsert_periods`, `upsert_line_items`,
  `upsert_metric_defs`, `upsert_signal_defs`, and `upsert_admin_user`.

## Rules

- The seeder must be **idempotent**. Re-running it on an existing database
  must not raise; existence checks guard every insert and engine fields on
  metric/signal definitions are refreshed in place.
- When you add a new model column that the pipeline reads, update the
  catalog seeder in the same change so production databases pick it up.
- Use `hash_password` from [`../core/security.py`](../core/security.py) for
  the optional admin bootstrap — never inline bcrypt calls.
- Admin bootstrap is opt-in via `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and
  optional `ADMIN_FULL_NAME` env vars. If unset, no users are created and
  deployers must call `POST /auth/signup` or create users manually.
- Do **not** seed companies, events, cards, evidence, watchlists, alerts,
  or non-admin users from this layer.
- Run from `start.sh` after `alembic upgrade head`; manual invocation is
  `python -m app.seed.seed_catalog`.
