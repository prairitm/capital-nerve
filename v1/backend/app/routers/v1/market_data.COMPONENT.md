# routers/v1/market_data

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

`POST /v1/market-data/{company_id}` — admin-only ingest for daily market
data. Writes / updates `MarketDataPoint` rows and projects the latest
snapshot into `financial_statement_facts` so valuation and market-reaction
metrics stay on the same engine path as financial line items.

## Source

- Path: `backend/app/routers/v1/market_data.py`
- Layer: backend-router

## Contract

- Request body: `MarketDataIngestRequest`
  - `points: list[MarketDataPointIn]` (`min_length=1`).
  - `period_id: int | None` — required only when projection to
    `financial_statement_facts` is desired.
- Each `MarketDataPointIn` carries `trade_date`, OHLCV, optional
  `delivery_qty` / `delivery_pct`, optional `avg_volume_20d`,
  `market_cap`, `fifty_two_week_high/low`, plus `pre_event_close` and
  `post_event_close` when ingesting an event-window snapshot.
- Response: `{company_id, points_written, facts_written, period_id}`.
- Auth: admin only via `get_current_admin`.

## Field → fact code mapping

| Request field | Fact `normalized_code` |
|---------------|-----------------------|
| `close_price` | `share_price_close` |
| `volume` | `volume` |
| `delivery_pct` | `delivery_pct` |
| `avg_volume_20d` | `avg_volume_20d` |
| `market_cap` | `market_cap` |
| `pre_event_close` | `pre_event_close` |
| `post_event_close` | `post_event_close` |

Adding a new code requires:
1. New column on `MarketDataPoint`.
2. New `LINE_ITEMS` row in [`seed_catalog.py`](../../seed/seed_catalog.py).
3. New entry in `_LINE_ITEM_BY_FIELD` here.

## Dependencies

- May import: `app.models.market`, `app.models.facts`, `app.models.master`,
  `app.core.deps`.
- Must not import: pipeline stages directly (the metric engine reads facts).

## Patterns (symmetry)

- Idempotent: re-ingesting the same `(company_id, trade_date)` updates the
  existing point.
- The fact projection is keyed by the unique `(company_id, period_id,
  line_item_def_id, consolidation, period_value_type)` constraint and uses
  `STANDALONE` / `UNAUDITED` defaults — market data has no audit status.

## Verification checklist

- [ ] 401 / 403 from a non-admin token.
- [ ] 404 when `company_id` doesn't exist or `period_id` is supplied but
      missing.
- [ ] Re-ingest with the same payload returns identical
      `points_written` / `facts_written` and updates rather than inserts.
- [ ] When `period_id` is omitted, `facts_written == 0` (the metric engine
      still has the old snapshot to read).
