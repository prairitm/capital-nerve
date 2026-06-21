# exchange/bse_client

> Inherits: ./_BASE.md

## Purpose

Synchronous client for BSE's corporate-announcements API. Given a
6-digit scrip code and a date window, returns a list of
`ExchangeFiling` rows.

## Source

- Path: `backend/app/services/ir_discovery/exchange/bse_client.py`
- Layer: backend-service-helper

## Contract

- `list_filings(*, scrip: str, from_date: date, to_date: date,
  timeout: float = 30.0, client: Optional[httpx.Client] = None)
  -> list[ExchangeFiling]`.
- Endpoint: `GET https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w`.
- Params: `strScrip`, `strPrevDate=YYYYMMDD`, `strToDate=YYYYMMDD`,
  `strSearch=P`, `strType=C`, `strCat=-1`, `pageno=1`.
- PDF URL: when `ATTACHMENTNAME` is a bare filename, prepended with
  `https://www.bseindia.com/xml-data/corpfiling/AttachLive/`. When it
  is already an absolute URL, used as-is.
- Returns `[]` on HTTP / JSON error — never raises.

## Dependencies

- May import: `httpx`, stdlib (`datetime`, `logging`, `typing`),
  `.schemas` (`ExchangeFiling`, `map_bse_category`).
- Must not: import `nse_client`, `discover`, `bse_master`.

## Patterns (symmetry)

- Browser-like `User-Agent`: BSE will 403 the default httpx UA.
- Date format: `YYYYMMDD`, no separator — different from NSE.
- Multiple key spellings handled (`CATEGORYNAME` vs `CategoryName` etc.)
  because BSE has changed its JSON casing more than once.
- One bad row in the payload never kills the whole list — caught,
  logged at DEBUG.

## Verification checklist

- [ ] `list_filings` opens its own `httpx.Client` when none is supplied
      and closes it on exit.
- [ ] All accepted `NEWS_DT` formats round-trip a fixture date.
- [ ] Categories not in `BSE_CATEGORY_MAP` round-trip with
      `document_type=None`.
- [ ] `ATTACHMENTNAME=https://...` flows through unchanged.
