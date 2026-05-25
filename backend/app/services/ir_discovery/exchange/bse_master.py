"""BSE listed-equity master-list cache + ``nse_symbol -> bse_code`` resolver.

The seed loads NSE symbols into ``Company.nse_symbol`` but leaves
``Company.bse_code`` null (the input source has no BSE codes). The
exchange-tier discovery needs a BSE scrip code to call
``api.bseindia.com``, so we backfill ``Company.bse_code`` from BSE's
own master list:

- Endpoint: ``https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w``.
- Response: list of ``{SCRIP_CD, SCRIP_NAME, ISIN_NUMBER, NSE_CODE,
  GROUP, STATUS, ...}`` rows for active equity instruments.
- Cache: stored on disk at ``<settings.STORAGE_DIR>/../bse_master/equity.json``,
  refreshed once per ``BSE_MASTER_TTL_DAYS`` (default 7).

Resolution order for a `Company`:

1. ``isin`` (highest confidence — a globally unique 12-char identifier).
2. ``nse_symbol`` exact match against the master list's ``NSE_CODE``.
3. Fuzzy match on ``company_name`` vs. ``SCRIP_NAME`` using
   ``difflib.SequenceMatcher`` with a configurable cutoff (default 0.92).

When ``lazy_resolve_bse_code`` resolves a code it persists it to
``Company.bse_code`` in the same session so subsequent calls are
zero-cost.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.master import Company


logger = logging.getLogger(__name__)


_MASTER_ENDPOINT = (
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"
    "?Group=&Scripcode=&industry=&segment=Equity&status=Active"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


# ---------------------------------------------------------------------------
# Master-list shape + fetch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BseScrip:
    """One row of the BSE listed-equity master list."""

    scrip_code: str
    scrip_name: str
    isin: Optional[str]
    nse_code: Optional[str]


def _master_path() -> Path:
    """Disk cache path: ``<STORAGE_DIR>/../bse_master/equity.json``."""
    root = settings.storage_path.parent / "bse_master"
    root.mkdir(parents=True, exist_ok=True)
    return root / "equity.json"


def _ttl_seconds() -> int:
    days = getattr(settings, "BSE_MASTER_TTL_DAYS", 7)
    return int(days) * 86_400


def load_master(*, force_refresh: bool = False) -> list[BseScrip]:
    """Return the cached master list, refreshing from BSE when stale."""
    path = _master_path()
    if not force_refresh and path.is_file():
        age = time.time() - path.stat().st_mtime
        if age < _ttl_seconds():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                return [_row_to_scrip(r) for r in payload if r]
            except (OSError, ValueError) as exc:
                logger.warning("Failed to read BSE master cache (%s); refreshing", exc)
    return _refresh_master(path)


def _refresh_master(path: Path) -> list[BseScrip]:
    logger.info("Refreshing BSE master list from %s", _MASTER_ENDPOINT)
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True, headers=_HEADERS) as client:
            response = client.get(_MASTER_ENDPOINT)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("BSE master fetch failed: %s", exc)
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return []
        else:
            return []

    rows = _coerce_rows(payload)
    # Persist a normalised shape so the cache reader doesn't have to
    # remember which key BSE used today.
    normalised = [_normalise_row(r) for r in rows if r]
    normalised = [r for r in normalised if r is not None]
    try:
        path.write_text(json.dumps(normalised, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write BSE master cache: %s", exc)
    return [_row_to_scrip(r) for r in normalised]


def _coerce_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("Table", "data", "Rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _normalise_row(row: dict) -> Optional[dict]:
    """Squash BSE's varying field names into a stable shape.

    The actual `ListofScripData/w` payload (verified Apr 2026) returns:
    `SCRIP_CD`, `Scrip_Name`, `Issuer_Name`, `ISIN_NUMBER`, `scrip_id`
    (which holds the NSE ticker — surprising but consistent), plus
    `Status`, `GROUP`, `Mktcap` etc.

    Older and snake_case spellings are preserved as fallbacks because
    BSE has historically rotated the casing.
    """
    if not isinstance(row, dict):
        return None
    code = (
        row.get("SCRIP_CD")
        or row.get("scrip_cd")
        or row.get("Scrip_Code")
        or row.get("Scripcode")
    )
    name = (
        row.get("Scrip_Name")
        or row.get("SCRIP_NAME")
        or row.get("scrip_name")
        or row.get("Issuer_Name")
        or row.get("ISSUER_NAME")
        or row.get("issuer_name")
    )
    if not code or not name:
        return None
    isin = row.get("ISIN_NUMBER") or row.get("ISIN") or row.get("isin")
    # The NSE ticker is published under the `scrip_id` key on BSE's
    # master endpoint (e.g. `scrip_id="RELIANCE"` for SCRIP_CD=500325).
    # Older code paths used `NSE_CODE`; we keep both for resilience.
    nse = (
        row.get("scrip_id")
        or row.get("Scrip_ID")
        or row.get("SCRIP_ID")
        or row.get("NSE_CODE")
        or row.get("nse_code")
        or row.get("NSE_Code")
    )
    return {
        "scrip_code": str(code).strip(),
        "scrip_name": str(name).strip(),
        "isin": (isin or None) and str(isin).strip().upper(),
        "nse_code": (nse or None) and str(nse).strip().upper(),
    }


def _row_to_scrip(row: dict) -> BseScrip:
    return BseScrip(
        scrip_code=row["scrip_code"],
        scrip_name=row["scrip_name"],
        isin=row.get("isin"),
        nse_code=row.get("nse_code"),
    )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolutionMatch:
    scrip_code: str
    scrip_name: str
    method: str  # "isin" | "nse_symbol" | "fuzzy"
    score: float  # 1.0 for exact matches; ratio in [0, 1] for fuzzy


def resolve(
    *,
    isin: Optional[str],
    nse_symbol: Optional[str],
    company_name: Optional[str],
    master: list[BseScrip],
    fuzzy_cutoff: float = 0.92,
) -> Optional[ResolutionMatch]:
    """Find the best BSE scrip for a Company row. Returns ``None`` when
    the best fuzzy match is below the cutoff."""
    if isin:
        target = isin.strip().upper()
        for s in master:
            if s.isin and s.isin == target:
                return ResolutionMatch(s.scrip_code, s.scrip_name, "isin", 1.0)

    if nse_symbol:
        target = nse_symbol.strip().upper()
        for s in master:
            if s.nse_code and s.nse_code == target:
                return ResolutionMatch(s.scrip_code, s.scrip_name, "nse_symbol", 1.0)

    if company_name:
        normalised_target = _normalise_name(company_name)
        best: Optional[ResolutionMatch] = None
        for s in master:
            ratio = SequenceMatcher(
                None, normalised_target, _normalise_name(s.scrip_name)
            ).ratio()
            if ratio >= fuzzy_cutoff and (best is None or ratio > best.score):
                best = ResolutionMatch(s.scrip_code, s.scrip_name, "fuzzy", ratio)
        return best

    return None


_LEGAL_SUFFIXES = (
    " ltd",
    " limited",
    " ltd.",
    " limited.",
    " pvt",
    " private",
    " corp",
    " corporation",
    " co",
    " co.",
    " inc",
    " incorporated",
)


def _normalise_name(name: str) -> str:
    n = name.strip().lower()
    n = n.replace("&", "and")
    n = "".join(c if c.isalnum() or c.isspace() else " " for c in n)
    n = " ".join(n.split())
    for suffix in _LEGAL_SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return n


# ---------------------------------------------------------------------------
# Lazy in-process resolution
# ---------------------------------------------------------------------------


def lazy_resolve_bse_code(
    db: Session,
    company: Company,
    *,
    master: Optional[list[BseScrip]] = None,
    persist: bool = True,
    fuzzy_cutoff: float = 0.92,
) -> Optional[str]:
    """Resolve and (optionally) persist ``Company.bse_code`` if missing.

    Returns the BSE scrip code if known or successfully resolved;
    ``None`` if the master list cannot identify the issuer with high
    confidence (in which case the caller falls back to NSE / agent for
    that company).
    """
    if company.bse_code:
        return company.bse_code

    catalog = master if master is not None else load_master()
    if not catalog:
        logger.warning(
            "BSE master list is empty; cannot resolve bse_code for %s",
            company.nse_symbol or company.company_name,
        )
        return None

    match = resolve(
        isin=company.isin,
        nse_symbol=company.nse_symbol,
        company_name=company.company_name,
        master=catalog,
        fuzzy_cutoff=fuzzy_cutoff,
    )
    if match is None:
        logger.warning(
            "Could not resolve bse_code for %s (isin=%s, nse=%s)",
            company.company_name,
            company.isin,
            company.nse_symbol,
        )
        return None

    logger.info(
        "Resolved bse_code for %s -> %s via %s (score=%.2f, master_name=%r)",
        company.nse_symbol or company.company_name,
        match.scrip_code,
        match.method,
        match.score,
        match.scrip_name,
    )
    if persist:
        company.bse_code = match.scrip_code
        db.add(company)
        try:
            db.commit()
        except Exception as exc:  # don't let a unique-constraint blow up the run
            db.rollback()
            logger.warning(
                "Failed to persist bse_code=%s for company_id=%s: %s",
                match.scrip_code,
                company.company_id,
                exc,
            )
    return match.scrip_code


__all__ = [
    "BseScrip",
    "ResolutionMatch",
    "lazy_resolve_bse_code",
    "load_master",
    "resolve",
]
