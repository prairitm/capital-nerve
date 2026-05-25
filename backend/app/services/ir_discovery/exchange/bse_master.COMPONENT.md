# exchange/bse_master

> Inherits: ./_BASE.md

## Purpose

Fetches and caches BSE's full listed-equity master list, then resolves
a `Company` row's missing `bse_code` from it. Two callers:

- The standalone backfill script
  [`scripts/resolve_bse_codes.py`](../../../scripts/resolve_bse_codes.py)
  — runs once after seed.
- `discover.py:_resolve_bse_code` — calls
  :func:`lazy_resolve_bse_code` mid-run when `Company.bse_code` is null.

## Master-list field reference

The `ListofScripData/w` endpoint returns rows shaped like this
(verified Apr 2026):

| BSE field    | Our normalised key | Used for                 |
|--------------|--------------------|--------------------------|
| `SCRIP_CD`   | `scrip_code`       | The 6-digit BSE code     |
| `Scrip_Name` | `scrip_name`       | Fuzzy `company_name` match |
| `Issuer_Name`| (fallback for name)| Fuzzy `company_name` match |
| `ISIN_NUMBER`| `isin`             | Highest-confidence resolve |
| `scrip_id`   | `nse_code`         | Exact NSE-symbol resolve   |

Note the surprising name: the NSE ticker is exposed on the BSE master
under `scrip_id`, not `NSE_CODE`. Older spellings (`NSE_CODE`,
`Scrip_ID`, etc.) are kept as fallbacks because BSE has rotated the
casing in the past.

## Source

- Path: `backend/app/services/ir_discovery/exchange/bse_master.py`
- Layer: backend-service-helper

## Contract

- `load_master(*, force_refresh: bool = False) -> list[BseScrip]`.
  Reads `<STORAGE_DIR>/../bse_master/equity.json` if fresher than
  `BSE_MASTER_TTL_DAYS`; otherwise refetches from the BSE master-list
  endpoint and rewrites the cache.
- `resolve(*, isin, nse_symbol, company_name, master,
  fuzzy_cutoff=0.92) -> Optional[ResolutionMatch]`. Resolution order:
  ISIN → exact NSE-symbol → fuzzy-name match (`difflib.SequenceMatcher`,
  legal-suffix stripped). Returns `None` when no method clears the
  cutoff.
- `lazy_resolve_bse_code(db, company, *, master=None,
  persist=True, fuzzy_cutoff=0.92) -> Optional[str]`. Memoising
  wrapper that writes the resolved code back to `Company.bse_code`.

## Dependencies

- May import: `httpx`, `sqlalchemy.orm.Session`, `app.core.config`,
  `app.models.master.Company`, stdlib.
- Must not: import sibling exchange modules (`bse_client`, `nse_client`,
  `discover`).

## Patterns (symmetry)

- Cache lives **off** the canonical `STORAGE_DIR`, in a peer
  `bse_master/` directory. An S3 swap on the canonical store does not
  break it.
- Refresh failures fall back to the previous cache file — we'd rather
  serve a slightly stale list than fail the run.
- Names are normalised before fuzzy matching: lowercase, ampersand →
  "and", non-alnum stripped, common suffixes (`ltd`, `limited`,
  `private`, ...) trimmed.

## Verification checklist

- [ ] `load_master` never raises on network failure when a cache file
      exists.
- [ ] `resolve` returns `None` (not a low-confidence match) when ISIN
      and NSE symbol miss and the best fuzzy ratio is below
      `fuzzy_cutoff`.
- [ ] `lazy_resolve_bse_code` rolls back on integrity errors so the
      run continues.
- [ ] Cache TTL respects `settings.BSE_MASTER_TTL_DAYS`.
