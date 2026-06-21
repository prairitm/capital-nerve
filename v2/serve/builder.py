"""Read-only metric derivation and card construction over the v2 store.

This mirrors the deterministic parts of the v2 notebook's metrics/signals/cards
cells (YoY, QoQ, margins, signal rules) so the serving layer can rebuild the
same intelligence on demand from `fact_values`. It imports the pure helpers
from `capital_nerve_logic` and never writes to the database.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ROOT_DIR, settings

# Ensure the v2 top-level modules (`capital_nerve_db`, `capital_nerve_logic`)
# are importable regardless of the process working directory.
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from capital_nerve_db import FactStore  # noqa: E402
from capital_nerve_logic import earnings_card_metrics, interpret_metric_signals  # noqa: E402
from catalog_engine import ScopeContext, compute_catalog_metrics  # noqa: E402
from periods import prior_quarter  # noqa: E402

PREFERRED_BASIS = "consolidated"
_SEVERITY_RANK = {"watch": 2, "info": 1}


@dataclass
class Period:
    ticker: str
    quarter: int
    fy_start_year: int
    fy_label: str
    quarter_end: str
    label: str


@dataclass
class Filing:
    document_id: str
    ticker: str
    sha256: str
    title: str | None
    quarter: int | None
    fy_start_year: int | None
    fy_label: str | None
    quarter_end: str | None
    ingested_at: str


@dataclass
class BuiltPeriod:
    period: Period
    basis_used: str
    metrics: list[dict[str, Any]]
    card_metrics: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    filing: Filing | None


class Catalog:
    """In-memory index over the v2 store: companies, periods, filings, cards."""

    def __init__(self, store: FactStore | None = None) -> None:
        self.store = store or FactStore(settings.db_path)
        self._built: dict[tuple[str, int, int], BuiltPeriod] = {}
        self._filings: list[Filing] = []
        self.refresh()

    # ------------------------------------------------------------------ load
    def refresh(self) -> None:
        self._built.clear()
        self._filings = self._load_filings()

    def _load_filings(self) -> list[Filing]:
        if not Path(self.store.db_path).exists():
            return []
        conn = sqlite3.connect(f"file:{self.store.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT document_id, company_ticker, sha256, title, quarter,
                       fy_start_year, fy_label, quarter_end, ingested_at
                FROM filings
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        return [
            Filing(
                document_id=r["document_id"],
                ticker=r["company_ticker"],
                sha256=r["sha256"],
                title=r["title"],
                quarter=r["quarter"],
                fy_start_year=r["fy_start_year"],
                fy_label=r["fy_label"],
                quarter_end=r["quarter_end"],
                ingested_at=r["ingested_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------- companies
    def tickers(self) -> list[str]:
        seen: dict[str, None] = {}
        conn = sqlite3.connect(f"file:{self.store.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT DISTINCT company_ticker FROM fact_values"
            ).fetchall()
            for r in rows:
                seen[r["company_ticker"]] = None
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()
        for f in self._filings:
            seen.setdefault(f.ticker, None)
        return sorted(seen)

    def resolve_ticker(self, symbol: str) -> str | None:
        target = symbol.strip().upper()
        for t in self.tickers():
            if t.upper() == target:
                return t
        return None

    # --------------------------------------------------------------- periods
    def periods(self, ticker: str) -> list[Period]:
        raw = self.store.list_periods(ticker)
        return [
            Period(
                ticker=ticker,
                quarter=p["quarter"],
                fy_start_year=p["fy_start_year"],
                fy_label=p["fy_label"],
                quarter_end=p["quarter_end"],
                label=p["label"],
            )
            for p in raw
        ]

    def latest_period(self, ticker: str) -> Period | None:
        periods = self.periods(ticker)
        return periods[-1] if periods else None

    def filings_for(self, ticker: str) -> list[Filing]:
        items = [f for f in self._filings if f.ticker == ticker]
        return sorted(items, key=lambda f: (f.quarter_end or ""))

    def filing_for_period(
        self, ticker: str, quarter: int, fy_start_year: int
    ) -> Filing | None:
        for f in self._filings:
            if (
                f.ticker == ticker
                and f.quarter == quarter
                and f.fy_start_year == fy_start_year
            ):
                return f
        return None

    def filing_by_document_id(self, document_id: str) -> Filing | None:
        for f in self._filings:
            if f.document_id == document_id:
                return f
        return None

    # ------------------------------------------------------ metric assembly
    def _load_base(
        self, ticker: str, quarter: int, fy_start_year: int
    ) -> tuple[dict[str, dict[str, Any]], str]:
        details = self.store.load_fact_details(
            ticker, quarter, fy_start_year, PREFERRED_BASIS
        )
        if details:
            return details, PREFERRED_BASIS
        fallback = self.store.load_fact_details(
            ticker, quarter, fy_start_year, "standalone"
        )
        if fallback:
            return fallback, "standalone"
        return {}, PREFERRED_BASIS

    def build_period(self, period: Period) -> BuiltPeriod:
        key = (period.ticker, period.quarter, period.fy_start_year)
        if key in self._built:
            return self._built[key]

        base, basis_used = self._load_base(
            period.ticker, period.quarter, period.fy_start_year
        )
        prior_year_details = self.store.load_fact_details(
            period.ticker, period.quarter, period.fy_start_year - 1, basis_used
        )
        pq, pfy = prior_quarter(period.quarter, period.fy_start_year)
        prior_quarter_details = self.store.load_fact_details(
            period.ticker, pq, pfy, basis_used
        )

        metrics = self._compute_metrics(
            base, prior_year_details, prior_quarter_details, period.label
        )
        signals = interpret_metric_signals(metrics)
        card_metrics = earnings_card_metrics(metrics)
        filing = self.filing_for_period(
            period.ticker, period.quarter, period.fy_start_year
        )

        built = BuiltPeriod(
            period=period,
            basis_used=basis_used,
            metrics=metrics,
            card_metrics=card_metrics,
            signals=signals,
            filing=filing,
        )
        self._built[key] = built
        return built

    def _compute_metrics(
        self,
        base: dict[str, dict[str, Any]],
        prior_year: dict[str, dict[str, Any]],
        prior_quarter: dict[str, dict[str, Any]],
        period_label: str,
    ) -> list[dict[str, Any]]:
        ctx = ScopeContext.from_fact_details(base, prior_year, prior_quarter)
        return compute_catalog_metrics(ctx, period_label=period_label, raw_details=base)

    # ------------------------------------------------------------- iteration
    def all_built(self) -> list[BuiltPeriod]:
        out: list[BuiltPeriod] = []
        for ticker in self.tickers():
            for period in self.periods(ticker):
                out.append(self.build_period(period))
        return out

    def built_for_ticker(self, ticker: str) -> list[BuiltPeriod]:
        return [self.build_period(p) for p in self.periods(ticker)]

    def primary_signal(self, built: BuiltPeriod) -> dict[str, Any] | None:
        if not built.signals:
            return None
        material = [s for s in built.signals if s["signal_key"] != "no_material_change"]
        if not material:
            return None
        return max(material, key=lambda s: _SEVERITY_RANK.get(s.get("severity", ""), 0))


_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
    return _catalog


def reset_catalog() -> None:
    """Rebuild the cached catalog (after the DB changes underneath us)."""
    global _catalog
    _catalog = Catalog()
