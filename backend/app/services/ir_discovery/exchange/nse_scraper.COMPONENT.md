# exchange/nse_scraper

> Inherits: ./_BASE.md

## Purpose

Alternate tier-1 IR discovery: a no-date-range scrape of NSE's
`corporate-announcements` JSON feed, matched against the requested
`PeriodSpec` by lowercased text markers. Triggered by the
`--nse-scraper` flag on
[`app/scripts/bulk_ingest.py`](../../scripts/bulk_ingest.COMPONENT.md);
mutually exclusive with the default BSE+NSE-JSON tier-1 and with the
OpenAI agent tier-2.

## Source

- Path: `backend/app/services/ir_discovery/exchange/nse_scraper.py`
- Layer: backend-service

## Contract

- `discover_period_assets_via_scraper(company: CompanyTarget,
  period: PeriodSpec, *, asset_keys: Iterable[str] | None = None,
  session: _NSESession | None = None, payload: object | None = None)
  -> DiscoveryResult`.
- Endpoint hit when `payload` is `None`:
  `GET https://www.nseindia.com/api/corporate-announcements
  ?index=equities&symbol=<SYM>&reqXbrl=false` (no `from_date` /
  `to_date`).
- Source label written on every filled key:
  `SOURCE_LABEL = "nse_scraper"`. Flows through to
  `IngestOutcome.assets[].discovery_source` and
  `SourceDocument.meta.ir_discovery.discovery_source`.
- Always returns an empty `fallback_by_asset_key`. This tier never
  produces alternate URLs — the agent fallback is off by design when
  this tier runs.
- Empty / failed fetches degrade to an empty `DiscoveryResult` (never
  raises). The CLI is responsible for caching the payload across
  periods for the same symbol.

## Dependencies

- May import: stdlib, `app.db.enums.DocumentType`,
  `app.services.ir_discovery.exchange.nse_client`
  (`_NSESession`, `_parse_dt`, `_ANN_PAGE_TEMPLATE`),
  `app.services.ir_discovery.exchange.schemas` (`map_nse_category`),
  `app.services.ir_discovery.schemas` (`AssetMatch`, `CompanyRef`,
  `CompanyTarget`, `DOC_TYPE_BY_ASSET_KEY`, `PeriodAssetSet`,
  `PeriodSpec`).
- Lazy import: `app.services.ir_discovery.exchange.discover.DiscoveryResult`
  inside `discover_period_assets_via_scraper` (avoids the
  `discover -> nse_scraper` cycle).
- Must not: import `agent.py`, `bse_client`, `bse_master`,
  `pipeline.*`, FastAPI, or any DB session module. Tier-1 is a pure
  read-side service.

## Patterns (symmetry)

- When `map_nse_category` returns `None`, `_infer_document_type` classifies
  rows from `attchmntText` / URL basename (e.g. `MediaRelease.pdf`,
  `SEFR_*`, "submitted … financial results"). Many NSE result PDFs use
  generic `desc` values (`Outcome of Board Meeting`, `Updates`,
  `Press Release`) that the static map does not cover.
- Rows mapped to `CONCALL_TRANSCRIPT` by category alone must also pass
  `_has_transcript_signals` — board-meeting prior intimations filed
  under the analyst-meet category are rejected.
- Attachments whose URL does not end in `.pdf`, `.txt`, or `.md` are
  dropped in `_row_to_filing` (e.g. postal-ballot `.zip` packages filed
  as “financial results”). Per-`DocumentType` selection only considers
  ingestible URLs, then picks the latest by `filing_date`.
- Period filtering mirrors `_filter_keys_for_period` in
  [`discover.py`](discover.py): annual periods only consider
  `annual_report`; quarterly periods skip it.
- Latest-per-doc-type pick mirrors `_pick_latest_per_type` in
  [`discover.py`](discover.py).
- Row parsing mirrors `nse_client._row_to_filing` (multiple key
  spellings, URL scheme repair, lenient date parser).
- `_period_markers(period)` builds a lowercased set of:
  - FY tokens (`fy2024-25`, `fy24-25`, `fy2425`, with and without
    space after `fy`).
  - `Q{q} FY...` combinations.
  - `period_end` rendered as `DD-MM-YYYY`, `DD.MM.YYYY`, `DD/MM/YYYY`,
    `DDMMYYYY`, `YYYY-MM-DD`, plus month-name spellings and ordinals
    (`31st december 2024`, `december 31, 2024`, `dec 2024`, etc.).
  - For annual periods, additional "year ended ..." phrasings; for
    quarterly periods, "quarter ended ..." phrasings.
- A row matches the period if **any** marker is a substring of the
  row's lowercased `text_blob` (combination of `attchmntText`, `desc`,
  `subCategory`, `subject`, `smIndustry`, the attachment URL
  basename, and the headline).
- The per-symbol payload cache lives in the CLI
  ([`bulk_ingest._run_async`](../../scripts/bulk_ingest.py),
  `scraper_payload_cache`), not in this module — keeps the module
  callable in isolation for tests.

## Verification checklist

- [ ] Without `nse_symbol`, the function returns an empty
      `DiscoveryResult` and logs an INFO line.
- [ ] When `payload` is passed in, the function does **not** open an
      `httpx.Client` and does **not** call NSE.
- [ ] `_period_markers` for `Q3 FY2024-25` contains both
      `"q3 fy24-25"` and `"31st december 2024"`.
- [ ] A row whose `attchmntText` contains "Quarter ended 31st
      December, 2024" matches the `Q3 FY2024-25` marker set.
- [ ] Rows whose category does not map via `map_nse_category` are
      dropped.
- [ ] When two filings of the same `DocumentType` match, the one with
      the later `filing_date` wins.
- [ ] `source_by_asset_key[key] == "nse_scraper"` on every filled key;
      `fallback_by_asset_key` is always empty.
- [ ] Annual periods only produce an `annual_report` slot; quarterly
      periods never produce one.
