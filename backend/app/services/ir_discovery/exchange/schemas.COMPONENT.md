# exchange/schemas

> Inherits: ./_BASE.md

## Purpose

Defines the unified `ExchangeFiling` row that BSE / NSE clients return,
the category-to-`DocumentType` mappings the orchestrator uses to decide
which asset slot a filing fills, and the `FilingWindow` helper used to
compute the date range we ask the exchange for.

## Source

- Path: `backend/app/services/ir_discovery/exchange/schemas.py`
- Layer: backend-service-helper

## Contract

- `ExchangeFiling` — frozen dataclass with `source` (`"bse"|"nse"`),
  `company_id_at_source`, `filing_date`, `headline`, `category`,
  `subcategory`, `attachment_url`, `document_type` (mapped or `None`),
  `source_page`, and the verbatim `raw` row.
- `BSE_CATEGORY_MAP` / `NSE_CATEGORY_MAP` — `(category, subcategory)`
  keys to `DocumentType` values. Lookups via :func:`map_bse_category` /
  :func:`map_nse_category` first try exact match, then wildcard
  (`subcategory=None`).
- `FilingWindow.for_period(period_start, period_end, *, is_annual)` —
  returns the inclusive `[period_end + 1d, period_end + 60d]`
  (quarterly) or `+180d` (annual) window.

## Dependencies

- May import: `app.db.enums.DocumentType`, stdlib (`dataclasses`,
  `datetime`, `typing`).
- Must not: import `httpx`, SQLAlchemy, or anything from
  `ir_discovery.agent` / `ir_discovery.ingest`.

## Patterns (symmetry)

- All dataclasses are `frozen=True` so the orchestrator can hash /
  diff filing rows.
- Wildcard subcategory entries (`(category, None)`) live alongside
  explicit ones — the lookup helper handles fall-through.
- Categories not in the map are dropped silently. Add new mappings
  here, never inline in clients.

## Verification checklist

- [ ] New mappings added in alphabetical order within their section.
- [ ] No `(cat, sub)` collides between BSE and NSE — they live in
  separate dicts intentionally.
- [ ] `FilingWindow.start <= FilingWindow.end` for every period.
- [ ] `ExchangeFiling.raw` retains the original dict (used for
  debugging when a row mis-maps).
