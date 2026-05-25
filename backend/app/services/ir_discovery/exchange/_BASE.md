# services/ir_discovery/exchange

> Inherits: [../_BASE.md](../_BASE.md)

## Purpose

Tier-1 IR-discovery client. Pulls structured corporate-filings data from
the BSE and NSE corporate-announcement APIs (which all listed Indian
companies are mandated to publish under SEBI LODR Reg 30 / 33), maps each
filing's category to a `DocumentType`, and returns a `PeriodAssetSet`
that the bulk ingestor can hand straight to `ingest_one`.

This is the deterministic, free, mandate-backed primary path. The
existing OpenAI-Agents WebSearch path in
[`../agent.py`](../agent.py) becomes a tier-2 fallback that is only
called for asset slots the exchanges did not cover.

## File layout

| File | Owns |
|------|------|
| [`__init__.py`](__init__.py) | Re-exports `discover_period_assets`. |
| [`schemas.py`](schemas.py) | `ExchangeFiling` dataclass + `BSE_CATEGORY_MAP` / `NSE_CATEGORY_MAP`. |
| [`bse_client.py`](bse_client.py) | BSE `AnnGetData` JSON client. |
| [`nse_client.py`](nse_client.py) | NSE `corporate-announcements` JSON client (with cookie warmup). |
| [`bse_master.py`](bse_master.py) | BSE listed-equity master cache + `nse_symbol -> bse_code` resolver. |
| [`discover.py`](discover.py) | Orchestrator that combines BSE + NSE into a `PeriodAssetSet`. |

## Cross-cutting rules

- **No HTML scraping.** Both clients only consume the documented JSON
  endpoints. If the JSON shape changes, fail loudly so the agent
  fallback takes over.
- **Pure read path.** Modules in this package never write to ingestion
  tables. The only DB write happens inside `bse_master.lazy_resolve_bse_code`
  (it persists a resolved `Company.bse_code` once the master list confirms
  it).
- **Per-pair session.** Each call to `discover_period_assets` opens a
  fresh `httpx.Client`. NSE's session-cookie warmup is encapsulated
  inside `nse_client.list_filings`; callers do not see it.
- **Mapped categories only.** Filings whose `(category, subcategory)`
  pair is not in `BSE_CATEGORY_MAP` / `NSE_CATEGORY_MAP` are dropped
  with a DEBUG log line. We never hand a filing to `ingest_one` whose
  `document_type` we couldn't determine.
- **Tier-1 is silent on failure.** Network errors / 401s / empty
  responses produce an empty `PeriodAssetSet` and a logged warning, so
  the agent fallback path runs.

## Required reading before changes here

- [../_BASE.md](../_BASE.md) — package-wide conventions.
- [../schemas.py](../schemas.py) — the canonical `PeriodAssetSet`,
  `AssetMatch`, and `DOC_TYPE_BY_ASSET_KEY` consumers.
- [../../ingest_common.py](../../ingest_common.py) — period helpers
  (especially `quarter_date_bounds` and `format_quarterly_display_label`).
