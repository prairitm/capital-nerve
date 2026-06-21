# exchange/nse_client

> Inherits: ./_BASE.md

## Purpose

Synchronous client for NSE's corporate-announcements API. Same shape
as the BSE client but adds session-cookie warmup — NSE blocks any call
that arrives without the `nsit` / `nseappid` cookies the homepage sets.

## Source

- Path: `backend/app/services/ir_discovery/exchange/nse_client.py`
- Layer: backend-service-helper

## Contract

- `list_filings(*, symbol: str, from_date: date, to_date: date,
  timeout: float = 30.0, session: Optional[_NSESession] = None)
  -> list[ExchangeFiling]`.
- Endpoint: `GET https://www.nseindia.com/api/corporate-announcements`.
- Params: `index=equities`, `from_date=DD-MM-YYYY`, `to_date=DD-MM-YYYY`,
  `symbol=...`.
- Returns `[]` on any failure (HTTP error, empty payload, JSON decode).

## Dependencies

- May import: `httpx`, stdlib, `.schemas` (`ExchangeFiling`,
  `map_nse_category`).
- Must not: import `bse_client`, `discover`, `bse_master`.

## Patterns (symmetry)

- `_NSESession` does the warmup (`GET https://www.nseindia.com`) lazily,
  on the first `get_json` call.
- A `401` / `403` triggers exactly one re-warm + retry; further failures
  return `None` so the orchestrator falls back.
- Date format: `DD-MM-YYYY` (NSE) vs. `YYYYMMDD` (BSE).
- Like the BSE client, multiple key spellings are tolerated.

## Verification checklist

- [ ] Warmup is performed before the first JSON call.
- [ ] Retry runs at most once per `list_filings` invocation.
- [ ] `attchmntFile` URLs without scheme are upgraded to `https://`.
- [ ] Tests use `httpx.MockTransport` to assert the warmup happens.
