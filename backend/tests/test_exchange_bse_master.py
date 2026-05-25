"""Unit tests for `services/ir_discovery/exchange/bse_master`.

Pure-function checks for the resolver: ISIN match wins, exact NSE
symbol wins next, and fuzzy name-matching only fires when nothing
better is available — and only above the cutoff.
"""
from __future__ import annotations

from app.services.ir_discovery.exchange.bse_master import (
    BseScrip,
    _normalise_row,
    resolve,
)


_MASTER = [
    BseScrip(
        scrip_code="500325",
        scrip_name="RELIANCE INDUSTRIES LTD.",
        isin="INE002A01018",
        nse_code="RELIANCE",
    ),
    BseScrip(
        scrip_code="532540",
        scrip_name="TATA CONSULTANCY SERVICES LTD.",
        isin="INE467B01029",
        nse_code="TCS",
    ),
    BseScrip(
        scrip_code="500570",
        scrip_name="TATA MOTORS LIMITED",
        isin="INE155A01022",
        nse_code="TATAMOTORS",
    ),
    BseScrip(
        scrip_code="500920",
        scrip_name="TATA STEEL LIMITED",
        isin="INE081A01020",
        nse_code="TATASTEEL",
    ),
]


def test_resolve_by_isin_wins():
    match = resolve(
        isin="INE002A01018",
        nse_symbol=None,
        company_name=None,
        master=_MASTER,
    )
    assert match is not None
    assert match.scrip_code == "500325"
    assert match.method == "isin"
    assert match.score == 1.0


def test_resolve_by_isin_takes_priority_over_nse_symbol():
    """Both ISIN and NSE symbol target different rows -> ISIN wins."""
    match = resolve(
        isin="INE467B01029",  # TCS by ISIN
        nse_symbol="RELIANCE",  # but reliance by symbol
        company_name=None,
        master=_MASTER,
    )
    assert match is not None
    assert match.method == "isin"
    assert match.scrip_code == "532540"


def test_resolve_by_nse_symbol_when_isin_missing():
    match = resolve(
        isin=None,
        nse_symbol="TCS",
        company_name=None,
        master=_MASTER,
    )
    assert match is not None
    assert match.method == "nse_symbol"
    assert match.scrip_code == "532540"


def test_resolve_fuzzy_when_only_name_available():
    match = resolve(
        isin=None,
        nse_symbol=None,
        company_name="Reliance Industries Limited",
        master=_MASTER,
    )
    assert match is not None
    assert match.method == "fuzzy"
    assert match.scrip_code == "500325"
    assert match.score >= 0.92


def test_resolve_fuzzy_normalises_legal_suffixes():
    """`Tata Motors Ltd` and `TATA MOTORS LIMITED` should match after
    suffix stripping + lowercase."""
    match = resolve(
        isin=None,
        nse_symbol=None,
        company_name="Tata Motors Ltd",
        master=_MASTER,
    )
    assert match is not None
    assert match.scrip_code == "500570"


def test_resolve_returns_none_when_below_cutoff():
    match = resolve(
        isin=None,
        nse_symbol=None,
        company_name="Some Completely Unrelated Industries",
        master=_MASTER,
        fuzzy_cutoff=0.92,
    )
    assert match is None


def test_resolve_returns_none_when_no_inputs():
    assert resolve(
        isin=None,
        nse_symbol=None,
        company_name=None,
        master=_MASTER,
    ) is None


def test_resolve_picks_best_fuzzy_score():
    """Multiple fuzzy candidates -> best ratio wins."""
    match = resolve(
        isin=None,
        nse_symbol=None,
        company_name="Tata Steel Limited",
        master=_MASTER,
        fuzzy_cutoff=0.85,
    )
    assert match is not None
    assert match.scrip_code == "500920"


# ---------------------------------------------------------------------------
# Master-row normalisation: BSE's actual field names
# ---------------------------------------------------------------------------


def test_normalise_row_reads_real_bse_fields():
    """The `ListofScripData/w` endpoint returns SCRIP_CD / Scrip_Name /
    ISIN_NUMBER / scrip_id (the NSE ticker)."""
    row = {
        "SCRIP_CD": "500325",
        "Scrip_Name": "Reliance Industries Ltd",
        "Status": "Active",
        "GROUP": "A",
        "FACE_VALUE": "10.00",
        "ISIN_NUMBER": "INE002A01018",
        "INDUSTRY": None,
        "scrip_id": "RELIANCE",
        "Segment": "Equity",
        "NSURL": "https://www.bseindia.com/...",
        "Issuer_Name": "Reliance Industries Ltd",
        "Mktcap": "1833117.70",
    }
    out = _normalise_row(row)
    assert out is not None
    assert out["scrip_code"] == "500325"
    assert out["scrip_name"] == "Reliance Industries Ltd"
    assert out["isin"] == "INE002A01018"
    assert out["nse_code"] == "RELIANCE"


def test_normalise_row_falls_back_to_legacy_keys():
    """Older payloads exposed NSE_CODE; resolver still tolerates it."""
    row = {
        "SCRIP_CD": "532540",
        "SCRIP_NAME": "TATA CONSULTANCY SERVICES LTD.",
        "ISIN": "INE467B01029",
        "NSE_CODE": "TCS",
    }
    out = _normalise_row(row)
    assert out is not None
    assert out["scrip_code"] == "532540"
    assert out["nse_code"] == "TCS"
    assert out["isin"] == "INE467B01029"


def test_normalise_row_drops_invalid_rows():
    assert _normalise_row({}) is None
    assert _normalise_row({"SCRIP_CD": "500325"}) is None  # no name
    assert _normalise_row({"Scrip_Name": "Something"}) is None  # no code
    assert _normalise_row(None) is None  # type: ignore[arg-type]


def test_real_master_row_drives_exact_nse_resolution():
    """End-to-end through `_normalise_row` + `resolve`: a single real
    BSE row should let `nse_symbol="RELIANCE"` resolve via the exact
    `nse_symbol` path with score 1.0 (no fuzzy)."""
    raw = {
        "SCRIP_CD": "500325",
        "Scrip_Name": "Reliance Industries Ltd",
        "ISIN_NUMBER": "INE002A01018",
        "scrip_id": "RELIANCE",
    }
    normalised = _normalise_row(raw)
    assert normalised is not None
    scrip = BseScrip(**normalised)
    match = resolve(
        isin=None,
        nse_symbol="RELIANCE",
        company_name="Reliance",  # short / ambiguous; should NOT need fuzzy
        master=[scrip],
    )
    assert match is not None
    assert match.method == "nse_symbol"
    assert match.scrip_code == "500325"
    assert match.score == 1.0
