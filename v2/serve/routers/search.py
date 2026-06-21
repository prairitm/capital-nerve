"""Search router — keyword match over companies, events, cards, parsed docs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import ids, mapper
from ..builder import Catalog
from ..config import settings
from ..deps import catalog_dep, get_current_user
from ..schemas import AskRequest
from ..state import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    q: str = Query(min_length=1),
    company_id: int | None = None,
    document_type: str | None = None,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict:
    needle = q.lower()
    companies = [
        b
        for b in (mapper.company_brief(catalog, t) for t in catalog.tickers())
        if needle in b["company_name"].lower() or needle in (b["nse_symbol"] or "").lower()
    ]

    events: list[dict] = []
    cards: list[dict] = []
    for built in catalog.all_built():
        brief = mapper.intelligence_object_brief(catalog, built)
        haystack = f"{brief['title']} {brief['subtitle']} {built.period.ticker}".lower()
        if needle not in haystack:
            continue
        events.append(
            {
                "event_id": brief["event_id"],
                "event_type": brief["event_type"],
                "event_title": brief["event_title"],
                "event_date": brief["event_date"],
                "company_name": built.period.ticker.title(),
                "company_symbol": built.period.ticker,
            }
        )
        cards.append(
            {
                "card_id": brief["intelligence_object_id"],
                "card_type": brief["object_type"],
                "headline": brief["title"],
                "one_line_summary": brief["subtitle"],
                "signal_direction": brief["status"],
                "severity": brief["severity"],
                "company_name": built.period.ticker.title(),
                "company_symbol": built.period.ticker,
            }
        )

    return {
        "companies": companies,
        "events": events,
        "cards": cards,
        "document_hits": _document_hits(catalog, needle),
    }


def _document_hits(catalog: Catalog, needle: str) -> list[dict]:
    hits: list[dict] = []
    for filing in catalog._filings:  # noqa: SLF001
        md_path = settings.parsed_dir / f"{filing.document_id}.md"
        if not md_path.exists():
            continue
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        idx = text.lower().find(needle)
        if idx < 0:
            continue
        start = max(0, idx - 80)
        snippet = text[start : idx + 120].replace("\n", " ").strip()
        hits.append(
            {
                "document_id": ids.document_id(filing.document_id),
                "page_number": 1,
                "snippet": snippet,
                "document_type": "FINANCIAL_RESULT",
                "document_title": filing.title or f"{filing.ticker} filing",
                "company_id": ids.company_id(filing.ticker),
                "company_name": filing.ticker.title(),
                "company_symbol": filing.ticker,
                "rank": 1.0,
            }
        )
        if len(hits) >= 15:
            break
    return hits


@router.post("/ask")
def ask(
    body: AskRequest,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict:
    answer = _build_answer(catalog, body)
    return {
        "answer": answer,
        "mode": "rag",
        "citations": [],
        "retrieval_mode": "fts_only",
        "sql": None,
        "columns": [],
        "rows": [],
        "row_count": 0,
    }


@router.post("/ask-data")
def ask_data(
    body: AskRequest,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict:
    return {
        "answer": _build_answer(catalog, body),
        "sql": "SELECT fact_key, numeric_value FROM fact_values",
        "columns": [],
        "rows": [],
        "row_count": 0,
    }


def _build_answer(catalog: Catalog, body: AskRequest) -> str:
    ticker = None
    if body.company_id is not None:
        for t in catalog.tickers():
            if ids.company_id(t) == body.company_id:
                ticker = t
                break
    if ticker is None:
        return (
            "This serving layer answers from the latest stored quarterly metrics. "
            "Open a company to see its revenue, EBITDA, PAT and EPS for the most recent quarter."
        )
    latest = catalog.latest_period(ticker)
    if latest is None:
        return f"No stored metrics found for {ticker}."
    built = catalog.build_period(latest)
    parts = [
        f"{mapper.METRIC_META.get(mapper._row_key(m), (mapper._row_key(m), mapper._row_key(m), ''))[1]}: {m['value']}"
        for m in built.card_metrics
        if m.get("derivation") == "raw"
    ]
    return f"{ticker} {latest.label} ({built.basis_used}): " + "; ".join(parts)
