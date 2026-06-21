# models/market

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`MarketDataPoint` — one row per (company, trade_date) holding the OHLCV
snapshot, delivery %, 20-day average volume, market cap, and 52-week
range. Backs the valuation and market-reaction cards.

## Source

- Path: `backend/app/models/market.py`
- Layer: backend-model

## Contract

- Table: `market_data_points`. Unique on `(company_id, trade_date)`.
- Numeric precision matches the rest of the schema (`Numeric(24, 6)` for
  amounts / volumes, `Numeric(12, 4)` for delivery %).
- Migration: [`alembic/versions/0003_market_data.py`](../../alembic/versions/0003_market_data.py).

## Dependencies

- Foreign key on `companies.company_id`.
- The metric engine does **not** read this table directly. The market-data
  router projects the latest snapshot down into `financial_statement_facts`
  rows keyed by `share_price_close`, `volume`, `avg_volume_20d`,
  `market_cap`, `delivery_pct`, `pre_event_close`, `post_event_close`.
  Keep that contract — the engine relies on facts being the single
  read-side surface.

## Patterns (symmetry)

- Idempotent ingest: existing `(company_id, trade_date)` rows are updated
  in place.
- New market fields require:
  1. Column on `MarketDataPoint`.
  2. New row in `seed_catalog.LINE_ITEMS` (so the engine can read it as a fact).
  3. Mapping in `_LINE_ITEM_BY_FIELD` in
     [`routers/v1/market_data.py`](../routers/v1/market_data.py).

## Verification checklist

- [ ] Unique constraint on `(company_id, trade_date)` is enforced.
- [ ] `created_at` populated by server default.
- [ ] Re-import of `app.models` exposes `MarketDataPoint` (`__init__.py`).
