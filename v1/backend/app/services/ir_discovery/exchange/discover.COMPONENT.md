# exchange/discover

> Inherits: ./_BASE.md

## Purpose

The single async entry point used by `bulk_ingest`'s tier-1 path.
Combines BSE + NSE filings for one `(Company, PeriodSpec)` pair,
projects the rows into a `PeriodAssetSet`, and returns a
`DiscoveryResult` whose `source_by_asset_key` maps each filled slot to
`"bse"` or `"nse"`.

## Source

- Path: `backend/app/services/ir_discovery/exchange/discover.py`
- Layer: backend-service-helper

## Contract

- `discover_period_assets(company, period, *, db=None,
  asset_keys=None, bse_window_days_after=None) -> DiscoveryResult`.
  Pure-read; never writes ingestion tables. Lazy-resolves
  `Company.bse_code` only when `db` is supplied.
- `DiscoveryResult` carries:
  - `assets: PeriodAssetSet` — the *primary* candidate per slot.
  - `source_by_asset_key: dict[str, "bse"|"nse"|"agent"]` — provenance
    of each primary URL.
  - `fallback_by_asset_key: dict[str, list[(AssetMatch, source)]]` —
    secondary candidates per slot, in priority order. Download-side
    code is expected to walk the primary first, then each fallback
    on `FetchError` until one succeeds.
  - Helpers: `.covered_keys()`, `.missing_keys(required)`.
- `merge_with_agent(exchange, agent_assets, *, keys_to_fill)` —
  combines the agent fallback into the exchange result. For each
  key in `keys_to_fill`:
    - If exchange left the slot empty → agent's URL becomes primary
      (source `"agent"`).
    - If exchange filled the slot → agent's URL is appended to that
      slot's fallback list with source `"agent"`. The exchange tier
      still wins the primary, but a broken BSE/NSE attachment no
      longer wastes the agent's research.

## Dependencies

- May import: `asyncio`, `sqlalchemy.orm.Session`, `app.db.enums`,
  sibling modules (`bse_client`, `nse_client`, `bse_master`,
  `schemas`), and `..schemas` (`PeriodAssetSet`, `AssetMatch`,
  `DOC_TYPE_BY_ASSET_KEY`).
- Must not: import `app.services.ir_discovery.agent` (the agent
  fallback is wired in the CLI, not here — keeps tier-1 dependency-free).

## Patterns (symmetry)

- Annual periods only consider the `annual_report` slot; quarterly
  periods skip it. See `_filter_keys_for_period`.
- BSE first (always tried when a code is known), NSE next (always
  tried when an `nse_symbol` is known — even if BSE filled every slot,
  because matching NSE filings are recorded as download-time fallbacks).
- "Latest filing per `DocumentType`" wins: companies sometimes file
  amendments / regional-language versions. Highest `filing_date` is
  kept as the primary; older same-type filings are dropped (we don't
  fall back to amendments).
- When BSE and NSE both have the same `DocumentType`, BSE is the
  primary and NSE goes into the fallback list. Order matters: tier-1
  fallbacks come first, then any agent-fallbacks added later by
  `merge_with_agent`.
- All HTTP work goes through `asyncio.to_thread` so the orchestrator
  doesn't block the event loop.

## Verification checklist

- [ ] All four asset slots may be filled by tier-1 alone (test:
      `test_exchange_discover.py`).
- [ ] Companies without `bse_code` and without `db` simply skip BSE
      without raising.
- [ ] When BSE covers every slot, NSE is *still* queried and any
      same-type NSE filings are stashed in `fallback_by_asset_key`.
- [ ] `merge_with_agent` never overwrites an exchange-tier hit, but
      does append the agent's URL to that slot's fallback list.
- [ ] `merge_with_agent` preserves any pre-existing tier-1 fallbacks
      (NSE-as-fallback) and appends agent fallbacks after them.
- [ ] Async path: clients must run inside `asyncio.to_thread`, not
      inline.
